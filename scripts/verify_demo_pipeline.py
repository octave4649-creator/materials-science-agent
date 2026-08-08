"""本地验证 docs/demo-pipeline.html 六阶段流水线演示页（交互 + 截图留痕）。"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = (ROOT / "docs" / "demo-pipeline.html").as_uri()
OUT = ROOT / "results" / "demo_pipeline_verify.png"
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
        page.wait_for_timeout(1500)

        # 1. 初始状态：6 个步骤按钮 + 步骤1 激活
        n_flow = page.locator("#flowbar button").count()
        print(f"flowbar steps = {n_flow}")
        assert n_flow == 6, "flowbar 应有 6 个步骤按钮"
        assert "1 / 6" in page.inner_text("#ind"), "初始指示应为 1 / 6"
        assert page.locator("#flowbar button.active").inner_text().strip().startswith("1"), "步骤1 应激活"

        # 2. 逐步骤点击导航
        steps = ["检索 Agent", "抽取 Agent", "Gap 识别", "搜索算法 × LLM", "OQMD/MP 验证", "证据链审计"]
        for i, name in enumerate(steps):
            page.locator("#flowbar button", has_text=name).click()
            page.wait_for_timeout(200)
            ind = page.inner_text("#ind").strip()
            assert ind == f"{i + 1} / 6", f"点击 {name} 后指示应为 {i + 1} / 6，实际 {ind}"
            body = page.inner_text("#stage")
            assert len(body) > 200, f"步骤 {name} 内容过短"
            print(f"step {i + 1} [{name}] ok ({len(body)} chars)")

        # 3. 上一步/下一步按钮
        page.locator("#btn-next").click()
        page.wait_for_timeout(200)
        assert page.inner_text("#ind").strip() == "1 / 6", "步骤6 后点下一步应回到步骤1"
        page.locator("#btn-prev").click()
        page.wait_for_timeout(200)
        assert page.inner_text("#ind").strip() == "6 / 6", "步骤1 后点上一步应回到步骤6"

        # 4. 自动播放开关
        page.locator("#btn-auto").click()
        page.wait_for_timeout(200)
        assert "暂停" in page.inner_text("#btn-auto"), "自动播放开启后按钮应显示暂停"
        page.locator("#btn-auto").click()
        page.wait_for_timeout(200)
        assert "自动播放" in page.inner_text("#btn-auto"), "暂停后按钮应恢复"

        # 5. 键盘左右键（先直接点步骤1 按钮回到起点）
        page.locator("#flowbar button", has_text="检索 Agent").click()
        page.wait_for_timeout(200)
        assert page.inner_text("#ind").strip() == "1 / 6", "应回到步骤1"
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(200)
        assert page.inner_text("#ind").strip() == "2 / 6", "右键应前进到步骤2"
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(200)
        assert page.inner_text("#ind").strip() == "1 / 6", "左键应后退到步骤1"

        # 6. 截图（停在步骤4 搜索×LLM，最有代表性）
        page.locator("#flowbar button", has_text="搜索算法 × LLM").click()
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT), full_page=True)
        print(f"screenshot -> {OUT}")

        # 7. 检查 JS 错误
        real_errors = [e for e in errors if "favicon" not in e]
        print(f"console errors = {len(real_errors)}")
        for e in real_errors:
            print("  ", e)
        browser.close()

    if real_errors:
        print("发现 JS 错误，验证不通过")
        return 1
    print("流水线演示页交互验证全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
