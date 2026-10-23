"""渲染原型三页并截图，同时收集控制台错误与布局溢出。

用法（仓库根目录）：
    python system/prototype/render_check.py
输出：system/prototype/shots/*.png，控制台错误打印到 stdout。
退出码：0 = 无控制台错误且无横向溢出。
"""
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "shots")
# (截图名, 顶栏 data-page 值, 该页内需要额外点开的 tab 的 data-tab 值或 None)
PAGES = [
    ("upload", "upload", None),
    ("scan", "scan", None),
    ("gaps", "lists", "gap"),
    ("corrupt", "lists", "corrupt"),
    ("dups", "lists", "dup"),
]

FATAL = []


def main():
    os.makedirs(SHOTS, exist_ok=True)
    url = "file:///" + os.path.join(HERE, "index.html").replace("\\", "/")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.goto(url, wait_until="networkidle")

        for name, page_key, tab_key in PAGES:
            clicked = page.evaluate(
                """(page_key) => {
                    const el = document.querySelector('[data-page="' + page_key + '"]');
                    if (el) { el.click(); return true; }
                    return false;
                }""",
                page_key,
            )
            page.wait_for_timeout(200)
            if tab_key:
                tabbed = page.evaluate(
                    """(tab_key) => {
                        const el = document.querySelector('[data-tab="' + tab_key + '"]');
                        if (el) { el.click(); return true; }
                        return false;
                    }""",
                    tab_key,
                )
                if not tabbed:
                    FATAL.append(f"{name} 页的 tab {tab_key} 未找到")
            page.wait_for_timeout(350)
            path = os.path.join(SHOTS, f"{name}.png")
            # 原型是「固定视口 + 内部滚动」布局（.app-main overflow-y:auto），
            # full_page 截图只会拍到 900px 视口；先量出滚动容器的内容高度再放大视口。
            need = page.evaluate(
                """() => {
                    const m = document.querySelector('.app-main');
                    const h = m ? m.scrollHeight : document.body.scrollHeight;
                    return Math.min(Math.max(h + 80, 900), 4000);
                }"""
            )
            page.set_viewport_size({"width": 1440, "height": int(need)})
            page.wait_for_timeout(250)
            page.screenshot(path=path, full_page=True)

            overflow = page.evaluate(
                "() => { const d = document.documentElement;"
                " return { sw: d.scrollWidth, cw: d.clientWidth }; }"
            )
            if overflow["sw"] > overflow["cw"] + 1:
                FATAL.append(f"{name} 页横向溢出：scrollWidth={overflow['sw']} > clientWidth={overflow['cw']}")
            if not clicked:
                FATAL.append(f"{name} 页切换失败：找不到 data-page={page_key} 的导航元素")

            # 页面内应能看到关键指标，检查是否渲染出 NaN / undefined / 空白
            body = page.inner_text("body")
            for bad in ("NaN", "undefined", "[object Object]"):
                if bad in body:
                    FATAL.append(f"{name} 页出现异常文本 {bad}")

        browser.close()

    if errors:
        for e in errors:
            print("[console]", e)
    print(f"[render_check] 截图输出：{SHOTS}")
    if FATAL or errors:
        for f in FATAL:
            print("[render_check] 失败：", f)
        return 1
    print("[render_check] 通过：三页渲染无控制台错误、无横向溢出、无 NaN/undefined")
    return 0


if __name__ == "__main__":
    sys.exit(main())
