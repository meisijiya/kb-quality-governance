/* =========================================================
   企业知识库质量治理系统 Web 端原型 交互脚本（静态讨论稿）
   ---------------------------------------------------------
   约定：
   - 文案统一取自 copy.js（按 body[data-variant] 选变体），页面不写死业务文案。
   - 数值统一取自 data.js；data.js 的每个取值都由 check_prototype.py
     对回 poc/kbgovernance/ 的机读产物，页面不自行计算指标。
   - 页面派生值（如「距阈值差值」）在界面上标注为派生值。
   - 状态切换只切显隐，不发起任何网络请求。
   ========================================================= */
(function () {
  'use strict';

  var KB = window.KB;
  var COPY = window.COPY;
  var VARIANT = document.body.getAttribute('data-variant') || 'v1';
  var T = (COPY && COPY[VARIANT]) || (COPY && COPY.v1) || {};

  /* ---------- 小工具 ---------- */
  function q(sel, root) { return (root || document).querySelector(sel); }
  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function setText(node, value) { if (node) node.textContent = String(value); }
  function show(node, visible) { if (node) node.hidden = !visible; }
  function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); }
  function hasElementChild(node) {
    if (!node) return false;
    for (var i = 0; i < node.childNodes.length; i += 1) {
      if (node.childNodes[i].nodeType === 1) return true;
    }
    return false;
  }
  function fmt(value) {
    if (value === null || value === undefined) return '—';
    return String(value);
  }
  function round4(value) { return Math.round(Number(value) * 10000) / 10000; }

  /* ---------- 变量表：文案里的 {占位符} ---------- */
  function dupScanByThreshold() {
    var map = {};
    (KB.audit.dup_threshold_scan || []).forEach(function (row) { map[String(row.threshold)] = row; });
    return map;
  }

  var DUP_SCAN = dupScanByThreshold();

  var VARS = {
    n_docs: KB.metrics.n_docs,
    n_tickets: KB.metrics.n_tickets,
    n_passages: KB.metrics.n_passages,
    gap_threshold: KB.metrics.gap.threshold,
    gap_clusters: KB.metrics.gap.gap_clusters,
    gap_intents: KB.metrics.gap.detected_intents,
    gap_pool_clusters: KB.audit.gap_pool.clusters,
    corrupt_detected: KB.metrics.corrupt.detected,
    corrupt_shown: KB.audit.corrupt_sample.shown,
    corrupt_combos: KB.audit.corrupt_sample.combos,
    dup_groups: KB.metrics.dup.dup_groups,
    dup_docs: KB.metrics.dup.detected_docs,
    dup_threshold: KB.metrics.dup.threshold,
    dup_f1_095: KB.metrics.dup.group_f1,
    dup_f1_095_threshold: KB.metrics.dup.threshold,
    dup_f1_090: (DUP_SCAN['0.9'] || {}).group_f1,
    dup_f1_090_threshold: 0.9,
    req_scan_seconds: KB.audit.requirement.scan_seconds_max,
    req_page_seconds: KB.audit.requirement.page_response_seconds_max,
    run_time: String(KB.audit.run.generated_at || '').replace('T', ' ').replace('+08:00', '')
  };

  function interpolate(text, extra) {
    if (text === undefined || text === null) return '';
    return String(text).replace(/\{([a-zA-Z0-9_]+)\}/g, function (whole, key) {
      if (extra && Object.prototype.hasOwnProperty.call(extra, key)) return String(extra[key]);
      if (Object.prototype.hasOwnProperty.call(VARS, key)) return String(VARS[key]);
      return whole;
    });
  }

  function copy(key, extra) {
    if (!(key in T)) return '';
    return interpolate(T[key], extra);
  }

  /* ---------- 数值注入 ---------- */
  function resolveNum(path) {
    var parts = String(path).split('.');
    var node = KB;
    for (var i = 0; i < parts.length; i += 1) {
      if (node === null || node === undefined) return null;
      node = node[parts[i]];
    }
    return node;
  }

  function fillNumbers() {
    qa('[data-num]').forEach(function (node) {
      if (node.textContent.trim()) return;
      node.textContent = fmt(resolveNum(node.getAttribute('data-num')));
    });
  }

  /* ---------- 文案注入：叶子节点整段替换；含子节点的保留结构 ---------- */
  function fillCopy() {
    qa('[data-copy]').forEach(function (node) {
      var key = node.getAttribute('data-copy');
      if (!(key in T)) return;
      if (hasElementChild(node)) return;
      node.textContent = copy(key);
    });
  }

  /* ---------- 状态模型 ----------
     三个状态必须互相自洽（评审 A7 / 操作效率 #3）：
     - 扫描未完成（idle / running / loading / error）时，清单没有数据，
       徽标、指标与明细一律走占位符，不允许出现「未扫描却显示上一轮数字」；
     - 扫描完成（success）后清单才有数据，徽标数 = 该类判定数，
       指标与该 tab 同源，明细行数与徽标对应。
     默认落在「语料已导入、尚未扫描」这一入口状态：先导语料、再扫描、最后看清单，
     与页内「原型状态演示」开关配合可逐个状态检视。 */
  var state = {
    page: 'upload',
    upload: 'success',
    scan: 'idle',
    lists: 'never'
  };

  /* 扫描状态变化时，清单状态随之收敛，避免出现自相矛盾的组合 */
  function applyScanState(next) {
    state.scan = next;
    if (next === 'success') state.lists = 'success';
    else if (next === 'running' || next === 'loading') state.lists = 'loading';
    else if (next === 'error') state.lists = 'error';
    else state.lists = 'never';
  }

  /* 清单状态变化时，反推扫描状态：只有「有结果」才意味着扫描跑过 */
  function applyListsState(next) {
    state.lists = next;
    if (next === 'success' || next === 'nohit') state.scan = 'success';
    else if (next === 'loading') state.scan = 'loading';
    else if (next === 'error') state.scan = 'error';
    else state.scan = 'idle';
  }

  function scanLocked() { return state.scan === 'running'; }

  function scanStatusKey() {
    if (state.scan === 'running') return 'running';
    if (state.scan === 'error') return 'error';
    if (state.scan === 'success') return 'ready';
    return 'empty';
  }

  /* ---------- 播报与轻提示 ---------- */
  function announce(text) {
    var region = q('#liveRegion');
    if (region) region.textContent = String(text);
  }

  var toastTimer = null;
  function toast(text) {
    var node = q('#toast');
    if (!node) return;
    node.textContent = String(text);
    show(node, true);
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { show(node, false); }, 3200);
  }

  /* ---------- 模态框：焦点陷阱 + Esc 关闭并归还焦点 ---------- */
  var modalOpener = null;
  var modalKeyHandler = null;

  function closeModal() {
    var root = q('#modalRoot');
    if (!root || !root.firstChild) return;
    clear(root);
    if (modalKeyHandler) {
      document.removeEventListener('keydown', modalKeyHandler);
      modalKeyHandler = null;
    }
    if (modalOpener && typeof modalOpener.focus === 'function') modalOpener.focus();
    modalOpener = null;
  }

  function openModal(opts) {
    var root = q('#modalRoot');
    if (!root) return;
    /* 焦点归还目标由调用方显式指定：弹窗常在切换页面之后才打开，
       此时 document.activeElement 已是新页标题，而不是触发按钮。 */
    modalOpener = opts.opener || document.activeElement;
    clear(root);

    var mask = el('div', 'modal-mask');
    var box = el('div', 'msgbox');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-labelledby', 'msgbox-title');

    var title = el('h2', null, opts.title);
    title.id = 'msgbox-title';
    var body = el('p', null, opts.body);
    var actions = el('div', 'msgbox-actions');

    var ok = el('button', 'btn btn-primary', opts.okText);
    ok.type = 'button';
    var cancel = el('button', 'btn btn-ghost', opts.cancelText);
    cancel.type = 'button';

    ok.addEventListener('click', function () { closeModal(); if (opts.onOk) opts.onOk(); });
    cancel.addEventListener('click', function () { closeModal(); if (opts.onCancel) opts.onCancel(); });

    actions.appendChild(ok);
    actions.appendChild(cancel);
    box.appendChild(title);
    box.appendChild(body);
    box.appendChild(actions);
    mask.appendChild(box);
    root.appendChild(mask);

    modalKeyHandler = function (event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeModal();
        if (opts.onCancel) opts.onCancel();
        return;
      }
      if (event.key !== 'Tab') return;
      var focusable = qa('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])', box);
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', modalKeyHandler);
    ok.focus();
  }

  /* ---------- 页面切换：切显隐 + 移焦 + 播报 ---------- */
  function setPage(page) {
    state.page = page;
    document.body.setAttribute('data-page', page);
    var heading = null;
    qa('.page').forEach(function (section) {
      var active = section.getAttribute('data-page') === page;
      show(section, active);
      if (active) heading = q('h1', section);
    });
    qa('.nav-item').forEach(function (item) {
      if (item.getAttribute('data-page') === page) item.setAttribute('aria-current', 'page');
      else item.removeAttribute('aria-current');
    });
    if (heading) {
      heading.setAttribute('tabindex', '-1');
      heading.focus();
      announce(heading.textContent);
    }
    render();
  }

  /* ---------- 表格片段 ---------- */
  function kpi(label, value, unit) {
    var box = el('div', 'kpi');
    box.appendChild(el('span', 'kpi-label', label));
    box.appendChild(el('span', 'kpi-value', value));
    if (unit) box.appendChild(el('span', 'kpi-unit', unit));
    return box;
  }

  function headRow(container, labels) {
    clear(container);
    labels.forEach(function (label) {
      var th = el('th', null, label);
      th.setAttribute('scope', 'col');
      container.appendChild(th);
    });
  }

  function cell(row, value, cls, title) {
    var td = el('td', cls || null, value);
    if (title) td.title = title;
    row.appendChild(td);
    return td;
  }

  /* ---------- 上传页 ---------- */
  function renderUpload() {
    var locked = scanLocked();
    qa('.page[data-page="upload"] .state-block').forEach(function (block) {
      var states = (block.getAttribute('data-states') || '').split(',');
      var wanted = locked ? 'busy' : state.upload;
      show(block, states.indexOf(wanted) >= 0);
    });

    var docs = '—';
    var tickets = '—';
    if (!locked) {
      if (state.upload === 'success') { docs = fmt(KB.metrics.n_docs); tickets = fmt(KB.metrics.n_tickets); }
      else if (state.upload === 'empty') { docs = '0'; tickets = '0'; }
    }
    setText(q('#corpusDocs'), docs);
    setText(q('#corpusTickets'), tickets);

    var cta = q('#uploadCta');
    var note = q('#uploadCtaNote');
    var ctaKey = 'upload.cta.ready';
    if (locked) ctaKey = 'upload.cta.busy';
    else if (state.upload === 'empty') ctaKey = 'upload.cta.empty';
    else if (state.upload === 'loading') ctaKey = 'upload.cta.loading';
    else if (state.upload === 'error') ctaKey = 'upload.cta.error';
    setText(cta, copy(ctaKey));
    if (cta) {
      var enabled = !locked && state.upload === 'success';
      cta.disabled = !enabled;
      cta.setAttribute('aria-disabled', enabled ? 'false' : 'true');
    }
    if (note) setText(note, copy('upload.cta.note'));

    [['#docUploadInput', '#docUpload'], ['#ticketUploadInput', '#ticketUpload']].forEach(function (pair) {
      var input = q(pair[0]);
      var zone = q(pair[1]);
      if (input) input.disabled = locked;
      if (zone) {
        if (locked) zone.setAttribute('data-busy', 'true');
        else zone.removeAttribute('data-busy');
        zone.setAttribute('aria-disabled', locked ? 'true' : 'false');
      }
    });
  }

  function wireUpload() {
    [['#docUploadInput', '#docUploadFeedback'], ['#ticketUploadInput', '#ticketUploadFeedback']].forEach(function (pair) {
      var input = q(pair[0]);
      var feedback = q(pair[1]);
      if (!input) return;
      function report(name) {
        var text = copy('upload.feedback.selected', { file: name });
        setText(feedback, text);
        show(feedback, true);
        announce(text);
      }
      input.addEventListener('change', function () {
        var file = input.files && input.files[0];
        if (file) report(file.name);
      });
      var zone = input.closest ? input.closest('.dropzone') : null;
      if (!zone) return;
      ['dragenter', 'dragover'].forEach(function (type) {
        zone.addEventListener(type, function (event) { event.preventDefault(); });
      });
      zone.addEventListener('drop', function (event) {
        event.preventDefault();
        var file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
        if (file) report(file.name);
      });
    });

    var cta = q('#uploadCta');
    if (cta) {
      cta.addEventListener('click', function () {
        if (scanLocked() || state.upload !== 'success') return;
        setPage('scan');
      });
    }
    var retry = q('#uploadRetry');
    if (retry) {
      retry.addEventListener('click', function () {
        state.upload = 'loading';
        render();
        window.setTimeout(function () { state.upload = 'success'; render(); }, 600);
      });
    }
  }

  /* ---------- 扫描页 ---------- */
  function renderScan() {
    qa('.page[data-page="scan"] .state-block').forEach(function (block) {
      var states = (block.getAttribute('data-states') || '').split(',');
      show(block, states.indexOf(state.scan) >= 0);
    });

    var cta = q('#scanCta');
    if (cta) {
      var key = 'scan.cta.idle';
      if (state.scan === 'running') key = 'scan.cta.running';
      else if (state.scan === 'success') key = 'scan.cta.success';
      else if (state.scan === 'error') key = 'scan.cta.error';
      else if (state.scan === 'loading') key = 'scan.cta.loading';
      setText(cta, copy(key));
      var busy = state.scan === 'running' || state.scan === 'loading';
      cta.disabled = busy;
      cta.setAttribute('aria-disabled', busy ? 'true' : 'false');
    }

    renderScanOverview();
    renderScanTiming();
    renderThresholdScan();
  }

  var OVERVIEW_ROWS = [
    { name: '知识缺口', metric: KB.metrics.gap, unit: 'lists.unit.gap', key: 'metrics.json → gap.best' },
    { name: '内容腐化', metric: KB.metrics.corrupt, unit: 'lists.unit.corrupt', key: 'metrics.json → corrupt' },
    { name: '重复冗余', metric: KB.metrics.dup, unit: 'lists.unit.dup', key: 'metrics.json → dup.best' }
  ];

  function renderScanOverview() {
    var body = q('#scanOverviewBody');
    if (!body) return;
    clear(body);
    OVERVIEW_ROWS.forEach(function (item) {
      var m = item.metric;
      var row = el('tr');
      cell(row, item.name);
      cell(row, fmt(m.threshold), 'n');
      cell(row, fmt(m.precision), 'n');
      cell(row, fmt(m.recall), 'n');
      cell(row, fmt(m.f1), 'n');
      cell(row, fmt(m.gap_clusters !== undefined ? m.gap_clusters : (m.detected !== undefined ? m.detected : m.dup_groups)), 'n');
      cell(row, copy(item.unit));
      cell(row, item.key, 'id');
      body.appendChild(row);
    });
    var note = q('#scanOverviewNote');
    if (note) setText(note, copy('scan.overview.note'));
  }

  var TIMING_ROWS = [
    { key: 'scan.timing.stage.embed', value: function () { return KB.metrics.encode_seconds; }, artifact: 'embeddings_meta.json → encode_seconds' },
    { key: 'scan.timing.stage.cluster', value: function () { return null; }, artifact: '—' },
    { key: 'scan.timing.stage.gap', value: function () { return null; }, artifact: '—' },
    { key: 'scan.timing.stage.corrupt', value: function () { return KB.metrics.corrupt.seconds; }, artifact: 'metrics.json → corrupt.seconds' },
    { key: 'scan.timing.stage.total', value: function () { return KB.metrics.total_seconds; }, artifact: 'metrics.json → total_seconds' }
  ];

  function renderScanTiming() {
    var body = q('#scanTimingBody');
    if (!body) return;
    clear(body);
    TIMING_ROWS.forEach(function (item) {
      var value = item.value();
      var row = el('tr');
      cell(row, copy(item.key));
      cell(row, value === null ? '—' : fmt(value) + ' 秒', 'n');
      cell(row, value === null ? copy('scan.timing.range.missing') : copy('scan.timing.range.measured'));
      cell(row, item.artifact, 'id');
      body.appendChild(row);
    });
    var note = q('#scanTimingNote');
    if (note) setText(note, copy('scan.timing.note'));
  }

  function renderThresholdScan() {
    var body = q('#gapThresholdBody');
    if (!body) return;
    clear(body);
    (KB.audit.gap_threshold_scan || []).forEach(function (item) {
      var row = el('tr');
      cell(row, fmt(item.threshold), 'n');
      cell(row, fmt(item.gap_clusters), 'n');
      cell(row, fmt(item.detected_intents), 'n');
      cell(row, fmt(item.precision), 'n');
      cell(row, fmt(item.recall), 'n');
      cell(row, fmt(item.f1), 'n');
      body.appendChild(row);
    });
  }

  var scanTimers = [];
  function clearScanTimers() {
    scanTimers.forEach(function (timer) { window.clearTimeout(timer); });
    scanTimers = [];
  }

  function runScan() {
    clearScanTimers();
    applyScanState('running');
    render();
    announce(copy('scan.running.title'));
    var steps = qa('#scanSteps .step');
    var bar = q('#scanProgress .progress-bar');
    var progress = q('#scanProgress');
    steps.forEach(function (step) { step.setAttribute('data-state', 'pending'); });
    if (bar) bar.style.width = '0%';
    steps.forEach(function (step, index) {
      scanTimers.push(window.setTimeout(function () {
        step.setAttribute('data-state', 'done');
        if (bar) bar.style.width = Math.round(((index + 1) / steps.length) * 100) + '%';
        if (progress) progress.setAttribute('aria-valuetext', step.textContent);
      }, 450 * (index + 1)));
    });
    scanTimers.push(window.setTimeout(function () {
      applyScanState('success');
      render();
      announce(copy('scan.overview.title'));
    }, 450 * steps.length + 400));
  }

  function confirmScan() {
    openModal({
      title: copy('confirm.scan.title'),
      body: copy('confirm.scan.body'),
      okText: copy('confirm.scan.ok'),
      cancelText: copy('confirm.scan.cancel'),
      opener: q('#scanCta'),
      onOk: runScan
    });
  }

  function wireScan() {
    var cta = q('#scanCta');
    if (cta) {
      cta.addEventListener('click', function () {
        if (state.scan === 'success') { setPage('lists'); return; }
        if (state.scan === 'running' || state.scan === 'loading') return;
        confirmScan();
      });
    }
    var cancel = q('#cancelScanBtn');
    if (cancel) {
      cancel.addEventListener('click', function () {
        clearScanTimers();
        applyScanState('idle');
        render();
        announce(copy('scan.cta.idle'));
      });
    }
    var retry = q('#retryScanBtn');
    if (retry) retry.addEventListener('click', confirmScan);
  }

  /* ---------- 清单页 ---------- */
  var TABS = ['gap', 'corrupt', 'dup'];

  function tabUnit(tab) {
    if (tab === 'gap') return copy('lists.unit.gap');
    if (tab === 'corrupt') return copy('lists.unit.corrupt');
    return copy('lists.unit.dup');
  }

  function tabMetrics(tab) {
    if (tab === 'gap') {
      var g = KB.metrics.gap;
      return { threshold: g.threshold, precision: g.precision, recall: g.recall, f1: g.f1, count: g.gap_clusters };
    }
    if (tab === 'corrupt') {
      var c = KB.metrics.corrupt;
      return { threshold: c.threshold, precision: c.precision, recall: c.recall, f1: c.f1, count: c.detected };
    }
    var d = KB.metrics.dup;
    return { threshold: d.threshold, precision: d.group_precision, recall: d.group_recall, f1: d.group_f1, count: d.dup_groups };
  }

  function tabHead(tab) {
    if (tab === 'gap') {
      return ['lists.table.head.gap1', 'lists.table.head.gap2', 'lists.table.head.gap3', 'lists.table.head.gap4', 'lists.table.head.gap5'];
    }
    if (tab === 'corrupt') {
      return ['lists.table.head.corrupt1', 'lists.table.head.corrupt2', 'lists.table.head.corrupt3', 'lists.table.head.corrupt4', 'lists.table.head.corrupt5', 'lists.table.head.corrupt6'];
    }
    return ['lists.table.head.dup1', 'lists.table.head.dup2', 'lists.table.head.dup3', 'lists.table.head.dup4'];
  }

  /* 各清单里由页面自己算出来的列（其余列都是产物里的原值）：
     缺口清单的「距阈值差值」= 判定阈值 − 覆盖度中位数；
     腐化清单的「规则命中组合」由产物的 rule_hits 归并而来。
     这些列在表头就写明是派生值——只写在单元格的 title 里等于没说。 */
  function derivedColumnIndex(tab) {
    if (tab === 'gap') return 4;
    if (tab === 'corrupt') return 4;
    return -1;
  }

  function tabCaption(tab) {
    return copy('lists.detail.caption.' + tab);
  }

  function tabDesc(tab) {
    return copy('lists.detail.desc.' + tab);
  }

  function ruleCodes(ruleHits) {
    if (!ruleHits) return '—';
    return String(ruleHits).split('|').map(function (part) {
      return String(part).split('_')[0];
    }).join('+');
  }

  function renderListMetrics() {
    var grid = q('#listMetricGrid');
    var sub = q('#listCaliGrid');
    var note = q('#listUnitNote');
    var ready = state.lists === 'success';
    var m = tabMetrics(state.tab);
    if (grid) {
      clear(grid);
      grid.appendChild(kpi(copy('lists.metrics.threshold'), ready ? fmt(m.threshold) : '—'));
      grid.appendChild(kpi(copy('lists.metrics.precision'), ready ? fmt(m.precision) : '—'));
      grid.appendChild(kpi(copy('lists.metrics.recall'), ready ? fmt(m.recall) : '—'));
      grid.appendChild(kpi(copy('lists.metrics.f1'), ready ? fmt(m.f1) : '—'));
      grid.appendChild(kpi(copy('lists.metrics.count'), ready ? fmt(m.count) : '—', tabUnit(state.tab)));
    }
    if (sub) {
      clear(sub);
      sub.appendChild(kpi(copy('lists.metrics.unit'), tabUnit(state.tab)));
    }
    if (note) setText(note, ready ? copy('lists.metrics.countNote') : copy('lists.metrics.thresholdNote'));
  }

  function detailRow(pairs) {
    var row = el('tr', 'detail-row');
    var td = el('td');
    td.setAttribute('colspan', '8');
    var grid = el('div', 'detail-grid');
    pairs.forEach(function (pair) {
      var item = el('div', 'detail-item');
      item.appendChild(el('dt', null, pair[0]));
      item.appendChild(el('dd', null, pair[1]));
      grid.appendChild(item);
    });
    td.appendChild(grid);
    row.appendChild(td);
    return row;
  }

  function appendExpandCell(row, index, label, build) {
    var td = el('td', 'action-cell');
    var button = el('button', 'btn btn-sm', copy('lists.btn.expand'));
    button.type = 'button';
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-label', copy('lists.expand', { n: index, label: label }));
    var detail = null;
    button.addEventListener('click', function () {
      var expanded = button.getAttribute('aria-expanded') === 'true';
      if (expanded) {
        if (detail && detail.parentNode) detail.parentNode.removeChild(detail);
        detail = null;
        button.setAttribute('aria-expanded', 'false');
        button.setAttribute('aria-label', copy('lists.expand', { n: index, label: label }));
        setText(button, copy('lists.btn.expand'));
        return;
      }
      detail = build();
      row.parentNode.insertBefore(detail, row.nextSibling);
      button.setAttribute('aria-expanded', 'true');
      button.setAttribute('aria-label', copy('lists.collapse', { n: index, label: label }));
      setText(button, copy('lists.btn.collapse'));
    });
    td.appendChild(button);
    row.appendChild(td);
  }

  function renderListTable() {
    var head = q('#listHead');
    var body = q('#listBody');
    var caption = q('#listCaption');
    if (!head || !body) return;
    var derived = copy('lists.derived');
    var labels = tabHead(state.tab).map(function (key) { return copy(key); });
    /* 页面自己算出来的列（缺口清单的「距阈值差值」、腐化清单的「规则命中组合」）
       在表头就写明是派生值——只写在单元格的 title 里等于没说。 */
    var dIndex = derivedColumnIndex(state.tab);
    if (dIndex >= 0 && labels[dIndex]) labels[dIndex] += '（' + derived + '）';
    headRow(head, labels.concat([copy('lists.table.action')]));
    if (caption) setText(caption, tabCaption(state.tab));
    clear(body);

    if (state.tab === 'gap') {
      (KB.gaps || []).forEach(function (item, index) {
        var row = el('tr');
        cell(row, fmt(item.rank), 'n');
        cell(row, item.intent);
        cell(row, fmt(item.size), 'n');
        cell(row, fmt(item.cover_median), 'n');
        cell(row, fmt(round4(KB.metrics.gap.threshold - item.cover_median)), 'n', derived);
        appendExpandCell(row, index + 1, item.intent, function () {
          return detailRow([
            [copy('lists.detail.rep'), item.rep_ticket + ' · ' + item.rep_text],
            [copy('lists.table.head.gap3'), fmt(item.size)],
            [copy('lists.table.head.gap4'), fmt(item.cover_median)]
          ]);
        });
        body.appendChild(row);
      });
    } else if (state.tab === 'corrupt') {
      (KB.corrupt || []).forEach(function (item, index) {
        var row = el('tr');
        cell(row, item.doc_id, 'id');
        cell(row, item.title, 'truncate', item.title);
        cell(row, item.category);
        cell(row, item.last_modified, 'id');
        cell(row, ruleCodes(item.rule_hits));
        cell(row, fmt(item.risk_score), 'n');
        appendExpandCell(row, index + 1, item.doc_id, function () {
          return detailRow([
            [copy('lists.detail.reason'), item.reasons],
            [copy('lists.table.head.corrupt6'), fmt(item.risk_score)]
          ]);
        });
        body.appendChild(row);
      });
    } else {
      (KB.dups || []).forEach(function (item, index) {
        var row = el('tr');
        cell(row, fmt(item.group), 'n');
        cell(row, fmt(item.size), 'n');
        cell(row, item.primary_doc, 'id');
        cell(row, fmt(item.max_sim), 'n');
        appendExpandCell(row, index + 1, item.primary_doc, function () {
          return detailRow([
            [copy('lists.detail.members'), String(item.member_docs).split('|').join('、')],
            [copy('lists.table.head.dup4'), fmt(item.max_sim)]
          ]);
        });
        body.appendChild(row);
      });
    }
  }

  function extraTable(headers, rows) {
    var wrap = el('div', 'tbl-wrap');
    var table = el('table', 'tbl');
    var thead = el('thead');
    var hrow = el('tr');
    headers.forEach(function (label) {
      var th = el('th', null, label);
      th.setAttribute('scope', 'col');
      hrow.appendChild(th);
    });
    thead.appendChild(hrow);
    table.appendChild(thead);
    var tbody = el('tbody');
    rows.forEach(function (cells) {
      var row = el('tr');
      cells.forEach(function (value, index) {
        cell(row, value, index === 0 ? null : 'n');
      });
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderListExtra() {
    var host = q('#listTabExtra');
    if (!host) return;
    clear(host);
    if (state.lists !== 'success') return;

    var section = el('section', 'panel');
    var head = el('div', 'panel-head');

    if (state.tab === 'gap') {
      head.appendChild(el('h2', 'panel-title', copy('lists.gap.extraTitle')));
      section.appendChild(head);
      section.appendChild(el('p', 'note', copy('lists.gap.extraNote')));
      section.appendChild(extraTable(
        [copy('lists.table.head.gap2'), copy('lists.table.head.gap3'), copy('lists.table.head.gap4')],
        (KB.audit.gap_near_miss || []).map(function (item) {
          return [item.intent, fmt(item.size), fmt(item.cover_median)];
        })
      ));
    } else if (state.tab === 'corrupt') {
      head.appendChild(el('h2', 'panel-title', copy('lists.corrupt.extraTitle')));
      section.appendChild(head);
      section.appendChild(el('p', 'note', copy('lists.corrupt.extraNote')));
      section.appendChild(extraTable(
        [copy('lists.extra.comboCol1'), copy('lists.extra.comboCol2')],
        (KB.audit.corrupt_rule_combos || []).map(function (item) {
          return [item.rules, fmt(item.docs)];
        })
      ));
      section.appendChild(el('h3', 'panel-title', copy('lists.corrupt.weightTitle')));
      section.appendChild(extraTable(
        [copy('lists.extra.weightCol1'), copy('lists.extra.weightCol2'), copy('lists.extra.weightCol3')],
        Object.keys(KB.metrics.corrupt.rule_weight || {}).map(function (rule) {
          return [rule, fmt(KB.metrics.corrupt.rule_weight[rule]), fmt((KB.metrics.corrupt.rule_hit_counts || {})[rule])];
        })
      ));
    } else {
      head.appendChild(el('h2', 'panel-title', copy('lists.dup.extraTitle')));
      section.appendChild(head);
      section.appendChild(el('p', 'note', copy('lists.dup.extraNote')));
      section.appendChild(extraTable(
        [copy('lists.extra.dupCol3'), copy('lists.extra.dupCol4'), copy('lists.extra.dupCol5')],
        (KB.audit.dup_threshold_scan || []).map(function (item) {
          return [fmt(item.threshold), fmt(item.group_f1), fmt(item.detected_docs)];
        })
      ));
    }
    host.appendChild(section);
  }

  function renderDownloads() {
    var body = q('#downloadBody');
    if (!body) return;
    clear(body);
    var products = KB.audit.products || {};
    TABS.forEach(function (key) {
      var item = products[key];
      if (!item) return;
      var row = el('tr');
      cell(row, item.label);
      cell(row, item.path, 'id');
      body.appendChild(row);
    });
  }

  function renderLists() {
    qa('#listPanel .state-block').forEach(function (block) {
      var key = block.getAttribute('data-list') || '';
      var active = key === state.lists;
      show(block, active);
      /* 加载态的 aria-busy 挂在真正会被替换的那个容器上：
         读屏据此知道该区域正在更新，而不是读到一段空白骨架。 */
      if (active && key === 'loading') block.setAttribute('aria-busy', 'true');
      else block.removeAttribute('aria-busy');
    });
    qa('.page[data-page="lists"] .tab').forEach(function (button) {
      var selected = button.getAttribute('data-tab') === state.tab;
      button.setAttribute('aria-selected', selected ? 'true' : 'false');
      button.tabIndex = selected ? 0 : -1;
    });

    var desc = q('#listDetailDesc');
    if (desc) setText(desc, state.lists === 'success' ? tabDesc(state.tab) : '');
    var caption = q('#listCaption');
    if (caption) setText(caption, tabCaption(state.tab));

    var stateNote = q('#listStateNote');
    if (stateNote) {
      var key = 'lists.tabnote.' + (state.lists === 'success' ? 'success' : state.lists);
      setText(stateNote, copy(key in T ? key : 'lists.tabnote.success'));
    }

    renderListMetrics();
    renderListTable();
    renderListExtra();

    var badgeValue = function (tab) {
      if (state.lists !== 'success') return '—';
      return fmt(tabMetrics(tab).count);
    };
    setText(q('#badge-gap'), badgeValue('gap'));
    setText(q('#badge-corrupt'), badgeValue('corrupt'));
    setText(q('#badge-dup'), badgeValue('dup'));

    var cta = q('#listsCta');
    if (cta) {
      var key = 'lists.cta.' + (state.lists === 'success' ? 'success' : state.lists);
      setText(cta, copy(key in T ? key : 'lists.cta.success'));
      var busy = state.lists === 'loading';
      cta.disabled = busy;
      cta.setAttribute('aria-disabled', busy ? 'true' : 'false');
    }
    var ctaNote = q('#listsCtaNote');
    if (ctaNote) setText(ctaNote, copy('lists.cta.note'));
  }

  function reloadLists() {
    applyListsState('loading');
    render();
    window.setTimeout(function () {
      applyListsState('success');
      render();
      toast(copy('toast.reloaded'));
    }, 500);
  }

  function wireLists() {
    qa('.page[data-page="lists"] .tab').forEach(function (button) {
      button.addEventListener('click', function () {
        state.tab = button.getAttribute('data-tab');
        render();
        announce(button.textContent);
      });
      button.addEventListener('keydown', function (event) {
        var tabs = qa('.page[data-page="lists"] .tab');
        var index = tabs.indexOf(button);
        var next = null;
        if (event.key === 'ArrowRight') next = tabs[(index + 1) % tabs.length];
        else if (event.key === 'ArrowLeft') next = tabs[(index - 1 + tabs.length) % tabs.length];
        else if (event.key === 'Home') next = tabs[0];
        else if (event.key === 'End') next = tabs[tabs.length - 1];
        if (!next) return;
        event.preventDefault();
        state.tab = next.getAttribute('data-tab');
        render();
        next.focus();
      });
    });

    var cta = q('#listsCta');
    if (cta) {
      cta.addEventListener('click', function () {
        if (state.lists === 'never') { setPage('scan'); return; }
        if (state.lists === 'nohit' || state.lists === 'error') { reloadLists(); return; }
        if (state.lists !== 'success') return;
        var product = (KB.audit.products || {})[state.tab];
        if (!product) return;
        setText(q('#downloadReceipt'), copy('lists.download.receipt', { product: product.label, path: product.path }));
        toast(copy('toast.download'));
      });
    }
    var retry = q('#listsRetry');
    if (retry) retry.addEventListener('click', reloadLists);
    var gotoScan = q('#listsGotoScan');
    if (gotoScan) gotoScan.addEventListener('click', function () { setPage('scan'); });
  }

  /* ---------- 状态演示开关 ---------- */
  function wireDemo() {
    qa('.seg-btn[data-target]').forEach(function (button) {
      button.addEventListener('click', function () {
        var target = button.getAttribute('data-target');
        var next = button.getAttribute('data-state');
        if (target === 'upload') state.upload = next;
        else if (target === 'scan') applyScanState(next === 'empty' ? 'idle' : next);
        else applyListsState(next);
        render();
      });
    });
  }

  function syncDemoButtons() {
    qa('.seg-btn[data-target]').forEach(function (button) {
      var target = button.getAttribute('data-target');
      var next = button.getAttribute('data-state');
      var current = target === 'upload' ? state.upload
        : (target === 'scan' ? (state.scan === 'idle' ? 'empty' : state.scan) : state.lists);
      button.setAttribute('aria-pressed', current === next ? 'true' : 'false');
    });
  }

  /* ---------- 侧栏状态与抽屉 ---------- */
  function renderStatus() {
    var dot = q('#statusDot');
    var text = q('#statusText');
    var key = scanStatusKey();
    if (dot) dot.setAttribute('data-tone', key === 'ready' ? 'ok' : (key === 'running' ? 'warn' : (key === 'error' ? 'bad' : 'idle')));
    if (text) setText(text, copy('status.' + key));
  }

  function wireChrome() {
    qa('.nav-item').forEach(function (item) {
      item.addEventListener('click', function () { setPage(item.getAttribute('data-page')); });
    });
    var statusLink = q('#statusLink');
    if (statusLink) statusLink.addEventListener('click', function () { setPage(statusLink.getAttribute('data-goto') || 'scan'); });

    var toggle = q('#menuToggle');
    var scrim = q('#drawerScrim');
    function setDrawer(open) {
      document.body.setAttribute('data-drawer', open ? 'open' : 'closed');
      if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      show(scrim, open);
    }
    if (toggle) {
      toggle.addEventListener('click', function () {
        setDrawer(document.body.getAttribute('data-drawer') !== 'open');
      });
    }
    if (scrim) scrim.addEventListener('click', function () { setDrawer(false); });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && document.body.getAttribute('data-drawer') === 'open') setDrawer(false);
    });
    setDrawer(false);
  }

  /* ---------- 总渲染 ---------- */
  function render() {
    renderUpload();
    renderScan();
    renderLists();
    renderDownloads();
    renderStatus();
    syncDemoButtons();
  }

  function init() {
    fillNumbers();
    fillCopy();
    wireUpload();
    wireScan();
    wireLists();
    wireDemo();
    wireChrome();
    var bar = q('#scanProgress .progress-bar');
    if (bar) bar.style.width = '0%';
    setPage('upload');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
}());
