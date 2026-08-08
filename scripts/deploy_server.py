# ruff: noqa: E501, S106, S602, S607, S603
"""远程服务器部署脚本（腾讯云 Lighthouse ubuntu@120.53.11.211）。

用法:
    python scripts/deploy_server.py snapshot
    python scripts/deploy_server.py cleanup
    python scripts/deploy_server.py all

阶段：
  snapshot   现状快照
  cleanup    停旧进程 + 清空旧项目目录 + 旧 nginx 站点
  install    apt-get python3/venv/nginx/git
  upload     git clone 项目 + 创建 venv + pip 安装依赖（含 streamlit）
  systemd    写入 systemd unit 并启动 Streamlit（127.0.0.1:8501）
  nginx      写入 /etc/nginx/sites-available/materials-agent 反代 80
  verify     本机/公网 HTTP 验证
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request

import paramiko

# 凭据走环境变量（禁止硬编码入库），与 deploy_demo_static.py 保持一致
HOST = os.environ.get("TENCENT_HOST", "120.53.11.211")
USER = os.environ.get("TENCENT_USER", "ubuntu")
PWD = os.environ.get("TENCENT_PWD", "")
PORT = 22

REPO_URL = "https://github.com/octave4649-creator/materials-science-agent.git"
APP_DIR = "/home/ubuntu/materials-science-agent"
VENV_DIR = f"{APP_DIR}/.venv"
PIP = f"{VENV_DIR}/bin/pip"
ST = f"{VENV_DIR}/bin/streamlit"

SVC_NAME = "streamlit-materials-agent"
NGINX_NAME = "materials-agent"


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
            tail = out if len(out) < 3000 else out[-3000:]
            sys.stderr.write(tail)
            if len(out) > 3000:
                sys.stderr.write(f"\n... (truncated {len(out)} chars total)\n")
        if err.strip():
            sys.stderr.write("-- STDERR:\n")
            sys.stderr.write(err[-1500:])
            sys.stderr.write("\n")
    return code, out, err


# ---------- stages ----------

def stage_snapshot(c: paramiko.SSHClient) -> None:
    print("========== SNAPSHOT ==========")
    cmds: list[tuple[str, str]] = [
        ("uname/os", "uname -a; echo '---os-release---'; cat /etc/os-release 2>/dev/null | head -10"),
        ("df/mem", "df -h /; echo '---'; free -h"),
        ("python", "which python3; python3 --version 2>&1"),
        ("nginx", "which nginx 2>/dev/null; nginx -v 2>&1; echo '---sites-enabled:'; ls -la /etc/nginx/sites-enabled 2>/dev/null; echo '---sites-available:'; ls -la /etc/nginx/sites-available 2>/dev/null"),
        ("systemd running units", "systemctl list-units --type=service --state=running --no-pager | head -40"),
        ("pm2", "(command -v pm2 >/dev/null 2>&1 && pm2 list 2>&1 | head -30) || echo 'pm2 not found'"),
        ("ports", "(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | head -30"),
        ("ps top-mem", "ps aux --sort=-%mem | head -30"),
        ("home contents", "ls -la ~ 2>/dev/null | head -40"),
        ("srv/var/www/opt", "echo '--- /srv ---'; ls -la /srv 2>/dev/null; echo '--- /var/www ---'; ls -la /var/www 2>/dev/null; echo '--- /opt ---'; ls -la /opt 2>/dev/null | head -20"),
        ("crontab", "(crontab -l 2>&1 || echo 'no crontab') | head -30"),
    ]
    for name, cmd in cmds:
        sys.stderr.write(f"\n----- {name} -----\n")
        run(c, cmd)


def stage_cleanup(c: paramiko.SSHClient) -> None:
    print("========== CLEANUP ==========")
    # 停常见名字的 systemd 服务
    for svc in [
        "streamlit-materials-agent", "streamlit",
        "rural-teacher-assistant", "materials-agent",
        "node-app", "next-app", "python-app", "uvicorn", "gunicorn",
    ]:
        run(c, f"systemctl stop {svc}.service 2>/dev/null; systemctl disable {svc}.service 2>/dev/null; true", sudo=True)
    # PM2
    run(c, "(command -v pm2 >/dev/null 2>&1 && (pm2 delete all 2>/dev/null || true); true)")
    run(c, "(command -v pm2 >/dev/null 2>&1 && (pm2 kill 2>/dev/null || true); true)")
    # Docker
    run(c, "(command -v docker >/dev/null 2>&1 && (docker stop $(docker ps -q) 2>/dev/null || true); true)")
    # 杀占用常见端口的进程
    kill_ports = r"""
    for PORT_NUM in 80 443 8501 3000 8000 5000 8080 5173 4173; do
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
    # 清旧项目目录
    dirs = [
        "/var/www/html",
        "/var/www/rural-teacher-assistant",
        "/srv/app", "/srv/www",
        "/opt/apps", "/opt/deploy",
        "/home/ubuntu/rural-teacher-assistant",
        "/home/ubuntu/projects", "/home/ubuntu/app", "/home/ubuntu/www",
        "/home/ubuntu/deploy", "/home/ubuntu/streamlit-apps",
        "/home/ubuntu/materials-science-agent",
    ]
    for d in dirs:
        run(c, f"rm -rf {d} 2>/dev/null || true", sudo=True)
    # Nginx 站点
    run(c, "rm -f /etc/nginx/sites-enabled/* 2>/dev/null; rm -f /etc/nginx/sites-available/* 2>/dev/null; rm -f /etc/nginx/conf.d/*.conf 2>/dev/null; true", sudo=True)
    run(c, "sed -Ei '/streamlit|materials-agent|rural-teacher|proxy_pass http:\\/\\/127\\.0\\.0\\.1:(8501|3000|8000)/d' /etc/nginx/nginx.conf 2>/dev/null || true", sudo=True)
    # 彻底停 nginx 再启（后面 nginx 阶段再配）
    run(c, "nginx -s stop 2>/dev/null; sleep 1; pkill -9 nginx 2>/dev/null; true", sudo=True)


def stage_install(c: paramiko.SSHClient) -> None:
    print("========== INSTALL ==========")
    run(c, "apt-get update -y 2>&1 | tail -15", sudo=True, timeout=300)
    run(c, (
        "DEBIAN_FRONTEND=noninteractive apt-get install -y "
        "python3 python3-venv python3-pip nginx git curl build-essential ca-certificates "
        "2>&1 | tail -20"
    ), sudo=True, timeout=900)
    run(c, "which python3; python3 --version")
    code, out, _ = run(c, "python3 -c 'import sys; print(sys.version_info >= (3,10))'")
    if "True" not in out:
        raise RuntimeError(f"Python 3.10+ not ready: {out!r}")


def stage_upload(c: paramiko.SSHClient) -> None:
    print("========== UPLOAD ==========")
    run(c, f"rm -rf {APP_DIR}; git clone --depth 1 {REPO_URL} {APP_DIR}", timeout=300)
    run(c, f"ls -la {APP_DIR} | head -30")
    run(c, f"cd {APP_DIR} && python3 -m venv .venv && {PIP} install --upgrade pip setuptools wheel 2>&1 | tail -10", timeout=300)
    deps = (
        "sciverse httpx pydantic python-dotenv 'ruff>=0.5' 'pytest>=8.0' pytest-asyncio "
        "scikit-learn pymoo deap streamlit"
    )
    run(c, f"cd {APP_DIR} && {PIP} install {deps} 2>&1 | tail -20", timeout=1800)
    run(c, f"{ST} --version")


SERVICE_FILE = f"""[Unit]
Description=Streamlit Materials Science Agent Demo
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory={APP_DIR}
Environment="PATH={VENV_DIR}/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart={ST} run app.py \\
    --server.headless true \\
    --server.address 127.0.0.1 \\
    --server.port 8501 \\
    --server.enableCORS false \\
    --server.enableXsrfProtection false \\
    --browser.serverAddress {HOST} \\
    --server.maxUploadSize 200
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


def stage_systemd(c: paramiko.SSHClient) -> None:
    print("========== SYSTEMD ==========")
    _put_text(c, f"/etc/systemd/system/{SVC_NAME}.service", SERVICE_FILE, sudo=True)
    run(c, "systemctl daemon-reload", sudo=True)
    run(c, f"systemctl enable {SVC_NAME}.service", sudo=True)
    run(c, f"systemctl restart {SVC_NAME}.service", sudo=True)
    time.sleep(5)
    run(c, f"systemctl status {SVC_NAME}.service --no-pager | head -30", sudo=True)
    run(c, f"journalctl -u {SVC_NAME}.service --no-pager -n 80", sudo=True)
    for _i in range(12):
        code, out, _ = run(c, "curl -sS -m 5 http://127.0.0.1:8501 -o /dev/null -w '%{http_code}\\n' 2>&1 || echo 000")
        if "200" in out:
            print("STREAMLIT OK:", out.strip())
            break
        time.sleep(3)
    else:
        print("WARN: streamlit 本地 8501 未返回 200，继续 nginx")


def stage_nginx(c: paramiko.SSHClient) -> None:
    print("========== NGINX ==========")
    _put_text(c, f"/etc/nginx/sites-available/{NGINX_NAME}", NGINX_CONF, sudo=True)
    run(c, f"ln -sf /etc/nginx/sites-available/{NGINX_NAME} /etc/nginx/sites-enabled/{NGINX_NAME}", sudo=True)
    run(c, "rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true", sudo=True)
    run(c, "nginx -t 2>&1", sudo=True)
    run(c, "systemctl enable nginx 2>/dev/null || true", sudo=True)
    run(c, "(systemctl restart nginx 2>&1 || (nginx && sleep 2 && nginx -s reload 2>/dev/null || true)); true", sudo=True)
    run(c, "(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | head -20")


def stage_verify(c: paramiko.SSHClient) -> None:
    print("========== VERIFY ==========")
    run(c, (
        "for i in 1 2 3 4 5 6 7 8 9 10; do "
        "s=$(curl -sS -m 10 -o /tmp/home.html -w '%{http_code}' http://127.0.0.1/ 2>/dev/null || echo 000); "
        "echo try-$i: $s; [ \"$s\" = \"200\" ] && break; sleep 2; done; "
        "echo '--home.html (head 600):'; head -c 600 /tmp/home.html 2>/dev/null; echo"
    ))
    run(c, "curl -sS -m 10 http://127.0.0.1/healthz 2>&1; echo")
    print("\n从本机访问公网：")
    try:
        with urllib.request.urlopen(f"http://{HOST}/", timeout=25) as r:
            body = r.read(800).decode("utf-8", errors="replace")
            print("HTTP", r.status)
            print(body)
    except Exception as e:
        print("公网访问未通过（请检查腾讯云安全组 / 防火墙是否放行 TCP 80）：", repr(e))


ACTIONS = ["snapshot", "cleanup", "install", "upload", "systemd", "nginx", "verify", "all"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="+", choices=ACTIONS)
    args = ap.parse_args()
    actions = list(args.action)
    if "all" in actions:
        actions = ["snapshot", "cleanup", "install", "upload", "systemd", "nginx", "verify"]

    c = new_client()
    try:
        dispatch = {
            "snapshot": stage_snapshot,
            "cleanup": stage_cleanup,
            "install": stage_install,
            "upload": stage_upload,
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
