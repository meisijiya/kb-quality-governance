"""对烟测页面截图并校验 el-table 是否真的渲染出那张表。

用法（仓库根目录）：
    python system/frontend-smoke/render_smoke.py [url]

默认 url 为 http://127.0.0.1:4173/，需先起静态服务：
    cd system/frontend-smoke && npm run build && npm run preview -- --port 4173

输出：system/frontend-smoke/smoke.png
退出码：0 = 截图成功、表头与表体齐全、无控制台错误、无异常文本。
"""
import os
import sys

from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK，中文输出会乱码

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "smoke.png")
DEFAULT_URL = "http://127.0.0.1:4173/"

EXPECT_HEADERS = ["业务意图", "簇数", "意图覆盖度"]
EXPECT_INTENTS = [
    "公积金提取材料",
    "海外出差报销标准",
    "密码策略例外申请",
    "社保转移办理",
    "终端病毒处置",
]
BAD_TEXTS = ["is_true_gap", "NaN", "undefined", "[object Object]"]


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page.on(
            "console",
            lambda m: errors.append(f"[console.{m.type}] {m.text}")
            if m.type == "error"
            else None,
        )
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))

        page.goto(url, wait_until="networkidle")
        page.wait_for_selector(".el-table", timeout=15000)
        page.wait_for_timeout(500)

        headers = page.eval_on_selector_all(
            ".el-table__header th .cell", "els => els.map(e => e.textContent.trim())"
        )
        cells = page.eval_on_selector_all(
            ".el-table__body tbody tr td .cell", "els => els.map(e => e.textContent.trim())"
        )
        row_count = page.eval_on_selector_all(
            ".el-table__body tbody tr", "els => els.length"
        )
        body = page.inner_text("body")

        page.screenshot(path=OUT, full_page=True)
        browser.close()

    print(f"[render_smoke] url = {url}")
    print(f"[render_smoke] 表头 = {headers}")
    print(f"[render_smoke] 表体行数 = {row_count}")
    print(f"[render_smoke] 表体单元格 = {cells}")
    print(f"[render_smoke] 截图 = {OUT}")

    if headers != EXPECT_HEADERS:
        errors.append(f"表头与预期不符：期望 {EXPECT_HEADERS}，实际 {headers}")
    if row_count != 5:
        errors.append(f"表体行数与预期不符：期望 5，实际 {row_count}")
    for want in EXPECT_INTENTS:
        if want not in cells:
            errors.append(f"表体缺少 intent 值：{want}")
    for bad in BAD_TEXTS:
        if bad in body:
            errors.append(f"页面出现不应出现的文本：{bad}")

    if errors:
        for e in errors:
            print("[render_smoke] 失败：", e)
        return 1
    print("[render_smoke] 通过：el-table 渲染出 3 列表头 + 5 行真实数据，无控制台错误")
    return 0


if __name__ == "__main__":
    sys.exit(main())
