"""验证远程服务器部署 UI：打开公网地址并截图保存到 results/deploy_verify.png"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://120.53.11.211/"
OUT = Path(__file__).resolve().parents[1] / "results" / "deploy_verify.png"
OUT.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        print(f"goto {URL} ...")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        # 等 streamlit 渲染
        try:
            page.wait_for_selector('[data-testid="stTabs"]', timeout=60000)
        except Exception as e:
            print("wait stTabs timeout, continuing anyway:", e)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT), full_page=True)
        content_len = len(page.content())
        title = page.title()
        print(f"title={title!r} content={content_len} chars")
        print(f"screenshot -> {OUT}")
        # 尝试抓一段可读文本
        try:
            body_text = page.inner_text("body")[:800]
            print("body (head):", body_text.replace("\n", " | "))
        except Exception as e:
            print("body text err:", e)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
