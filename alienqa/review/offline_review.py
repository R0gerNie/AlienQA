"""Trusted, embedded offline review UI; user content never becomes active markup."""

OFFLINE_REVIEW_SCRIPT = r"""<script id="alienqa-offline-review">
(function () {
  'use strict';
  const root = document.querySelector('[data-offline-report]');
  if (!root) return;
  const rows = Array.from(root.querySelectorAll('[data-offline-review]'));
  const status = root.querySelector('[data-review-status]');
  const key = 'alienqa:offline-review:v1:' + location.href.split('#')[0] + ':' + root.dataset.runId;
  root.dataset.reviewStorageKey = key;
  const defaults = rows.map(row => ({evidence_id: row.dataset.offlineReview, decision: 'confirmed',
    note: row.querySelector('textarea').value}));
  let persisted = defaults;
  function choices() {
    return rows.map(row => ({evidence_id: row.dataset.offlineReview,
      decision: row.querySelector('select').value, note: row.querySelector('textarea').value}));
  }
  function envelope(decisions) {
    return {schema_version: 1, run_id: root.dataset.runId, report_mode: root.dataset.reportMode,
      exported_at: new Date().toISOString(), decisions: decisions};
  }
  function valid(data) {
    return data && data.schema_version === 1 && data.run_id === root.dataset.runId &&
      data.report_mode === root.dataset.reportMode && Array.isArray(data.decisions) &&
      data.decisions.length === defaults.length && data.decisions.every((item, i) => item &&
        item.evidence_id === defaults[i].evidence_id && ['confirmed', 'rejected'].includes(item.decision) &&
        typeof item.note === 'string');
  }
  function updateCount() {
    const count = choices().filter(item => item.decision === 'confirmed').length;
    root.querySelectorAll('[data-selected-count]').forEach(el => { el.textContent = String(count); });
  }
  function save(onlyRow) {
    const current = choices();
    const next = onlyRow ? persisted.map((item, i) => rows[i] === onlyRow ? current[i] : item) : current;
    try {
      localStorage.setItem(key, JSON.stringify(envelope(next)));
      persisted = next;
      (onlyRow ? [onlyRow] : rows).forEach(row => {
        row.querySelector('[role="status"]').textContent = '已保存到此浏览器';
      });
      status.textContent = onlyRow ? '此条选择与备注已保存到此浏览器。' : '全部选择与备注已保存到此浏览器。';
    } catch (_) {
      const message = '保存失败：此浏览器不允许本机存储。编辑内容已保留，仍可导出。';
      status.textContent = message;
      (onlyRow ? [onlyRow] : rows).forEach(row => { row.querySelector('[role="status"]').textContent = message; });
    }
  }
  try {
    const stored = localStorage.getItem(key);
    if (stored !== null) {
      const data = JSON.parse(stored);
      if (!valid(data)) throw new Error('invalid offline review');
      persisted = data.decisions;
      rows.forEach((row, i) => {
        row.querySelector('select').value = persisted[i].decision;
        row.querySelector('textarea').value = persisted[i].note;
        row.querySelector('[role="status"]').textContent = '已恢复本机保存的选择';
      });
      status.textContent = '已恢复此浏览器保存的选择与备注。';
    }
  } catch (_) {
    status.textContent = '无法恢复本机选择；当前默认全部采信。可以重新保存或直接导出。';
  }
  rows.forEach(row => {
    row.querySelector('button').disabled = false;
    row.querySelector('button').addEventListener('click', () => save(row));
    row.querySelectorAll('select, textarea').forEach(input => input.addEventListener('input', () => {
      row.querySelector('[role="status"]').textContent = '有未保存的更改';
      status.textContent = '选择已更新；可保存到此浏览器或直接导出。';
      updateCount();
    }));
  });
  function download(text, filename, mime) {
    const url = URL.createObjectURL(new Blob([text], {type: mime}));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = filename;
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function finalReport() {
    const selected = new Map(choices().map(item => [item.evidence_id, item]));
    const accepted = Array.from(selected.values()).filter(item => item.decision === 'confirmed');
    const clone = document.documentElement.cloneNode(true);
    clone.querySelectorAll('.finding').forEach(card => {
      const controls = card.querySelector('[data-offline-review]');
      const item = selected.get(controls.dataset.offlineReview);
      if (item.decision === 'rejected') { card.remove(); return; }
      const result = document.createElement('div');
      result.className = 'review-result';
      const heading = document.createElement('h3'); heading.textContent = '开发者选择 · 采信';
      const note = document.createElement('p'); note.textContent = item.note || '未填写备注';
      result.appendChild(heading); result.appendChild(note);
      controls.replaceWith(result);
    });
    clone.querySelectorAll('[data-finding-link]').forEach(link => {
      if (selected.get(link.dataset.findingLink).decision === 'rejected') link.remove();
    });
    clone.querySelectorAll('script, .offline-toolbar, .model-supplement, noscript').forEach(el => el.remove());
    const report = clone.querySelector('[data-offline-report]');
    report.removeAttribute('data-offline-report'); report.removeAttribute('data-review-storage-key');
    clone.querySelector('title').textContent = 'AlienQA 采信发现报告';
    clone.querySelector('.hero h1').textContent = '采信发现报告';
    clone.querySelector('.hero-copy').textContent = '基于用户在离线报告中的选择，展示 ' + accepted.length +
      ' 条采信发现。原始分析报告仍保留全部发现；本报告不代表完整覆盖或证明产品无问题。';
    clone.querySelector('[data-displayed-count]').textContent = String(accepted.length);
    clone.querySelectorAll('[data-selected-count]').forEach(el => {
      el.textContent = String(accepted.length);
      el.closest('.stat').querySelector('.stat-label').textContent = '最终采信';
      el.closest('.stat').querySelector('.stat-note').textContent = '依据导出时的用户选择';
    });
    clone.querySelector('[data-findings-count]').textContent = accepted.length + ' 条采信发现';
    if (accepted.length === 0) {
      const empty = document.createElement('p'); empty.className = 'empty-state';
      empty.textContent = '本次没有采信的发现；此结果不代表已覆盖所有功能或证明产品无问题。';
      const container = clone.querySelector('#findings');
      container.querySelectorAll('.empty-state').forEach(el => el.remove());
      container.appendChild(empty);
    }
    download('<!doctype html>\n' + clone.outerHTML, 'alienqa-final-report.html', 'text/html;charset=utf-8');
    status.textContent = '已导出最终报告，包含 ' + accepted.length + ' 条采信发现；原始报告未修改。';
  }
  const actions = {
    save: () => save(null),
    decisions: () => { download(JSON.stringify(envelope(choices()), null, 2),
      'alienqa-decisions.json', 'application/json;charset=utf-8'); status.textContent = '已导出当前全部决定与备注。'; },
    final: finalReport
  };
  root.querySelectorAll('[data-review-action]').forEach(button => {
    button.disabled = false;
    button.addEventListener('click', actions[button.dataset.reviewAction]);
  });
  updateCount();
})();
</script>"""
