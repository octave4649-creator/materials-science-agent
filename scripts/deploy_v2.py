# ruff: noqa: E501, S106, S602, S603, S607
"""部署脚本 v2：补清旧残留 + 本地 zip 上传（绕过 GitHub TLS 问题）。

用法:
    python scripts/deploy_v2.py cleanup        # 彻底停旧服务/端口/容器
    python scripts/deploy_v2.py upload         # 打包+SFTP上传+解压
    python scripts/deploy_v2.py provision      # venv + pip install
    python scripts/deploy_v2.py serve          # systemd + nginx
    python scripts/deploy_v2.py verify         # 验证
    python scripts/deploy_v2.py all            # 按顺序执行全部
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
import time
import urllib.request
import zipfile

import paramiko

# 凭据走环境变量（禁止硬编码入库），与 deploy_demo_static.py 保持一致
HOST = os.environ.get("TENCENT_HOST", "120.53.11.211")
USER = os.environ.get("TENCENT_USER", "ubuntu")
PWD = os.environ.get("TENCENT_PWD", "")
PORT = 22

LOCAL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_DIR = "/home/ubuntu/materials-science-agent"
VENV_DIR = f"{APP_DIR}/.venv"
PIP = f"{VENV_DIR}/bin/pip"
ST = f"{VENV_DIR}/bin/streamlit"

SVC_NAME = "streamlit-materials-agent"
NGINX_NAME = "materials-agent"

EXCLUDE_PATTERNS = [
    ".git", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".venv", "venv", "node_modules", ".mypy_cache", ".idea", ".vscode",
    "data/parsed/赛道三：前沿探索AIforResearch/auto/images",
    ".trae/plan",  # 内部计划文件，不上传
]


def new_client() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        HOST, port=PORT, username=USER, password=PWD,
        timeout=30, banner_timeout=60, auth_timeout=30,
    )
    return c


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def run(c: paramiko.SSHClient, cmd: str, *, sudo: bool = False, timeout: int = 600, silent: bool = False) -> tuple[int, str, str]:
    if sudo:
        real = f"echo {_sh_quote(PWD)} | sudo -S -p '' bash -lc {_sh_quote(cmd)}"
    else:
        real = f"bash -lc {_sh_quote(cmd)}"
    _stdin, stdout, stderr = c.exec_command(real, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if not silent:
        hdr = f"===== [{code}] $ {cmd[:160]}"
        if len(cmd) > 160:
            hdr += "..."
        sys.stderr.write("\n" + hdr + "\n")
        if out:
            tail = out if len(out) < 2000 else out[-2000:]
            sys.stderr.write(tail)
            if len(out) > 2000:
                sys.stderr.write(f"\n... (truncated {len(out)} chars total)\n")
        if err.strip():
            sys.stderr.write("-- STDERR:\n")
            sys.stderr.write(err[-1000:])
            sys.stderr.write("\n")
    return code, out, err


def _put_text(c: paramiko.SSHClient, remote_path: str, content: str, *, sudo: bool = False) -> None:
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


# ---------- stages ----------

def stage_cleanup(c: paramiko.SSHClient) -> None:
    print("========== CLEANUP v2 (deep) ==========")
    # 1. 先停 systemd 中所有 jinmao-* 服务
    code, svc_list, _ = run(c, "systemctl list-units --type=service --all --no-pager --full | grep -E 'jinmao|streamlit|materials' | awk '{print $1}'")
    if svc_list.strip():
        for svc in svc_list.strip().splitlines():
            svc = svc.strip()
            if not svc:
                continue
            run(c, f"systemctl stop {svc} 2>/dev/null; systemctl disable {svc} 2>/dev/null; true", sudo=True)
    # 额外确保以下列出的每个服务都停掉
    for svc in [
        "jinmao-fitout", "jinmao-gateway", "jinmao-kb-chat",
        "jinmao-ppt", "jinmao-proposal", "jinmao-rag", "jinmao-renew",
        "streamlit-materials-agent", "streamlit", "materials-agent",
        "nginx", "docker", "containerd",
    ]:
        run(c, f"systemctl stop {svc}.service 2>/dev/null; systemctl disable {svc}.service 2>/dev/null; true", sudo=True)
    # 2. 杀残留进程（python/gunicorn/uvicorn/node/nginx/容器相关）
    kill_procs = (
        "pkill -9 -f gunicorn 2>/dev/null; "
        "pkill -9 -f uvicorn 2>/dev/null; "
        "pkill -9 -f streamlit 2>/dev/null; "
        "pkill -9 -f python 2>/dev/null; "
        "pkill -9 nginx 2>/dev/null; "
        "pkill -9 docker 2>/dev/null; "
        "pkill -9 containerd 2>/dev/null; "
        "true"
    )
    run(c, kill_procs)
    # 3. 杀占用 5000-5100 / 5700-5900 / 80 / 443 / 3000 / 8000 / 8080 / 8501 的任何进程
    kill_ports = r"""
    for PORT_NUM in 80 443 8501 3000 8000 5000 5001 5002 5003 5004 5005 5006 5007 5008 5010 5011 5721 5800 5803 8080 5173 4173; do
        PID=$(ss -ltnp 2>/dev/null | awk -v P=":$PORT_NUM " '$4 ~ P {
            n=split($NF,arr,",");
            for (i=1;i<=n;i++){
                split(arr[i],kv,"=");
                if (kv[1]=="pid") {gsub(/"/,"",kv[2]); print kv[2]; exit;}
            }
        }' | head -1)
        if [ -n "$PID" ]; then
            echo "killing port $PORT_NUM pid=$PID"
            kill -9 "$PID" 2>/dev/null || true
        fi
    done
    true
    """
    run(c, kill_ports)
    # 4. 停 docker 容器（如果有的话，需要 sudo）
    run(c, "(command -v docker >/dev/null 2>&1 && echo " + _sh_quote(PWD) + " | sudo -S docker stop $(docker ps -q 2>/dev/null) 2>/dev/null); true")
    # 5. 清旧目录（扩大范围）
    dirs = [
        "/var/www/html", "/var/www",
        "/srv/app", "/srv/www", "/srv",
        "/opt/apps", "/opt/deploy", "/opt/jinmao",
        "/home/ubuntu/jinmao",
        "/home/ubuntu/rural-teacher-assistant",
        "/home/ubuntu/projects", "/home/ubuntu/app", "/home/ubuntu/www",
        "/home/ubuntu/deploy", "/home/ubuntu/streamlit-apps",
        "/home/ubuntu/materials-science-agent",
        "/root/jinmao", "/root/apps",
    ]
    for d in dirs:
        run(c, f"rm -rf {d} 2>/dev/null || true", sudo=True)
    # 6. 清 Nginx 配置
    run(c, "rm -f /etc/nginx/sites-enabled/* 2>/dev/null; rm -f /etc/nginx/sites-available/* 2>/dev/null; rm -f /etc/nginx/conf.d/*.conf 2>/dev/null; true", sudo=True)
    run(c, "sed -Ei '/jinmao|streamlit|materials-agent|rural-teacher|proxy_pass http:\\/\\/127\\.0\\.0\\.1:(8501|3000|8000|500.)/d' /etc/nginx/nginx.conf 2>/dev/null || true", sudo=True)
    # 7. 再次确保 Nginx 已停
    run(c, "nginx -s stop 2>/dev/null; sleep 1; pkill -9 nginx 2>/dev/null; true", sudo=True)
    # 8. 查看清理后状态
    print("\n=== 清理后服务/端口检查 ===")
    run(c, "systemctl list-units --type=service --state=running --no-pager | grep -Ei 'jinmao|python|gunicorn|docker|nginx' || echo '(无匹配服务，清理成功)'")
    run(c, "(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | head -25")
    run(c, "ls -la ~ | head -30")


def _should_exclude(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/")
    for pat in EXCLUDE_PATTERNS:
        if pat in norm or norm.endswith(pat) or norm.startswith(pat):
            return True
        parts = norm.split("/")
        if pat in parts:
            return True
    return False


def _build_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(LOCAL_ROOT):
            # 过滤掉要排除的目录（避免递归进入）
            dirnames[:] = [d for d in dirnames if not _should_exclude(os.path.relpath(os.path.join(dirpath, d), LOCAL_ROOT))]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, LOCAL_ROOT)
                if _should_exclude(rel):
                    continue
                # 跳过过大的二进制文件（>50MB）
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                if size > 50 * 1024 * 1024:
                    continue
                zf.write(full, arcname=rel)
    return buf.getvalue()


def stage_upload(c: paramiko.SSHClient) -> None:
    print("========== UPLOAD (local zip -> SFTP) ==========")
    # 先清远端目标目录
    run(c, f"rm -rf {APP_DIR}; mkdir -p {APP_DIR}")
    # 打包 zip
    sys.stderr.write("Building zip...\n")
    zip_bytes = _build_zip_bytes()
    sys.stderr.write(f"Zip size: {len(zip_bytes)/1024/1024:.2f} MB\n")
    # SFTP 上传
    remote_zip = "/tmp/materials-science-agent.zip"
    sftp = c.open_sftp()
    try:
        with sftp.file(remote_zip, "wb") as f:
            # 分块写入
            chunk = 1024 * 1024
            total = len(zip_bytes)
            sent = 0
            view = memoryview(zip_bytes)
            while sent < total:
                nxt = min(sent + chunk, total)
                f.write(bytes(view[sent:nxt]))
                sent = nxt
                pct = sent * 100 // total
                sys.stderr.write(f"\rUploading: {pct}% ({sent//1024}KB/{total//1024}KB)")
                sys.stderr.flush()
        sys.stderr.write("\nUpload done.\n")
    finally:
        sftp.close()
    # 远端解压
    run(c, f"cd /tmp && unzip -q -o {remote_zip} -d {APP_DIR} && ls -la {APP_DIR} | head -30")
    run(c, f"rm -f {remote_zip}")


def stage_provision(c: paramiko.SSHClient) -> None:
    print("========== PROVISION (venv + pip) ==========")
    # 确保基础环境已安装（apt-get update 刚跑过但再确认一次）
    run(c, "DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip nginx git curl build-essential ca-certificates unzip 2>&1 | tail -10", sudo=True, timeout=600)
    # 创建 venv
    run(c, f"cd {APP_DIR} && python3 -m venv .venv && {PIP} install --upgrade pip setuptools wheel 2>&1 | tail -10", timeout=300)
    # 装依赖：基础 + streamlit + 搜索/验证相关
    deps = (
        "httpx pydantic python-dotenv 'ruff>=0.5' 'pytest>=8.0' pytest-asyncio "
        "scikit-learn pymoo deap streamlit pandas numpy tabulate"
    )
    run(c, f"cd {APP_DIR} && {PIP} install {deps} 2>&1 | tail -20", timeout=2400)
    run(c, f"{ST} --version")
    # 简单启动一下看看有没有 ImportError
    code, out, _ = run(c, f"cd {APP_DIR} && {ST} --version 2>&1; echo '--- try import ---'; {VENV_DIR}/bin/python -c 'import streamlit, json, pathlib, sys; sys.path.insert(0, {_sh_quote(APP_DIR)}); print(\"import ok\")'")


SERVICE_FILE = f"""[Unit]
Description=Streamlit Materials Science Agent Demo
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory={APP_DIR}
Environment="PATH={VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart={ST} run app.py \\
    --server.headless true \\
    --server.address 127.0.0.1 \\
    --server.port 8501 \\
    --server.enableCORS false \\
    --server.enableXsrfProtection false \\
    --browser.serverAddress {HOST} \\
    --server.maxUploadSize 200 \\
    --server.fileWatcherType none
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

NGINX_CONF = f"""server {{
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name {HOST} _;

    client_max_body_size 200M;

    location / {{
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_buffering off;
    }}

    location ^~ /static/ {{
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        expires 30d;
        access_log off;
    }}

    location /healthz {{
        access_log off;
        return 200 "ok\\n";
        add_header Content-Type text/plain;
    }}
}}
"""


def stage_systemd(c: paramiko.SSHClient) -> None:
    print("========== SYSTEMD ==========")
    # 先清旧 unit
    run(c, f"systemctl stop {SVC_NAME}.service 2>/dev/null || true", sudo=True)
    _put_text(c, f"/etc/systemd/system/{SVC_NAME}.service", SERVICE_FILE, sudo=True)
    run(c, "systemctl daemon-reload", sudo=True)
    run(c, f"systemctl enable {SVC_NAME}.service", sudo=True)
    run(c, f"systemctl restart {SVC_NAME}.service", sudo=True)
    time.sleep(6)
    run(c, f"systemctl status {SVC_NAME}.service --no-pager | head -40", sudo=True)
    run(c, f"journalctl -u {SVC_NAME}.service --no-pager -n 120", sudo=True)
    # 本地 8501 探活
    for _i in range(20):
        code, out, _ = run(c, "curl -sS -m 5 http://127.0.0.1:8501 -o /dev/null -w '%{http_code}\\n' 2>&1 || echo 000")
        if "200" in out:
            print("STREAMLIT OK:", out.strip())
            return
        print(f"probe {_i+1}: {out.strip()}")
        time.sleep(3)
    print("WARN: streamlit 本地 8501 未返回 200")


def stage_nginx(c: paramiko.SSHClient) -> None:
    print("========== NGINX ==========")
    _put_text(c, f"/etc/nginx/sites-available/{NGINX_NAME}", NGINX_CONF, sudo=True)
    run(c, f"ln -sf /etc/nginx/sites-available/{NGINX_NAME} /etc/nginx/sites-enabled/{NGINX_NAME}", sudo=True)
    run(c, "rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true", sudo=True)
    # Nginx 可能没装 default，再次确保 /etc/nginx 目录存在
    run(c, "nginx -v 2>&1; echo '--- sites dirs ---'; ls -la /etc/nginx/sites-available /etc/nginx/sites-enabled 2>&1 | head -20")
    code, out, err = run(c, "nginx -t 2>&1", sudo=True)
    if code != 0:
        print("nginx -t failed, 检查 /etc/nginx/nginx.conf default_server 冲突...")
        # Ubuntu 默认 nginx.conf 会 include sites-enabled/*，但如果 sites-available/default
        # 或其他配置也 listen 80 default_server 就冲突。我们已经 rm -f sites-enabled/* 了。
        # 但若 /etc/nginx/nginx.conf 自身或 conf.d 里有 default_server，也会冲突。查一下：
        run(c, "grep -Rrn 'default_server' /etc/nginx/ 2>&1 | head -20")
    run(c, "systemctl enable nginx 2>/dev/null || true", sudo=True)
    run(c, "(systemctl restart nginx 2>&1 || (nginx && sleep 2 && nginx -s reload 2>/dev/null || true)); true", sudo=True)
    time.sleep(2)
    run(c, "(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | head -20")


def stage_verify(c: paramiko.SSHClient) -> None:
    print("========== VERIFY ==========")
    run(c, (
        "for i in 1 2 3 4 5 6 7 8 9 10 11 12; do "
        "s=$(curl -sS -m 10 -o /tmp/home.html -w '%{http_code}' http://127.0.0.1/ 2>/dev/null || echo 000); "
        "echo try-$i: $s; [ \"$s\" = \"200\" ] && break; sleep 2; done; "
        "echo '--home.html (head 800):'; head -c 800 /tmp/home.html 2>/dev/null; echo"
    ))
    run(c, "curl -sS -m 10 http://127.0.0.1/healthz 2>&1; echo")
    print(f"\n本机访问公网 http://{HOST}/ ...")
    try:
        with urllib.request.urlopen(f"http://{HOST}/", timeout=25) as r:
            body = r.read(800).decode("utf-8", errors="replace")
            print("HTTP", r.status)
            print(body[:400])
    except Exception as e:
        print("公网访问未通过（请检查腾讯云安全组/防火墙是否放行 TCP 80）：", repr(e))


ACTIONS = ["cleanup", "upload", "provision", "systemd", "nginx", "serve", "verify", "all"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="+", choices=ACTIONS)
    args = ap.parse_args()
    actions = list(args.action)
    if "all" in actions:
        actions = ["cleanup", "upload", "provision", "systemd", "nginx", "verify"]
    elif "serve" in actions:
        # serve 是 systemd + nginx 的别名
        actions = [a for a in actions if a != "serve"]
        actions.extend(["systemd", "nginx"])

    c = new_client()
    try:
        dispatch = {
            "cleanup": stage_cleanup,
            "upload": stage_upload,
            "provision": stage_provision,
            "systemd": stage_systemd,
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
