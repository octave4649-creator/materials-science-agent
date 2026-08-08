"""公网验证腾讯云 demo-pipeline.html（六阶段流水线演示页 + 截图留痕）。"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://120.53.11.211/demo-pipeline.html"
OUT = Path(__file__).resolve().parents[1] / "results" / "deploy_pipeline_verify.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

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
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=exe)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        print(f"goto {URL} ...")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        assert page.locator("#flowbar button").count() == 6, "flowbar 应有 6 个步骤"
        steps = ["检索 Agent", "抽取 Agent", "Gap 识别", "搜索算法 × LLM", "OQMD/MP 验证", "证据链审计"]
        for i, name in enumerate(steps):
            page.locator("#flowbar button", has_text=name).click()
            page.wait_for_timeout(150)
            ind = page.inner_text("#ind").strip()
            assert ind == f"{i + 1} / 6", f"{name} 应显示 {i + 1} / 6，实际 {ind}"
            print(f"step {i + 1} [{name}] ok")
        page.screenshot(path=str(OUT), full_page=True)
        print(f"screenshot -> {OUT}")

        real_errors = [e for e in errors if "favicon" not in e]
        print(f"console errors = {len(real_errors)}")
        for e in real_errors:
            print("  ", e)
        browser.close()

    if real_errors:
        print("发现 JS 错误")
        return 1
    print("公网流水线演示页验证通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
