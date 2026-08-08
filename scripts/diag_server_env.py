"""探测腾讯云服务器环境：Python/依赖/网络可达性（为真实流水线部署做可行性判断）。"""
from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("TENCENT_HOST", "120.53.11.211")
USER = os.environ.get("TENCENT_USER", "ubuntu")
PWD = os.environ.get("TENCENT_PWD", "")


def main() -> int:
    if not PWD:
        print("缺少 TENCENT_PWD 环境变量")
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=22, username=USER, password=PWD, timeout=30)
    cmds = [
        "python3 --version; which python3; python3 -c 'import sys; print(sys.executable)'",
        "pip3 --version 2>/dev/null || pip --version 2>/dev/null || echo no-pip",
        "free -h | head -2; df -h / | tail -1; nproc",
        # 网络可达性探测（5s 超时）
        "curl -sS -m 6 -o /dev/null -w 'sciverse: %{http_code}\\n' https://api.sciverse.space 2>&1 || echo 'sciverse: FAIL'",
        "curl -sS -m 6 -o /dev/null -w 'oqmd: %{http_code}\\n' https://oqmd.org 2>&1 || echo 'oqmd: FAIL'",
        "curl -sS -m 6 -o /dev/null -w 'mp: %{http_code}\\n' https://api.materialsproject.org 2>&1 || echo 'mp: FAIL'",
        "curl -sS -m 6 -o /dev/null -w 'deepseek: %{http_code}\\n' https://api.deepseek.com 2>&1 || echo 'deepseek: FAIL'",
        # 已装相关包
        "python3 -c 'import sciverse' 2>&1 | head -1; python3 -c 'import langgraph' 2>&1 | head -1; python3 -c 'import fastapi' 2>&1 | head -1",
        # 环境变量是否有 key（只显示是否存在，不泄露值）
        "env | grep -E '^(SCIVERSE|DEEPSEEK|MP_API|LLM_API)' | cut -d= -f1 || echo 'no keys in env'",
    ]
    for cmd in cmds:
        _in, out, err = c.exec_command(cmd, timeout=60)
        o = out.read().decode("utf-8", errors="replace")
        e = err.read().decode("utf-8", errors="replace")
        print(f"===== $ {cmd}")
        if o.strip():
            print(o.strip())
        if e.strip():
            print("STDERR:", e.strip()[:500])
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
