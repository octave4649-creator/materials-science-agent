"""腾讯云静态 demo 部署脚本（替换旧 streamlit 部署）。

将 `docs/demo-panel.html`（完全自包含静态页面）部署到腾讯云 Lighthouse，
nginx 直接静态托管，取代旧版 streamlit 反代部署。

凭据从环境变量读取（禁止硬编码入库）：
    TENCENT_HOST（默认 120.53.11.211）/ TENCENT_USER（默认 ubuntu）/ TENCENT_PWD（必填）

用法:
    python scripts/deploy_demo_static.py cleanup    # 停旧 streamlit 服务 + 清旧目录 + 清旧 nginx 反代
    python scripts/deploy_demo_static.py upload     # 上传 demo-panel.html 到 /var/www/html/
    python scripts/deploy_demo_static.py nginx      # 写入静态托管 nginx 配置
    python scripts/deploy_demo_static.py verify     # 验证（本机 + 公网 HTTP）
    python scripts/deploy_demo_static.py all        # 按顺序执行全部
"""
# ruff: noqa: E501
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request
from pathlib import Path

import paramiko

HOST = os.environ.get("TENCENT_HOST", "120.53.11.211")
USER = os.environ.get("TENCENT_USER", "ubuntu")
PWD = os.environ.get("TENCENT_PWD", "")
PORT = 22

LOCAL_ROOT = Path(__file__).resolve().parents[1]
DEMO_SRC = LOCAL_ROOT / "docs" / "demo-panel.html"
WEB_ROOT = "/var/www/html"

SVC_OLD = "streamlit-materials-agent"   # 旧 streamlit 部署的服务名
APP_DIR_OLD = "/home/ubuntu/materials-science-agent"
NGINX_OLD = "materials-agent"            # 旧 nginx 反代站点名


def new_client() -> paramiko.SSHClient:
    if not PWD:
        raise RuntimeError("缺少 TENCENT_PWD 环境变量（腾讯云服务器密码）")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PWD, timeout=30,
              banner_timeout=60, auth_timeout=30)
    return c


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def run(c: paramiko.SSHClient, cmd: str, *, sudo: bool = False, timeout: int = 300,
        silent: bool = False) -> tuple[int, str, str]:
    if sudo:
        real = f"echo {_sh_quote(PWD)} | sudo -S -p '' bash -lc {_sh_quote(cmd)}"
    else:
        real = f"bash -lc {_sh_quote(cmd)}"
    _stdin, stdout, stderr = c.exec_command(real, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if not silent:
        hdr = f"===== [{code}] $ {cmd[:120]}"
        if len(cmd) > 120:
            hdr += "..."
        sys.stderr.write("\n" + hdr + "\n")
        if out:
            tail = out if len(out) < 1500 else out[-1500:]
            sys.stderr.write(tail)
            if len(out) > 1500:
                sys.stderr.write(f"\n... (truncated {len(out)} chars)\n")
        if err.strip():
            sys.stderr.write("-- STDERR:\n" + err[-800:] + "\n")
    return code, out, err


def _put_text(c: paramiko.SSHClient, remote_path: str, content: str, *, sudo: bool = False) -> None:
    import hashlib
    tmp = f"/tmp/_deploy_{hashlib.md5(remote_path.encode()).hexdigest()}"
    sftp = c.open_sftp()
    try:
        with sftp.file(tmp, "w") as f:
            f.write(content)
    finally:
        sftp.close()
    if sudo:
        run(c, f"mv {tmp} {remote_path} && chmod 0644 {remote_path}", sudo=True)
    else:
        run(c, f"mv {tmp} {remote_path} && chmod 0644 {remote_path}")


def stage_cleanup(c: paramiko.SSHClient) -> None:
    print("========== CLEANUP（仅本项目旧 streamlit 部署，不碰 jinmao/docker 等无关服务） ==========")
    # 1. 停并禁用旧 streamlit 服务
    run(c, f"systemctl stop {SVC_OLD}.service 2>/dev/null; systemctl disable {SVC_OLD}.service 2>/dev/null; true", sudo=True)
    # 2. 杀占用 8501 的残留 streamlit 进程
    kill_ports = r"""
    for PORT_NUM in 8501; do
        PID=$(ss -ltnp 2>/dev/null | awk -v P=":$PORT_NUM " '$4 ~ P {
            n=split($NF,arr,",");
            for (i=1;i<=n;i++){
                split(arr[i],kv,"=");
                if (kv[1]=="pid") {gsub(/"/,"",kv[2]); print kv[2]; exit;}
            }
        }' | head -1)
        if [ -n "$PID" ]; then echo "killing port $PORT_NUM pid=$PID"; kill -9 "$PID" 2>/dev/null || true; fi
    done
    true
    """
    run(c, kill_ports)
    # 3. 删除旧应用目录
    run(c, f"rm -rf {APP_DIR_OLD} 2>/dev/null || true", sudo=True)
    # 4. 清旧 nginx 反代站点（materials-agent），不删除静态托管所需配置
    run(c, f"rm -f /etc/nginx/sites-enabled/{NGINX_OLD} 2>/dev/null; rm -f /etc/nginx/sites-available/{NGINX_OLD} 2>/dev/null; true", sudo=True)
    # 5. 清空静态目录旧内容（保留目录本身）
    run(c, f"rm -rf {WEB_ROOT}/* 2>/dev/null || true", sudo=True)
    # 6. 状态确认
    print("\n=== 清理后状态 ===")
    run(c, "systemctl list-units --type=service --state=running --no-pager | grep -Ei 'streamlit|materials' || echo '(本项目服务已全部停止)'")
    run(c, "(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | grep -E ':80 |:8501' || echo '(80 端口待静态 nginx 接管)'")


def stage_upload(c: paramiko.SSHClient) -> None:
    print("========== UPLOAD demo-panel.html + demo-pipeline.html -> /var/www/html/ ==========")
    if not DEMO_SRC.exists():
        raise RuntimeError(f"demo 文件不存在: {DEMO_SRC}")
    pipeline_src = LOCAL_ROOT / "docs" / "demo-pipeline.html"
    if not pipeline_src.exists():
        raise RuntimeError(f"流水线演示文件不存在: {pipeline_src}")
    # /var/www/html 归 root 所有，SFTP 直写需要权限；先传 /tmp 再 sudo 拷贝
    tmp_dir = "/tmp/demo_upload"
    run(c, f"rm -rf {tmp_dir}; mkdir -p {tmp_dir}")
    # 上传为 index.html（直接访问 http://IP/ 即渲染 demo），并保留原名副本 + 流水线演示页
    files = {
        "index.html": DEMO_SRC,
        "demo-panel.html": DEMO_SRC,
        "demo-pipeline.html": pipeline_src,
    }
    for target, src in files.items():
        sftp = c.open_sftp()
        try:
            with sftp.file(f"{tmp_dir}/{target}", "wb") as f:
                with src.open("rb") as fsrc:
                    f.write(fsrc.read())
            print(f"uploaded -> {tmp_dir}/{target} ({src.stat().st_size} bytes)")
        finally:
            sftp.close()
    run(c, f"sudo mkdir -p {WEB_ROOT} && sudo cp {tmp_dir}/index.html {tmp_dir}/demo-panel.html {tmp_dir}/demo-pipeline.html {WEB_ROOT}/ && sudo chown -R ubuntu:ubuntu {WEB_ROOT} && rm -rf {tmp_dir}")
    run(c, f"ls -la {WEB_ROOT}")


NGINX_STATIC_CONF = """server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    root /var/www/html;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    location /healthz {
        access_log off;
        return 200 "ok\\n";
        add_header Content-Type text/plain;
    }
}
"""


def stage_nginx(c: paramiko.SSHClient) -> None:
    print("========== NGINX（静态托管 /var/www/html） ==========")
    _put_text(c, "/etc/nginx/sites-available/demo-static", NGINX_STATIC_CONF, sudo=True)
    run(c, "ln -sf /etc/nginx/sites-available/demo-static /etc/nginx/sites-enabled/demo-static", sudo=True)
    run(c, "rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true", sudo=True)
    run(c, "nginx -t 2>&1", sudo=True)
    run(c, "systemctl enable nginx 2>/dev/null || true", sudo=True)
    run(c, "(systemctl restart nginx 2>&1 || (nginx && sleep 2 && nginx -s reload 2>/dev/null || true)); true", sudo=True)
    time.sleep(2)
    run(c, "(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | head -12")


def stage_verify(c: paramiko.SSHClient) -> None:
    print("========== VERIFY ==========")
    run(c, "curl -sS -m 10 -o /dev/null -w 'local http80: %{http_code}\\n' http://127.0.0.1/ 2>&1 || echo 'local http80: 000'")
    run(c, "curl -sS -m 10 http://127.0.0.1/healthz 2>&1; echo")
    run(c, "curl -sS -m 10 http://127.0.0.1/ | head -c 300; echo")
    print(f"\n从本机访问公网 http://{HOST}/ ...")
    try:
        with urllib.request.urlopen(f"http://{HOST}/", timeout=25) as r:
            body = r.read(400).decode("utf-8", errors="replace")
            print("HTTP", r.status)
            print(body[:200])
    except Exception as e:
        print("公网访问未通过（请检查腾讯云安全组/防火墙是否放行 TCP 80）：", repr(e))


ACTIONS = ["cleanup", "upload", "nginx", "verify", "all"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="+", choices=ACTIONS)
    args = ap.parse_args()
    actions = list(args.action)
    if "all" in actions:
        actions = ["cleanup", "upload", "nginx", "verify"]
    c = new_client()
    try:
        dispatch = {
            "cleanup": stage_cleanup,
            "upload": stage_upload,
            "nginx": stage_nginx,
            "verify": stage_verify,
        }
        for a in actions:
            dispatch[a](c)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
