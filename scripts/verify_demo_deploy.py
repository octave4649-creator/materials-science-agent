"""验证腾讯云部署的 demo 页面（公网访问 + 截图留痕）。"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://120.53.11.211/"
OUT = Path(__file__).resolve().parents[1] / "results" / "deploy_demo_verify.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

# 本机已安装的浏览器（未装 playwright 自带 chromium，直接复用系统 Chrome）
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _find_browser() -> str:
    for p in CHROME_PATHS:
        if Path(p).exists():
            return p
    raise RuntimeError("未找到本机 Chrome/Edge 浏览器")


def main() -> int:
    exe = _find_browser()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=exe)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        print(f"goto {URL} ...")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        page.screenshot(path=str(OUT), full_page=True)
        title = page.title()
        content_len = len(page.content())
        print(f"title={title!r} content={content_len} chars")
        print(f"screenshot -> {OUT}")
        # 抓一段可读文本验证渲染
        try:
            body_text = page.inner_text("body")[:600]
            print("body (head):", body_text.replace("\n", " | "))
        except Exception as e:
            print("body text err:", e)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
