"""验证 demo-live.html：提交问题 → 轮询进度 → 检查六阶段产物渲染。

用法:
    python scripts/verify_demo_live.py                 # 本地（前置启动 run_live_api.py）
    python scripts/verify_demo_live.py --online        # 公网（http://120.53.11.211）
"""
# ruff: noqa: E501
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

LOCAL_BASE = "http://127.0.0.1:8000/demo/demo-live.html"
ONLINE_BASE = "http://120.53.11.211/demo-live.html"

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
    ap = argparse.ArgumentParser()
    ap.add_argument("--online", action="store_true", help="验证公网部署（http://120.53.11.211）")
    args = ap.parse_args()
    base = ONLINE_BASE if args.online else LOCAL_BASE
    shot = Path(__file__).resolve().parents[1] / "results" / (
        "live_online_shot.png" if args.online else "live_local_shot.png"
    )
    exe = _find_browser()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=exe)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        console_errors: list[str] = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        print("=== 1. 打开页面 ===")
        page.goto(base, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(800)
        assert page.locator("#question").is_visible(), "问题输入框不可见"
        print("页面加载 OK，输入框可见")

        print("=== 2. 填写研究问题并提交 ===")
        page.locator("#question").fill("PbTe 热电材料 Na 掺杂优化 zT")
        page.locator("#domain").select_option("thermoelectric")
        page.locator("#algo").select_option("ga")
        page.locator("#runBtn").click()
        page.wait_for_timeout(1500)
        assert page.locator("#progressCard").is_visible(), "进度卡片未显示"
        assert page.locator("#statusLine").is_visible(), "状态行未显示"
        print("任务已提交，进度卡片显示")

        print("=== 3. 轮询等待流水线完成（最长 240s）===")
        deadline = time.time() + 240
        done = False
        stages_seen: list[str] = []
        while time.time() < deadline:
            page.wait_for_timeout(3000)
            status = page.locator("#statusLine").inner_text()
            stage_nodes = page.locator("#stages .stage.active").all_inner_texts()
            if stage_nodes:
                stages_seen.append("|".join(stage_nodes))
            print(f"  状态: {status[:60]}")
            if page.locator("#resultCard").is_visible():
                done = True
                break
            if page.locator("#errorCard").is_visible():
                err = page.locator("#errorMsg").inner_text()
                print(f"流水线失败: {err[:300]}")
                browser.close()
                return 2
        if not done:
            print("超时未完成")
            browser.close()
            return 3

        print("=== 4. 校验结果区渲染 ===")
        page.wait_for_timeout(800)
        assert page.locator("#statBars .stat-bar").count() >= 4, "统计条不足 4 个"
        n_papers_rows = page.locator("#papersBox table tr").count()
        print(f"统计条 OK；文献表格行数: {n_papers_rows}")
        assert n_papers_rows >= 2, "文献未渲染"
        gap_items = page.locator("#gapBox .gap-item").count()
        print(f"Gap 条目数: {gap_items}")
        find_items = page.locator("#searchBox .find-item").count()
        print(f"构效发现条目数: {find_items}")
        verdict_items = page.locator("#verifyBox .verdict-item").count()
        print(f"验证条目数: {verdict_items}")

        # 截图存档
        page.screenshot(path=str(shot), full_page=True)
        print(f"截图已保存: {shot}")

        if console_errors:
            print(f"console 错误 {len(console_errors)} 条: {console_errors[:5]}")
        browser.close()
        print("\n=== 本地验证通过 ===")
        return 0


if __name__ == "__main__":
    sys.exit(main())
