"""腾讯云真实在线流水线部署脚本（FastAPI 后端 + 静态页面）。

将可运行的六阶段流水线（run_live_api.py + 训练好的资产：Sci-Base BM25 索引 +
oracle 真值表）部署到腾讯云 Lighthouse：
- 后端 uvicorn 监听 127.0.0.1:8000（/api/run、/api/jobs/...）
- nginx 80 端口静态托管 demo-live.html，并反代 /api 到后端
- .env 配置在线凭据（SCIVERSE_API_TOKEN / DEEPSEEK_API_KEY / MP_API_KEY），
  从本机环境变量与凭据文件安全读取，仅写入服务器 .env（不入库）

凭据从环境变量读取（禁止硬编码入库）：
    TENCENT_HOST（默认 120.53.11.211）/ TENCENT_USER（默认 ubuntu）/ TENCENT_PWD（必填）

用法:
    python scripts/deploy_live_backend.py upload      # 上传源码 + 训练好的资产 + 页面
    python scripts/deploy_live_backend.py deps        # 安装依赖（fastapi/uvicorn/sciverse）
    python scripts/deploy_live_backend.py env         # 写 .env（读取本机凭据）
    python scripts/deploy_live_backend.py service     # 启动/重启 uvicorn 服务
    python scripts/deploy_live_backend.py nginx       # 配置 nginx /api 反代 + 静态托管
    python scripts/deploy_live_backend.py verify      # 验证（本地 + 公网）
    python scripts/deploy_live_backend.py all         # 全部按序执行
"""
# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
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
APP_DIR = "/home/ubuntu/materials-live"   # 后端运行目录
VENV_DIR = f"{APP_DIR}/venv"
WEB_ROOT = "/var/www/html"
SVC = "materials-live"

# 需要上传的源码目录（排除 __pycache__ 等）
SRC_DIRS = ["src", "scripts", "data/cache/scibase", "results/oracle"]
# 数据资产（训练好的模型/真值表）
INDEX_SRC = LOCAL_ROOT / "data" / "cache" / "scibase" / "scibase_index.json"
ORACLE_GLOB = LOCAL_ROOT / "results" / "oracle" / "oracle_truth_*.json"
LIVE_PAGE = LOCAL_ROOT / "docs" / "demo-live.html"
PANEL_PAGE = LOCAL_ROOT / "docs" / "demo-panel.html"
PIPELINE_PAGE = LOCAL_ROOT / "docs" / "demo-pipeline.html"


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


def _put_file(c: paramiko.SSHClient, local: Path, remote_dir: str) -> None:
    """上传单个文件到远程目录（先 /tmp 再 mv，避免权限问题）。"""
    import hashlib
    tmp = f"/tmp/_deploy_{hashlib.md5(str(local).encode()).hexdigest()}"
    sftp = c.open_sftp()
    try:
        with sftp.file(tmp, "wb") as f:
            with local.open("rb") as fsrc:
                f.write(fsrc.read())
        print(f"  uploaded {local.name} -> {remote_dir}/")
    finally:
        sftp.close()
    run(c, f"mkdir -p {remote_dir} && mv {tmp} {remote_dir}/{local.name}")


def _upload_tree(c: paramiko.SSHClient, local_dir: Path, remote_dir: str) -> None:
    """递归上传目录（跳过 __pycache__ / .pyc）。"""
    sftp = c.open_sftp()
    try:
        for p in sorted(local_dir.rglob("*")):
            if p.is_dir():
                if p.name == "__pycache__":
                    continue
                continue
            if p.suffix == ".pyc":
                continue
            rel = p.relative_to(local_dir)
            rp = f"{remote_dir}/{rel.as_posix()}"
            rdir = rp.rsplit("/", 1)[0]
            try:
                sftp.stat(rdir)
            except FileNotFoundError:
                sftp.mkdir(rdir)
            try:
                sftp.stat(rp)
            except FileNotFoundError:
                with sftp.file(rp, "wb") as f:
                    with p.open("rb") as fsrc:
                        f.write(fsrc.read())
                print(f"  up {rel.as_posix()}")
    finally:
        sftp.close()


# ---------- 各阶段 ----------


def stage_upload(c: paramiko.SSHClient) -> None:
    print("========== UPLOAD 源码 + 训练好的资产 + 页面 ==========")
    # 只清理源码/资产/入口（保留 venv 与 .env，避免每次 upload 都要重装依赖）
    run(c, (
        f"mkdir -p {APP_DIR} && "
        f"rm -rf {APP_DIR}/src {APP_DIR}/data {APP_DIR}/results {APP_DIR}/scripts "
        f"{APP_DIR}/run_live_api.py {APP_DIR}/*.pyc && "
        f"mkdir -p {APP_DIR}/src {APP_DIR}/results/oracle {APP_DIR}/data/cache"
    ))
    # 源码目录
    _upload_tree(c, LOCAL_ROOT / "src", f"{APP_DIR}/src")
    # 后端入口放应用根目录（uvicorn 从工作目录 import，需与 src 同级）
    _put_file(c, LOCAL_ROOT / "scripts" / "run_live_api.py", APP_DIR)
    # 数据资产
    _put_file(c, INDEX_SRC, f"{APP_DIR}/data/cache/scibase")
    for f in sorted(ORACLE_GLOB.parent.glob(ORACLE_GLOB.name)):
        _put_file(c, f, f"{APP_DIR}/results/oracle")
    # 静态页面
    for src in (LIVE_PAGE, PANEL_PAGE, PIPELINE_PAGE):
        _put_file(c, src, "/tmp/live_pages")
    run(c, f"sudo mkdir -p {WEB_ROOT} && sudo cp /tmp/live_pages/*.html {WEB_ROOT}/ && sudo chown -R ubuntu:ubuntu {WEB_ROOT} && rm -rf /tmp/live_pages")
    # 同步首页别名：用最新的 demo-panel.html 覆盖 index.html
    run(c, f"sudo cp {WEB_ROOT}/demo-panel.html {WEB_ROOT}/index.html", silent=True)
    run(c, f"ls -la {WEB_ROOT} && echo '---' && ls -la {APP_DIR}/src {APP_DIR}/results/oracle {APP_DIR}/data/cache/scibase")


def stage_deps(c: paramiko.SSHClient) -> None:
    print("========== DEPS 安装依赖（venv） ==========")
    run(c, f"cd {APP_DIR} && python3 -m venv venv")
    run(c, (
        f"cd {APP_DIR} && venv/bin/pip install --quiet --upgrade pip && "
        "venv/bin/pip install --quiet fastapi 'uvicorn[standard]' httpx pydantic python-dotenv sciverse"
    ), timeout=600)
    run(c, f"cd {APP_DIR} && venv/bin/python -c 'import fastapi, uvicorn, httpx, pydantic; print(\"deps ok\")'")


def _read_env_map() -> dict[str, str]:
    """读取本机凭据 → 服务器 .env 内容（只读不打印值）。"""
    env: dict[str, str] = {}
    # Sciverse token：环境变量或 CLI 凭据文件
    tok = os.getenv("SCIVERSE_API_TOKEN") or os.getenv("SCIVERSE_API_KEY")
    if not tok:
        creds = Path.home() / ".sciverse" / "credentials.json"
        try:
            tok = json.loads(creds.read_text(encoding="utf-8")).get("token")
        except (OSError, json.JSONDecodeError):
            tok = None
    if tok:
        env["SCIVERSE_API_TOKEN"] = tok
    # LLM / MP 凭据（本机环境变量）
    for key in ("DEEPSEEK_API_KEY", "MP_API_KEY"):
        v = os.getenv(key)
        if v:
            env[key] = v
    # 允许 LLM_BASE_URL / LLM_MODEL 覆盖
    for key in ("LLM_BASE_URL", "LLM_MODEL"):
        v = os.getenv(key)
        if v:
            env[key] = v
    return env


def stage_env(c: paramiko.SSHClient) -> None:
    print("========== ENV 写 .env（凭据仅写入服务器，不回显） ==========")
    env = _read_env_map()
    if not env:
        raise RuntimeError("本机未读取到任何凭据（SCIVERSE / DEEPSEEK / MP），无法配置在线能力")
    lines = "\n".join(f"{k}={v}" for k, v in env.items()) + "\n"
    _put_text(c, f"{APP_DIR}/.env", lines)
    run(c, f"chmod 0600 {APP_DIR}/.env")
    run(c, f"echo '已写入 keys:' && grep -oE '^[A-Z_]+=' {APP_DIR}/.env")


SERVICE_UNIT = """[Unit]
Description=Materials Science Live Pipeline (FastAPI)
After=network.target

[Service]
User=ubuntu
WorkingDirectory={app}
ExecStart={app}/venv/bin/uvicorn run_live_api:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
Environment=PYTHONPATH={app}

[Install]
WantedBy=multi-user.target
"""


def stage_service(c: paramiko.SSHClient) -> None:
    print("========== SERVICE 启动 uvicorn 服务 ==========")
    _put_text(c, f"/etc/systemd/system/{SVC}.service",
              SERVICE_UNIT.format(app=APP_DIR), sudo=True)
    run(c, (
        f"systemctl daemon-reload && systemctl enable {SVC} && "
        f"systemctl restart {SVC} && sleep 3 && "
        f"systemctl is-active {SVC} && "
        "(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | grep ':8000' || echo '(8000 未监听)'; "
        "curl -sS -m 5 http://127.0.0.1:8000/api/health; echo"
    ), sudo=True)


NGINX_LIVE_CONF = """server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    root /var/www/html;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

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
    print("========== NGINX 静态托管 + /api 反代 ==========")
    _put_text(c, "/etc/nginx/sites-available/demo-static", NGINX_LIVE_CONF, sudo=True)
    run(c, "ln -sf /etc/nginx/sites-available/demo-static /etc/nginx/sites-enabled/demo-static", sudo=True)
    run(c, "rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true", sudo=True)
    run(c, "nginx -t 2>&1", sudo=True)
    run(c, "(systemctl restart nginx 2>&1 || (nginx && sleep 2 && nginx -s reload 2>/dev/null || true)); true", sudo=True)
    time.sleep(2)
    run(c, "(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | grep -E ':80 |:8000' | head -5")


def stage_verify(c: paramiko.SSHClient) -> None:
    print("========== VERIFY ==========")
    run(c, "curl -sS -m 10 http://127.0.0.1:8000/api/health; echo")
    run(c, "curl -sS -m 10 http://127.0.0.1/api/health; echo")
    run(c, "curl -sS -m 10 -o /dev/null -w 'demo-live: %{http_code}\\n' http://127.0.0.1/demo-live.html")
    print(f"\n从本机访问公网 http://{HOST}/api/health ...")
    try:
        with urllib.request.urlopen(f"http://{HOST}/api/health", timeout=25) as r:
            body = r.read(300).decode("utf-8", errors="replace")
            print("HTTP", r.status)
            print(body[:250])
    except Exception as e:
        print("公网 API 未通过（请检查安全组放行 TCP 80）：", repr(e))


ACTIONS = ["upload", "deps", "env", "service", "nginx", "verify", "all"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="+", choices=ACTIONS)
    args = ap.parse_args()
    actions = list(args.action)
    if "all" in actions:
        actions = ["upload", "deps", "env", "service", "nginx", "verify"]
    c = new_client()
    try:
        dispatch = {
            "upload": stage_upload,
            "deps": stage_deps,
            "env": stage_env,
            "service": stage_service,
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
