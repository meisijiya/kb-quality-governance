"""逐条核验准备清单 §2.8 H1~H7 的验收信号。

用法（仓库根目录）：python system/prototype/acceptance_check.py
退出码：0 = 全部验收信号成立；1 = 有信号不成立。

为什么是长期脚本：H1~H7 的验收信号是原型的长期约束（上传可用、主路径首屏可见、
状态自洽、键盘可达、数字口径标注齐、真值列不外泄、溯源路径真实）。
只靠一次人工核验无法防止后续改动把这些问题带回来，因此固化成脚本。
与 check_prototype.py（数字溯源）、render_check.py（渲染）并列，互不重叠。
"""
import os
import sys

from playwright.sync_api import sync_playwright

PROTO = os.path.dirname(os.path.abspath(__file__))
INDEX = "file:///" + os.path.join(PROTO, "index.html").replace("\\", "/")

FAILS = []
OKS = []


def check(name, cond, detail=""):
    if cond:
        OKS.append(name)
        print(f"[OK]   {name} {detail}")
    else:
        FAILS.append(f"{name} {detail}")
        print(f"[FAIL] {name} {detail}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1248, "height": 949})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(INDEX, wait_until="networkidle")

        # ---- H1 上传控件真实存在且能响应 ----
        inputs = page.eval_on_selector_all(
            "input[type=file]", "els => els.map(e => e.id)")
        check("H1 存在 file input", len(inputs) >= 2, f"ids={inputs}")
        before = page.inner_text("body")
        page.set_input_files("#docUploadInput", files=[{
            "name": "docs_probe.csv", "mimeType": "text/csv", "buffer": b"a,b\n1,2\n"}])
        page.wait_for_timeout(200)
        feedback = page.inner_text("#docUploadFeedback")
        after = page.inner_text("body")
        check("H1 选中文件后有反馈", "docs_probe.csv" in feedback, repr(feedback[:60]))
        check("H1 页面文本随之变化", len(after) != len(before))

        # ---- H2 主 CTA 在首屏可见 ----
        for w, h in ((1248, 949), (1440, 900)):
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(150)
            cta = page.query_selector("#uploadCta")
            box = cta.bounding_box()
            check(f"H2 {w}x{h} 上传页 CTA 首屏可见",
                  box is not None and box["y"] + box["height"] <= h,
                  f"y={box['y'] if box else None}")

        # 扫描页 CTA
        page.set_viewport_size({"width": 1248, "height": 949})
        page.evaluate("document.querySelector('.nav-item[data-page=\"scan\"]').click()")
        page.wait_for_timeout(250)
        box = page.query_selector("#scanCta").bounding_box()
        check("H2 1248x949 扫描页 CTA 首屏可见",
              box is not None and box["y"] + box["height"] <= 949, f"y={box['y'] if box else None}")

        # 1024-1439 侧栏折叠下导航有可访问名
        page.set_viewport_size({"width": 1200, "height": 900})
        page.wait_for_timeout(200)
        names = page.eval_on_selector_all(
            ".nav-item",
            "els => els.map(e => (e.getAttribute('aria-label') || e.innerText || '').trim())")
        check("H2 1200px 导航均有可访问名", all(n for n in names), f"names={names}")

        # ---- H3 状态自洽：未扫描时徽标为占位符，指标为占位符 ----
        page.set_viewport_size({"width": 1440, "height": 900})
        page.evaluate("document.querySelector('.nav-item[data-page=\"lists\"]').click()")
        page.wait_for_timeout(250)
        badges = page.eval_on_selector_all(".badge", "els => els.map(e => e.innerText.trim())")
        check("H3 未扫描时徽标为占位符", all(b in ("—", "") for b in badges), f"badges={badges}")
        metrics = page.eval_on_selector_all(
            "#listMetricGrid .kpi-value", "els => els.map(e => e.innerText.trim())")
        check("H3 未扫描时指标为占位符", all(m == "—" for m in metrics), f"metrics={metrics}")
        # 加载态有文字且 aria-busy
        page.evaluate(
            "document.querySelector('.seg-btn[data-target=\"lists\"][data-state=\"loading\"]').click()")
        page.wait_for_timeout(200)
        loading = page.evaluate("""() => {
            const b = document.querySelector('#listPanel .state-block[data-list="loading"]');
            if (!b || b.hidden) return null;
            return { text: b.innerText.trim(), busy: b.getAttribute('aria-busy'),
                     sk: b.querySelectorAll('.skeleton-wrap[aria-busy="true"]').length };
        }""")
        check("H3 加载态有文字且标记 aria-busy",
              loading is not None and bool(loading["text"]) and loading["busy"] == "true",
              f"{loading}")
        # 错误态有非破坏性恢复入口
        page.evaluate(
            "document.querySelector('.seg-btn[data-target=\"lists\"][data-state=\"error\"]').click()")
        page.wait_for_timeout(200)
        err = page.evaluate("""() => {
            const b = document.querySelector('#listPanel .state-block[data-list="error"]');
            if (!b || b.hidden) return null;
            return { text: b.innerText.trim(),
                     retry: !!b.querySelector('#listsRetry'),
                     goto: !!b.querySelector('#listsGotoScan') };
        }""")
        check("H3 错误态有重载与转扫描两个恢复入口",
              err is not None and err["retry"] and err["goto"], f"{err}")

        # ---- H4 键盘与无障碍 ----
        page.evaluate("document.querySelector('.nav-item[data-page=\"upload\"]').click()")
        page.wait_for_timeout(200)
        focus_tag = page.evaluate("() => document.activeElement.tagName")
        check("H4 切页后焦点落在新页 h1", focus_tag == "H1", f"activeElement={focus_tag}")
        # 数字右对齐 + tabular
        page.evaluate("document.querySelector('.nav-item[data-page=\"lists\"]').click()")
        page.wait_for_timeout(200)
        page.evaluate(
            "document.querySelector('.seg-btn[data-target=\"lists\"][data-state=\"success\"]').click()")
        page.wait_for_timeout(250)
        align = page.evaluate("""() => {
            const n = document.querySelectorAll('#listBody td.n');
            if (!n.length) return { count: 0 };
            let right = 0, mono = 0;
            n.forEach(td => {
                if (getComputedStyle(td).textAlign === 'right') right += 1;
                if (getComputedStyle(td).fontVariantNumeric.includes('tabular-nums')) mono += 1;
            });
            return { count: n.length, right: right, mono: mono };
        }""")
        check("H4 数值单元格右对齐", align.get("right") == align.get("count"), f"{align}")
        check("H4 数值单元格启用 tabular-nums", align.get("mono") == align.get("count"), f"{align}")
        # 最小字号
        small = page.evaluate("""() => {
            const bad = [];
            document.querySelectorAll('.app-main *').forEach(el => {
                if (!el.textContent || !el.textContent.trim()) return;
                if (el.children.length) return;
                const size = parseFloat(getComputedStyle(el).fontSize);
                if (size < 12) bad.push(el.className + ':' + size);
            });
            return bad.slice(0, 5);
        }""")
        check("H4 无小于 12px 的正文字号", not small, f"{small}")
        # 展开按钮可访问名随状态变化
        page.evaluate(
            "document.querySelector('.seg-btn[data-target=\"lists\"][data-state=\"success\"]').click()")
        page.wait_for_timeout(250)
        btn = page.query_selector("#listBody button.btn-sm")
        name_before = btn.get_attribute("aria-label")
        expanded_before = btn.get_attribute("aria-expanded")
        btn.click()
        page.wait_for_timeout(200)
        btn2 = page.query_selector("#listBody button.btn-sm")
        name_after = btn2.get_attribute("aria-label")
        expanded_after = btn2.get_attribute("aria-expanded")
        check("H4 展开按钮可访问名随状态变化",
              name_before != name_after and expanded_before == "false" and expanded_after == "true",
              f"{name_before!r} -> {name_after!r}")
        # tab 方向键
        page.evaluate("document.querySelector('#tab-gap').focus()")
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(200)
        sel = page.evaluate(
            "() => document.querySelector('.tab[aria-selected=\"true\"]').dataset.tab")
        check("H4 tab 支持方向键切换", sel == "corrupt", f"selected={sel}")
        # 弹窗关闭后焦点归还
        # 先把扫描态复位到「未扫描」：扫描已成功时点 CTA 是「查看清单」，
        # 不该弹确认框——那是另一条路径，不能混在同一次检查里。
        page.evaluate(
            "document.querySelector('.seg-btn[data-target=\"scan\"][data-state=\"empty\"]').click()")
        page.wait_for_timeout(200)
        page.evaluate("document.querySelector('.nav-item[data-page=\"scan\"]').click()")
        page.wait_for_timeout(250)
        page.evaluate("document.querySelector('#scanCta').click()")
        page.wait_for_timeout(300)
        has_modal = page.evaluate("() => !!document.querySelector('#modalRoot .msgbox')")
        check("H4 扫描前有确认弹窗", has_modal)
        if has_modal:
            page.keyboard.press("Escape")
            page.wait_for_timeout(250)
            back = page.evaluate("() => document.activeElement.id")
            check("H4 弹窗 Esc 关闭后焦点归还触发按钮", back == "scanCta", f"activeElement={back}")

        # ---- H5/H6/H7 文案与口径 ----
        page.evaluate("document.querySelector('.nav-item[data-page=\"lists\"]').click()")
        page.wait_for_timeout(250)
        page.evaluate(
            "document.querySelector('.seg-btn[data-target=\"lists\"][data-state=\"success\"]').click()")
        page.wait_for_timeout(250)
        # 缺口页：判定单元是业务意图，候选池规模来自簇级明细
        page.evaluate("document.querySelector('#tab-gap').click()")
        page.wait_for_timeout(250)
        gap_text = page.inner_text("body")
        gap_rows = page.eval_on_selector_all("#listBody tr", "els => els.length")
        gap_head = page.inner_text("#listHead")
        check("H5 缺口页声明判定单元是业务意图",
              "判定单元" in gap_text and "业务意图" in gap_text)
        check("H5 缺口清单按业务意图逐条列示",
              gap_rows == 5 and "业务意图" in gap_head and "簇数" in gap_head
              and "意图覆盖度" in gap_head and "意图下工单数" in gap_head,
              f"rows={gap_rows}")
        check("H5 缺口候选池规模取自簇级明细",
              "95" in gap_text and "30" in gap_text, "")

        # 腐化页：两个口径各自报 P/R/F1，合计只作覆盖面说明
        page.evaluate("document.querySelector('#tab-corrupt').click()")
        page.wait_for_timeout(250)
        body = page.inner_text("body")
        check("H5 腐化页分两类口径各报 P/R/F1",
              "内容过期" in body and "维护周期" in body
              and "1.0000" in body and "0.8158" in body and "0.8986" in body)
        check("H5 腐化页声明合计只作覆盖面说明", "覆盖面" in body)
        check("H6 下载区明示含评测标注列", "评测标注" in body or "溯源" in body)
        check("H7 交代展示行数与判定总数", "代表行" in body and "判定总数" in body)
        check("H5 派生值有标注", "派生值" in body)
        # 真值列不外泄
        leaked = [f for f in ("is_true_gap", "is_true_group", "in_control_sample",
                              "is_dup_copy", "dup_source", "fp_reason") if f in body]
        check("H5 界面不透出真值列", not leaked, f"leaked={leaked}")
        # 溯源路径真实
        check("H6 溯源指向真实产物目录", "poc/kbgovernance/" in body and "data/" not in body)

        browser.close()

    print()
    print(f"[acceptance_check] 通过 {len(OKS)} 条，失败 {len(FAILS)} 条")
    if errors:
        print(f"[acceptance_check] pageerror: {errors}")
    for f in FAILS:
        print("[acceptance_check] 失败：", f)
    return 1 if (FAILS or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
