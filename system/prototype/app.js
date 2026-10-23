/* =========================================================
   企业知识库质量治理系统 Web 端原型 交互脚本
   仅做本地交互：页面切换、状态切换、Tab 切换、行展开、
   确认弹窗、轻提示、复制。不发起任何真实网络请求。
   ========================================================= */
(function () {
  'use strict';

  var KB = window.KB;
  var M = KB.metrics;

  var ui = {
    page: 'upload',
    states: { upload: 'success', scan: 'success', lists: 'success' },
    tab: 'gap',
    scanTriggered: false,
    expanded: {}
  };

  /* ---------- 工具 ---------- */
  function q(sel, root) { return (root || document).querySelector(sel); }
  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* 阈值等原值：3 -> "3"，0.62 -> "0.62" */
  function raw(v) { return String(v); }
  /* 三类模块的精确率等：缺口 3 位，其余 4 位 */
  function p3(v) { return Number(v).toFixed(3); }
  function p4(v) { return Number(v).toFixed(4); }
  function diff4(a, b) { return (Number(a) - Number(b)).toFixed(4); }

  var toastTimer = null;
  function toast(msg) {
    var el = q('#toast');
    el.textContent = msg;
    el.hidden = false;
    if (toastTimer) { clearTimeout(toastTimer); }
    toastTimer = setTimeout(function () { el.hidden = true; }, 2400);
  }

  function copyText(text, label) {
    function done() { toast('已复制 ' + (label || text)); }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); done(); }
      catch (e) { toast('复制失败，请手动选择文本'); }
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
  }

  /* ---------- 确认弹窗（message-box） ---------- */
  function messageBox(opts) {
    return new Promise(function (resolve) {
      var mask = document.createElement('div');
      mask.className = 'mask';
      mask.innerHTML =
        '<div class="msgbox" role="dialog" aria-modal="true" aria-labelledby="mbTitle">' +
          '<div class="msgbox-head"><span id="mbTitle">' + esc(opts.title) + '</span>' +
            '<button class="icon-btn msgbox-close" type="button" aria-label="关闭确认框"><svg class="icon"><use href="#i-close"></use></svg></button>' +
          '</div>' +
          '<div class="msgbox-body">' + esc(opts.message) + '</div>' +
          '<div class="msgbox-foot">' +
            '<button class="btn msgbox-cancel" type="button">' + esc(opts.cancelText || '取消') + '</button>' +
            '<button class="btn btn-primary msgbox-ok" type="button">' + esc(opts.okText || '确定') + '</button>' +
          '</div>' +
        '</div>';

      document.body.appendChild(mask);
      var okBtn = q('.msgbox-ok', mask);
      var cancelBtn = q('.msgbox-cancel', mask);
      var closeBtn = q('.msgbox-close', mask);

      function close(result) {
        document.removeEventListener('keydown', onKey);
        mask.remove();
        resolve(result);
      }
      function onKey(e) {
        if (e.key === 'Escape') { close(false); }
        if (e.key === 'Tab') {
          var f = [okBtn, cancelBtn, closeBtn];
          var i = f.indexOf(document.activeElement);
          e.preventDefault();
          var next = e.shiftKey ? (i <= 0 ? f.length - 1 : i - 1) : (i === f.length - 1 ? 0 : i + 1);
          f[next].focus();
        }
      }
      okBtn.addEventListener('click', function () { close(true); });
      cancelBtn.addEventListener('click', function () { close(false); });
      closeBtn.addEventListener('click', function () { close(false); });
      mask.addEventListener('mousedown', function (e) { if (e.target === mask) { close(false); } });
      document.addEventListener('keydown', onKey);
      okBtn.focus();
    });
  }

  /* ---------- 页面切换 ---------- */
  function setPage(name) {
    ui.page = name;
    document.body.setAttribute('data-page', name);
    qa('.page').forEach(function (sec) { sec.hidden = sec.getAttribute('data-page') !== name; });
    qa('.menu-item').forEach(function (b) {
      var on = b.getAttribute('data-page') === name;
      b.classList.toggle('is-active', on);
      if (on) { b.setAttribute('aria-current', 'page'); } else { b.removeAttribute('aria-current'); }
    });
    closeDrawer();
    var main = q('.app-main');
    if (main) { main.scrollTop = 0; }
  }

  /* ---------- 状态切换 ---------- */
  function applyState(page, state) {
    ui.states[page] = state;
    var sec = q('#page-' + page);
    qa('[data-states]', sec).forEach(function (el) {
      var list = el.getAttribute('data-states').split(',');
      el.hidden = list.indexOf(state) === -1;
    });
    qa('.seg-btn[data-target="' + page + '"]').forEach(function (b) {
      var on = b.getAttribute('data-state') === state;
      b.classList.toggle('is-on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    if (page === 'scan') {
      var running = state === 'running';
      document.body.classList.toggle('is-scanning', running);
      q('#globalProgress').hidden = !running;
      if (running) { setSteps(2); }
      else if (ui.scanTriggered) {
        ui.scanTriggered = false;
        markCorpusCleared();
      }
      updateBadge(state);
    }
    refreshUploadLock();
  }

  /* 扫描占用时的上传锁定：扫描页进入 running，或上传页切到「扫描占用」态 */
  function refreshUploadLock() {
    var scanning = document.body.classList.contains('is-scanning');
    var busy = scanning || ui.states.upload === 'busy';
    q('#scanLockAlert').hidden = !busy;
    syncUploadDisabled();
  }

  function markCorpusCleared() {
    var el = q('#corpusClearedAlert');
    if (el) { el.hidden = false; }
    var btn = q('[data-goto="scan"]', q('#page-upload'));
    var hint = q('#uploadNextHint');
    if (hint) { hint.textContent = '上次扫描已清空语料，如需再次扫描请重新上传。'; }
    if (btn) {
      btn.setAttribute('disabled', 'disabled');
      btn.setAttribute('title', '语料已清空，请重新上传语料');
    }
  }

  function syncUploadDisabled() {
    var busy = document.body.classList.contains('is-scanning');
    ['#docUpload', '#ticketUpload'].forEach(function (sel) {
      var el = q(sel);
      if (!el) { return; }
      el.setAttribute('aria-disabled', busy ? 'true' : 'false');
      el.style.pointerEvents = busy ? 'none' : '';
      el.style.opacity = busy ? '0.55' : '';
    });
  }

  function updateBadge(scanState) {
    var badge = q('#scanBadge');
    var map = {
      success: { cls: 'tag-success', icon: 'i-success', text: '已完成', tip: '扫描状态：已完成（status=completed）' },
      running: { cls: 'tag-warning', icon: 'i-info', text: '扫描中', tip: '扫描状态：扫描中（status=running）' },
      empty: { cls: 'tag-info', icon: 'i-info', text: '未扫描', tip: '扫描状态：从未扫描（status=never_scanned）' },
      error: { cls: 'tag-danger', icon: 'i-error', text: '失败', tip: '扫描状态：失败（status=failed）' }
    };
    var m = map[scanState] || map.success;
    badge.className = 'tag ' + m.cls;
    badge.setAttribute('data-tip', m.tip);
    badge.innerHTML = '<svg class="icon"><use href="#' + m.icon + '"></use></svg>' + m.text;
  }

  function setSteps(activeIndex) {
    qa('#scanSteps .step').forEach(function (li, i) {
      li.classList.remove('is-done', 'is-process');
      if (i < activeIndex) { li.classList.add('is-done'); }
      else if (i === activeIndex) { li.classList.add('is-process'); }
    });
  }

  /* ---------- 扫描结果总览 ---------- */
  function renderScanOverview() {
    var rows = [
      { name: '知识缺口', thr: M.gap.threshold, p: p3(M.gap.precision), r: p3(M.gap.recall), f: p3(M.gap.f1), count: M.gap.gap_clusters, unit: '缺口簇' },
      { name: '内容腐化', thr: M.corrupt.threshold, p: p4(M.corrupt.precision), r: p4(M.corrupt.recall), f: p4(M.corrupt.f1), count: M.corrupt.detected, unit: '篇文档' },
      { name: '重复冗余', thr: M.dup.threshold, p: p4(M.dup.group_precision), r: p4(M.dup.group_recall), f: p4(M.dup.group_f1), count: M.dup.dup_groups, unit: '个重复组' }
    ];
    q('#scanOverviewBody').innerHTML = rows.map(function (row) {
      return '<tr>' +
        '<td>' + esc(row.name) + '</td>' +
        '<td class="num">' + esc(raw(row.thr)) + '</td>' +
        '<td class="num">' + esc(row.p) + '</td>' +
        '<td class="num">' + esc(row.r) + '</td>' +
        '<td class="num">' + esc(row.f) + '</td>' +
        '<td class="num">' + esc(String(row.count)) + ' ' + esc(row.unit) + '</td>' +
      '</tr>';
    }).join('');
  }

  /* ---------- 清单页：指标条 ---------- */
  function tabMetrics(tab) {
    if (tab === 'gap') {
      return {
        thr: raw(M.gap.threshold), p: p3(M.gap.precision), r: p3(M.gap.recall), f: p3(M.gap.f1),
        count: M.gap.gap_clusters, unit: '缺口簇',
        cali: '缺口簇（1 簇 = 1 个业务意图下的工单群）；涉及业务意图 5 个',
        rule: '段落级语义覆盖度中位数低于阈值 0.62 判定为知识缺口，命中名次 1–7 共 7 个缺口簇。同一业务意图可能对应多个缺口簇，列表未按意图去重。'
      };
    }
    if (tab === 'corrupt') {
      return {
        thr: raw(M.corrupt.threshold), p: p4(M.corrupt.precision), r: p4(M.corrupt.recall), f: p4(M.corrupt.f1),
        count: M.corrupt.detected, unit: '篇文档',
        cali: '文档（1 篇 = 1 行）；埋入 62 篇 / 检出 69 篇',
        rule: '风险分达到阈值 3 判定为内容腐化。风险分与命中规则组合一一对应（权重 R1 3 / R2 2 / R3 2 / R4 1），每行同时给出数值与规则组合，不以颜色作为唯一编码。'
      };
    }
    return {
      thr: raw(M.dup.threshold), p: p4(M.dup.group_precision), r: p4(M.dup.group_recall), f: p4(M.dup.group_f1),
      count: M.dup.dup_groups, unit: '个重复组',
      cali: '重复组（1 组 = 1 组重复文档）；覆盖文档 49 篇',
      rule: '组内最大余弦相似度达到阈值 0.95 判定为重复冗余。精确率、召回率、F1 为组级口径，F1 = 1.0000 属乐观值。'
    };
  }

  function renderListMetrics() {
    var m = tabMetrics(ui.tab);
    q('#listMetricGrid').innerHTML =
      cell('阈值', m.thr) +
      cell('精确率', m.p) +
      cell('召回率', m.r) +
      cell('F1', m.f) +
      cell('命中数', String(m.count) + '<span class="unit">' + esc(m.unit) + '</span>');

    q('#listCaliGrid').innerHTML =
      '<div class="desc-cell"><span class="desc-label">统计单元口径</span><span class="desc-value">' + esc(m.cali) + '</span></div>' +
      '<div class="desc-cell"><span class="desc-label">判定口径</span><span class="desc-value">' + esc(m.rule) + '</span></div>';
  }

  function cell(label, value) {
    return '<div class="desc-cell"><span class="desc-label">' + esc(label) + '</span><span class="desc-value">' + value + '</span></div>';
  }

  /* ---------- 清单页：表格 ---------- */
  function progCell(dec, threshold, label) {
    var pct = Math.round(dec * 100);
    return '<div class="prog-cell">' +
      '<div class="prog-nums"><span class="prog-pct">' + pct + '%</span><span class="prog-dec">' + esc(raw(dec)) + '</span></div>' +
      '<div class="prog" role="img" aria-label="' + esc(label) + ' ' + pct + '%，原始值 ' + esc(raw(dec)) + '，阈值 ' + esc(raw(threshold)) + '">' +
        '<span class="prog-fill" style="width:' + (dec * 100).toFixed(2) + '%"></span>' +
        '<span class="prog-tick" style="left:' + (threshold * 100) + '%"></span>' +
      '</div>' +
      '<div class="prog-foot">刻度线标出阈值 ' + esc(raw(threshold)) + '</div>' +
    '</div>';
  }

  function copyBtn(text, label) {
    return '<button class="copy-btn" type="button" data-copy="' + esc(text) + '" data-copy-label="' + esc(label || '') + '" aria-label="复制 ' + esc(label || text) + '">' +
      '<svg class="icon"><use href="#i-copy"></use></svg></button>';
  }

  var HEADS = {
    gap: ['排名', '业务意图', '簇内工单数', '覆盖度（中位数）', '距阈值差值'],
    corrupt: ['文档编码', '标题', '业务域', '最后修改时间', '风险分', '命中规则'],
    dup: ['组号', '组内文档数', '主文档', '组内最大余弦相似度', '组规模']
  };

  function severityOf(score) {
    if (score >= 8) { return { cls: 'sev-danger', tag: 'tag-solid-danger', text: '最高风险' }; }
    if (score >= 6) { return { cls: 'sev-danger', tag: 'tag-danger', text: '高' }; }
    if (score >= 5) { return { cls: 'sev-warning', tag: 'tag-warning', text: '中' }; }
    return { cls: 'sev-info', tag: 'tag-info', text: '低（达阈值）' };
  }

  function ruleCodes(ruleHits) {
    return ruleHits.split('|').map(function (s) { return s.split('_')[0]; }).join('+');
  }

  function renderListTable() {
    var head = q('#listHead');
    var body = q('#listBody');
    var alertHost = q('#listAlertHost');

    head.innerHTML = '<tr><th scope="col" class="col-expand"><span class="visually-hidden">展开</span></th>' +
      HEADS[ui.tab].map(function (h) { return '<th scope="col">' + esc(h) + '</th>'; }).join('') + '</tr>';

    alertHost.innerHTML = '';
    var rows = [];

    if (ui.tab === 'gap') {
      rows = KB.gaps.map(function (g) {
        var d = diff4(M.gap.threshold, g.cover_median);
        return {
          id: 'gap-' + g.rank,
          cls: '',
          cells:
            '<td class="num">' + g.rank + '</td>' +
            '<td>' + esc(g.intent) + '</td>' +
            '<td><span class="tag tag-info">' + g.size + ' 条工单</span></td>' +
            '<td>' + progCell(g.cover_median, M.gap.threshold, '覆盖度') + '</td>' +
            '<td class="num">低于阈值 ' + d + '</td>',
          detail: gapDetail(g, d)
        };
      });
    } else if (ui.tab === 'corrupt') {
      rows = KB.corrupt.map(function (c) {
        var s = severityOf(c.risk_score);
        return {
          id: 'corrupt-' + c.doc_id,
          cls: s.cls,
          cells:
            '<td class="cell-code">' + esc(c.doc_id) + copyBtn(c.doc_id, c.doc_id) + '</td>' +
            '<td><span class="cell-clip is-wide" title="' + esc(c.title) + '">' + esc(c.title) + '</span></td>' +
            '<td>' + esc(c.category) + '</td>' +
            '<td class="num">' + esc(c.last_modified) + '</td>' +
            '<td><span class="num">' + c.risk_score + '</span> <span class="tag ' + s.tag + '">' + esc(s.text) + '</span></td>' +
            '<td><span class="cell-clip" title="' + esc(c.rule_hits) + '">' + esc(ruleCodes(c.rule_hits)) + '</span></td>',
          detail: corruptDetail(c, s)
        };
      });
      alertHost.innerHTML =
        '<div class="alert alert-info mb12">' +
          '<svg class="icon alert-icon"><use href="#i-info"></use></svg>' +
          '<div><span class="alert-title">共命中 ' + M.corrupt.detected + ' 项，已加载 ' + KB.corrupt.length + ' 条明细</span>' +
          '<span class="alert-desc">列表展示命中结果中的代表行，完整命中集合共 ' + M.corrupt.detected + ' 篇文档。</span></div>' +
        '</div>';
    } else {
      rows = KB.dups.map(function (d) {
        var three = d.size === 3;
        return {
          id: 'dup-' + d.group,
          cls: three ? 'sev-warning' : 'sev-info',
          cells:
            '<td class="num">' + d.group + '</td>' +
            '<td class="num">' + d.size + ' 篇</td>' +
            '<td class="cell-code">' + esc(d.primary_doc) + copyBtn(d.primary_doc, d.primary_doc) + '</td>' +
            '<td>' + progCell(d.max_sim, M.dup.threshold, '组内最大余弦相似度') + '</td>' +
            '<td><span class="tag ' + (three ? 'tag-warning' : 'tag-info') + '">' + d.size + ' 篇成组</span></td>',
          detail: dupDetail(d)
        };
      });
    }

    body.innerHTML = rows.map(function (row) {
      return '<tr class="' + row.cls + '" data-row-id="' + row.id + '">' +
          '<td class="col-expand">' +
            '<button class="expand-btn" type="button" aria-expanded="false" aria-label="展开该行详情" data-expand="' + row.id + '">' +
              '<svg class="icon"><use href="#i-chevron"></use></svg>' +
            '</button>' +
          '</td>' +
          row.cells +
        '</tr>' +
        '<tr class="expand-row" data-expand-row="' + row.id + '" hidden><td colspan="' + (HEADS[ui.tab].length + 1) + '">' + row.detail + '</td></tr>';
    }).join('');

    var hint = q('#downloadHint');
    if (hint) {
      var names = { gap: '知识缺口', corrupt: '内容腐化', dup: '重复冗余' };
      hint.textContent = '当前 Tab：' + names[ui.tab] + '。下载内容为源 CSV 原文，不做二次加工。';
    }
  }

  /* ---------- 展开详情 ---------- */
  function gapDetail(g, d) {
    return '<div class="expand">' +
      '<div class="sub-card">' +
        '<h4>代表工单' + copyBtn(g.rep_ticket, g.rep_ticket) + '</h4>' +
        '<dl class="kv-list">' +
          '<div class="kv"><dt>代表工单号</dt><dd class="cell-code">' + esc(g.rep_ticket) + '</dd></div>' +
        '</dl>' +
        '<div class="quote mt12">' + esc(g.rep_text) + '</div>' +
      '</div>' +
      '<div class="expand-cols">' +
        '<div class="sub-card">' +
          '<h4>覆盖度判定</h4>' +
          '<dl class="kv-list">' +
            '<div class="kv"><dt>覆盖度（中位数）</dt><dd class="num">' + esc(raw(g.cover_median)) + '</dd></div>' +
            '<div class="kv"><dt>阈值</dt><dd class="num">' + esc(raw(M.gap.threshold)) + '</dd></div>' +
            '<div class="kv"><dt>差值</dt><dd class="num">低于阈值 ' + d + '</dd></div>' +
          '</dl>' +
          '<p class="hint mt12">覆盖度低于阈值才入选；条越短表示覆盖越低。数值与整数百分比并列，避免整数化造成精度误读。</p>' +
        '</div>' +
        '<div class="sub-card">' +
          '<h4>影响规模</h4>' +
          '<dl class="kv-list">' +
            '<div class="kv"><dt>业务意图</dt><dd>' + esc(g.intent) + '</dd></div>' +
            '<div class="kv"><dt>簇内工单数</dt><dd class="num">' + g.size + ' 条</dd></div>' +
            '<div class="kv"><dt>命中名次</dt><dd class="num">' + g.rank + '</dd></div>' +
          '</dl>' +
          '<p class="hint mt12">列表按源文件命中名次固定展示，不提供列排序切换。</p>' +
        '</div>' +
      '</div>' +
      '<div class="alert alert-info">' +
        '<svg class="icon alert-icon"><use href="#i-info"></use></svg>' +
        '<div><span class="alert-title">判定基于段落级语义覆盖度</span><span class="alert-desc">同一业务意图可能对应多个缺口簇，因此命中 7 簇只涉及 5 个业务意图。产物中没有严重度字段，因此不做离散分档。</span></div>' +
      '</div>' +
    '</div>';
  }

  function corruptDetail(c, s) {
    var reasons = c.reasons.split(';').map(function (r) { return r.trim(); }).filter(Boolean);
    var rules = c.rule_hits.split('|');
    var weightMap = { R1: M.corrupt.rule_weight.R1, R2: M.corrupt.rule_weight.R2, R3: M.corrupt.rule_weight.R3, R4: M.corrupt.rule_weight.R4 };
    var hitMap = { R1: M.corrupt.rule_hit_counts.R1, R2: M.corrupt.rule_hit_counts.R2, R3: M.corrupt.rule_hit_counts.R3, R4: M.corrupt.rule_hit_counts.R4 };

    return '<div class="expand">' +
      '<div class="sub-card">' +
        '<h4>判定理由' + copyBtn(c.doc_id, c.doc_id) + '</h4>' +
        '<div class="reason-list">' +
          reasons.map(function (r, i) {
            return '<div class="reason-item"><span class="bullet">' + (i + 1) + '</span><span>' + esc(r) + '</span></div>';
          }).join('') +
        '</div>' +
      '</div>' +
      '<div class="expand-cols">' +
        '<div class="sub-card">' +
          '<h4>命中规则</h4>' +
          '<dl class="kv-list">' +
            rules.map(function (r) {
              var code = r.split('_')[0];
              var text = r.split('_').slice(1).join('_');
              return '<div class="kv"><dt>' + esc(code) + ' ' + esc(text) + '</dt><dd>权重 ' + weightMap[code] + '，命中 ' + hitMap[code] + ' 篇</dd></div>';
            }).join('') +
            '<div class="kv"><dt>风险分</dt><dd class="num">' + c.risk_score + ' <span class="tag ' + s.tag + '">' + esc(s.text) + '</span></dd></div>' +
          '</dl>' +
          '<p class="hint mt12">规则命中数为全部 300 篇文档的统计口径。</p>' +
        '</div>' +
        '<div class="sub-card">' +
          '<h4>文档信息</h4>' +
          '<dl class="kv-list">' +
            '<div class="kv"><dt>文档编码</dt><dd class="cell-code">' + esc(c.doc_id) + '</dd></div>' +
            '<div class="kv"><dt>标题</dt><dd>' + esc(c.title) + '</dd></div>' +
            '<div class="kv"><dt>业务域</dt><dd>' + esc(c.category) + '</dd></div>' +
            '<div class="kv"><dt>最后修改时间</dt><dd class="num">' + esc(c.last_modified) + '</dd></div>' +
          '</dl>' +
        '</div>' +
      '</div>' +
      '<div class="alert alert-warning">' +
        '<svg class="icon alert-icon"><use href="#i-warning"></use></svg>' +
        '<div><span class="alert-title">阈值 risk_score ≥ 3</span><span class="alert-desc">命中规则越多分值越高。风险分与规则组合一一对应，颜色不是唯一编码，可只读数值与文字分辨。</span></div>' +
      '</div>' +
    '</div>';
  }

  function dupDetail(d) {
    var members = d.member_docs.split('|');
    var tags = members.map(function (m) {
      var isPrimary = m === d.primary_doc;
      return '<span class="tag ' + (isPrimary ? 'tag-primary-doc' : 'tag-info') + '">' + esc(m) + (isPrimary ? ' 主文档' : '') + '</span>';
    }).join('');

    return '<div class="expand">' +
      '<div class="sub-card">' +
        '<h4>成员文档</h4>' +
        '<div class="tag-cloud">' + tags + '</div>' +
      '</div>' +
      '<div class="expand-cols">' +
        '<div class="sub-card">' +
          '<h4>相似度判定</h4>' +
          '<dl class="kv-list">' +
            '<div class="kv"><dt>组内最大余弦相似度</dt><dd class="num">' + esc(raw(d.max_sim)) + '</dd></div>' +
            '<div class="kv"><dt>阈值</dt><dd class="num">' + esc(raw(M.dup.threshold)) + '</dd></div>' +
            '<div class="kv"><dt>组内文档数</dt><dd class="num">' + d.size + ' 篇</dd></div>' +
          '</dl>' +
          '<div class="mt12">' + progCell(d.max_sim, M.dup.threshold, '组内最大余弦相似度') + '</div>' +
        '</div>' +
        '<div class="sub-card">' +
          '<h4>主文档选举</h4>' +
          '<dl class="kv-list">' +
            '<div class="kv"><dt>主文档</dt><dd class="cell-code">' + esc(d.primary_doc) + '</dd></div>' +
            '<div class="kv"><dt>选举依据</dt><dd>引用次数、最后修改时间、标题包含度的归一化加权合成</dd></div>' +
          '</dl>' +
          '<p class="hint mt12">产物只给出归一化合成式描述，不提供各项权重数值，因此界面不作量化说明。</p>' +
        '</div>' +
      '</div>' +
    '</div>';
  }

  /* ---------- 展开 / 收起 ---------- */
  function toggleExpand(id, btn) {
    var row = q('[data-expand-row="' + id + '"]');
    var tr = q('[data-row-id="' + id + '"]');
    if (!row) { return; }
    var open = row.hidden;
    row.hidden = !open;
    if (tr) { tr.classList.toggle('is-open', open); }
    if (btn) { btn.setAttribute('aria-expanded', open ? 'true' : 'false'); }
  }

  /* ---------- Tab 切换 ---------- */
  function setTab(tab) {
    ui.tab = tab;
    qa('.tab').forEach(function (b) {
      var on = b.getAttribute('data-tab') === tab;
      b.classList.toggle('is-on', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    q('#listPanel').setAttribute('aria-labelledby', 'tab-' + tab);
    renderListMetrics();
    renderListTable();
  }

  /* ---------- 侧边抽屉（窄屏） ---------- */
  function closeDrawer() {
    var aside = q('#appAside');
    aside.classList.remove('is-open');
    q('#asideMask').hidden = true;
    q('#menuToggle').setAttribute('aria-expanded', 'false');
  }

  /* ---------- 初始化 ---------- */
  function init() {
    renderScanOverview();
    setPage('upload');
    setTab('gap');
    updateBadge('success');

    qa('.menu-item').forEach(function (b) {
      b.addEventListener('click', function () { setPage(b.getAttribute('data-page')); });
    });

    qa('.seg-btn').forEach(function (b) {
      b.addEventListener('click', function () {
        applyState(b.getAttribute('data-target'), b.getAttribute('data-state'));
      });
    });

    qa('[data-goto]').forEach(function (b) {
      b.addEventListener('click', function () { setPage(b.getAttribute('data-goto')); });
    });

    qa('.tab').forEach(function (b) {
      b.addEventListener('click', function () { setTab(b.getAttribute('data-tab')); });
    });

    q('#menuToggle').addEventListener('click', function () {
      var aside = q('#appAside');
      var open = !aside.classList.contains('is-open');
      aside.classList.toggle('is-open', open);
      q('#asideMask').hidden = !open;
      this.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    q('#asideMask').addEventListener('click', closeDrawer);

    document.addEventListener('click', function (e) {
      var expand = e.target.closest ? e.target.closest('[data-expand]') : null;
      if (expand) {
        toggleExpand(expand.getAttribute('data-expand'), expand);
        return;
      }
      var copy = e.target.closest ? e.target.closest('[data-copy]') : null;
      if (copy) {
        copyText(copy.getAttribute('data-copy'), copy.getAttribute('data-copy-label'));
      }
    });

    q('#runScanBtn').addEventListener('click', function () {
      messageBox({
        title: '运行治理扫描',
        message: '本次扫描将清空当前库中数据并重新计算，是否继续？',
        okText: '继续扫描',
        cancelText: '取消'
      }).then(function (ok) {
        if (!ok) { return; }
        ui.scanTriggered = true;
        setPage('scan');
        applyState('scan', 'running');
        toast('扫描已启动');
      });
    });

    q('#retryScanBtn').addEventListener('click', function () {
      messageBox({
        title: '重新运行治理扫描',
        message: '本次扫描将清空当前库中数据并重新计算，是否继续？',
        okText: '继续扫描',
        cancelText: '取消'
      }).then(function (ok) {
        if (!ok) { return; }
        ui.scanTriggered = true;
        applyState('scan', 'running');
        toast('扫描已启动');
      });
    });

    q('#downloadBtn').addEventListener('click', function () {
      messageBox({
        title: '下载结果文件',
        message: '下载的是源 CSV 原文，文件名由接口返回，本原型不发起真实下载请求。是否继续？',
        okText: '继续下载',
        cancelText: '取消'
      }).then(function (ok) {
        if (ok) { toast('下载已开始'); }
      });
    });

    applyState('upload', 'success');
    applyState('scan', 'success');
    applyState('lists', 'success');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
