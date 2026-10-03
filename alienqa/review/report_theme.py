"""Embedded report styles: no network or additional build step."""

REPORT_STYLE = """
<style>
  :root {
    color-scheme: light;
    --paper: #f5f6f3; --surface: #fff; --ink: #202e2b; --muted: #62716c;
    --line: #e1e7e1; --accent: #186951; --soft: #edf5ef;
    --amber: #805916; --amber-soft: #fff7e8;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; scroll-padding-top: 28px; }
  body { margin: 0; background: var(--paper); color: var(--ink);
    font: 15px/1.75 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    -webkit-font-smoothing: antialiased; overflow-wrap: anywhere; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  a:focus-visible, summary:focus-visible, button:focus-visible, select:focus-visible, textarea:focus-visible {
    outline: 3px solid #67ac8b; outline-offset: 4px; border-radius: 4px; }
  .skip-link { position: absolute; top: -100px; left: 20px; z-index: 10; background: var(--surface); padding: 12px; }
  .skip-link:focus { top: 12px; }
  .site-header { max-width: 1240px; margin: auto; padding: 26px 36px;
    display: flex; align-items: center; justify-content: space-between; gap: 20px; }
  .brand { display: flex; align-items: center; gap: 12px; font-weight: 750; font-size: 19px; letter-spacing: -.6px; }
  .brand-mark { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 11px;
    background: var(--ink); color: #d4efb9; font: 700 19px/1 ui-monospace, monospace; }
  .header-label, .eyebrow { color: var(--muted); font: 650 11px/1.5 ui-monospace, SFMono-Regular, monospace;
    letter-spacing: 1.5px; text-transform: uppercase; }
  .header-label { padding: 6px 12px; border: 1px solid var(--line); border-radius: 99px; letter-spacing: .7px; }
  .report-shell { max-width: 1240px; margin: auto; padding: 12px 36px 64px; }
  .report-layout { display: grid; grid-template-columns: 188px minmax(0, 1fr); gap: 36px; align-items: start; }
  .report-nav { position: sticky; top: 28px; padding: 18px 0; }
  .report-nav .eyebrow { display: block; padding: 0 12px; margin-bottom: 14px; }
  .report-nav a { display: block; padding: 9px 12px; border-radius: 8px; color: var(--muted); font-size: 13px; }
  .report-nav a:hover { color: var(--accent); background: #e8eee8; text-decoration: none; }
  .report-nav .nav-primary { color: var(--ink); font-weight: 650; }
  .nav-findings { border-top: 1px solid var(--line); margin-top: 16px; padding-top: 12px;
    max-height: 46vh; overflow-y: auto; }
  .nav-findings a { display: flex; gap: 8px; align-items: baseline; }
  .nav-findings .nav-number { color: var(--accent); font: 12px/1.8 ui-monospace, monospace; }
  .report-content { min-width: 0; }
  h1, h2, h3, h4, p, figure { margin: 0; }
  h1 { font-size: clamp(26px, 3vw, 38px); font-weight: 720; line-height: 1.35; letter-spacing: -1.2px; margin: 12px 0; }
  h2 { font-size: 21px; line-height: 1.5; font-weight: 680; letter-spacing: -.4px; }
  h3 { font-size: 15px; font-weight: 680; margin: 22px 0 8px; }
  h4 { font-size: 14px; margin: 18px 0 8px; }
  p + p { margin-top: 10px; }
  .hero { padding: 18px 0 28px; }
  .hero-copy { max-width: 630px; color: var(--muted); }
  .run-label { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 18px; }
  .run-label code { background: transparent; padding: 0; font-size: 12px; color: var(--muted); }
  .badge { display: inline-flex; align-items: center; padding: 3px 10px; border-radius: 99px;
    background: var(--soft); color: var(--accent); font-size: 12px; font-weight: 650; }
  .badge-neutral { background: #eef1ef; color: #50615a; }
  .badge-major, .badge-critical { background: #fceeea; color: #a33e31; }
  .badge-minor, .badge-partial { background: var(--amber-soft); color: var(--amber); }
  .stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 26px; }
  .stat { border: 1px solid var(--line); border-radius: 14px; padding: 18px 20px; background: var(--surface); }
  .stat:first-child { background: var(--ink); color: #fff; border-color: var(--ink); }
  .stat-label { font-size: 12px; color: var(--muted); }
  .stat:first-child .stat-label, .stat:first-child .stat-note { color: #bad0c7; }
  .stat-value { font-size: 34px; letter-spacing: -1px; line-height: 1.3; font-weight: 650; margin: 5px 0; }
  .stat-note { font-size: 11px; color: var(--muted); }
  .offline-toolbar { margin-top: 18px; padding: 18px; background: #edf2ed; border-radius: 12px; font-size: 12px; color: var(--muted); }
  .review-actions, .review-row-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
  button { appearance: none; font-family: inherit; font-size: 12px; font-weight: 600; line-height: 1.5;
    background: var(--surface); color: var(--ink); border: 1px solid #cad5cb; border-radius: 8px;
    padding: 9px 14px; cursor: pointer; }
  button:hover { background: #e6efe7; border-color: #91b39b; }
  button:disabled { cursor: not-allowed; opacity: .5; }
  .primary-button { background: var(--accent); color: #fff; border-color: var(--accent); }
  .primary-button:hover { background: #12533e; border-color: #12533e; }
  [data-review-status] { margin-top: 12px; }
  .review-controls { border-top: 1px solid var(--line); padding-top: 18px; margin-top: 6px; }
  .review-controls label { display: block; font-size: 12px; font-weight: 600; margin-bottom: 12px; }
  select, textarea { display: block; width: 100%; font: inherit; color: var(--ink); background: #fbfcfa;
    border: 1px solid #ced9cf; border-radius: 8px; padding: 10px 12px; margin-top: 7px; }
  select { max-width: 200px; }
  textarea { resize: vertical; min-height: 82px; }
  .review-row-actions [role="status"] { font-size: 12px; color: var(--muted); }
  .review-result { border-top: 1px solid var(--line); margin-top: 16px; padding-top: 4px; }
  .review-result p { white-space: pre-wrap; font-size: 13px; }
  .panel, .finding { background: var(--surface); border: 1px solid var(--line); border-radius: 16px;
    padding: 26px; margin-bottom: 22px; box-shadow: 0 3px 12px #24352a03; }
  .section-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;
    gap: 12px; margin-bottom: 18px; }
  .section-heading .eyebrow { font-size: 10px; }
  .section-description { color: var(--muted); font-size: 13px; margin: -7px 0 20px; }
  .metadata { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px 28px; margin: 0 0 20px; }
  .metadata dt { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
  .metadata dd { margin: 0; font-size: 13px; }
  .warning { color: #744f15; background: var(--amber-soft); border: 1px solid #ead8b3; border-radius: 10px;
    padding: 16px 18px; font-size: 13px; margin: 16px 0; }
  .warning pre { background: #fffaf1; border-color: #ead8b3; }
  .empty-state { padding: 24px; border: 1px dashed #c8d6ca; border-radius: 12px; color: var(--muted); background: #fafcf9; }
  .finding-heading { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
  .finding-number { font: 650 12px/1 ui-monospace, monospace; color: var(--muted); }
  .finding-title { font-size: 20px; margin: 0 0 20px; }
  .comparison { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin: 18px 0; }
  .comparison > div { background: #f2f7f3; border: 1px solid #e0ebe2; border-radius: 12px; padding: 18px; }
  .comparison > div:last-child { background: #f8f7f3; border-color: #ebe8df; }
  .comparison h3 { margin: 0 0 10px; color: var(--muted); font-size: 12px; }
  .comparison p { font-size: 14px; }
  .reasoning { color: var(--muted); font-size: 13px; margin: 16px 0; }
  .screenshots { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin: 12px 0 20px; }
  figure { min-width: 0; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; background: #f7f9f6; }
  figcaption { color: var(--muted); font-size: 12px; padding: 9px 13px; border-bottom: 1px solid var(--line); }
  img { display: block; max-width: 100%; height: auto; }
  figure img { width: 100%; }
  .screenshots > p { padding: 20px; background: #f7f9f6; border-radius: 10px; color: var(--muted); font-size: 12px; }
  details { border-top: 1px solid var(--line); padding: 12px 0; }
  details + details { margin-top: 2px; }
  summary { cursor: pointer; color: var(--ink); font-size: 13px; font-weight: 600; }
  details[open] > summary { margin-bottom: 16px; color: var(--accent); }
  details details { margin-top: 12px; }
  .step-heading { display: inline-flex; max-width: calc(100% - 18px); vertical-align: baseline;
    gap: 12px; flex-wrap: wrap; align-items: baseline; }
  .step-heading small { color: var(--muted); font-weight: 400; }
  pre { margin: 10px 0; padding: 16px; border: 1px solid #e6ebe5; border-radius: 9px; background: #f7f9f6;
    font: 12px/1.8 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
  code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: .88em; background: #eff3ee; padding: 2px 5px; border-radius: 4px; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }
  th, td { border-bottom: 1px solid var(--line); padding: 10px 12px; text-align: left; vertical-align: top; }
  th { color: var(--muted); font-weight: 500; background: #f7f9f6; width: 27%; }
  ol, ul { padding-left: 22px; margin: 10px 0; }
  li + li { margin-top: 6px; }
  blockquote { border-left: 3px solid var(--accent); padding-left: 18px; color: var(--muted); margin-left: 0; }
  hr { border: 0; border-top: 1px solid var(--line); margin: 24px 0; }
  .report-footer { border-top: 1px solid var(--line); padding-top: 20px; font-size: 12px; color: var(--muted);
    display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .report-footer a { font-weight: 600; }
  @media (min-width: 900px) { .report-nav { border-right: 1px solid var(--line); padding-right: 12px; } }
  @media (max-width: 899px) {
    .site-header { padding: 20px 24px; }
    .report-shell { padding: 0 24px 40px; }
    .report-layout { display: block; }
    .report-nav { position: static; padding: 0 0 12px; display: flex; flex-wrap: wrap; gap: 4px; }
    .report-nav .eyebrow, .nav-findings { display: none; }
    .report-nav a { padding: 7px 10px; }
    .hero { padding-top: 12px; }
  }
  @media (max-width: 560px) {
    .site-header { padding: 18px 16px; }
    .header-label { font-size: 9px; }
    .report-shell { padding: 0 16px 32px; }
    .stats { gap: 8px; }
    .stat { padding: 12px; border-radius: 10px; }
    .stat-value { font-size: 28px; }
    .stat-note { font-size: 10px; }
    .panel, .finding { padding: 18px; border-radius: 12px; }
    .comparison, .screenshots, .metadata { grid-template-columns: 1fr; }
    .finding-title { font-size: 18px; }
    th, td { padding: 8px; }
  }
  @media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }
  @media print {
    body { background: #fff; font-size: 11px; }
    .site-header { padding: 0 0 16px; }
    .report-shell { padding: 0; max-width: none; }
    .report-layout { display: block; }
    .report-nav, .skip-link, .report-footer a, .offline-toolbar, .review-controls button,
    .review-row-actions [role="status"] { display: none; }
    .panel, .finding { box-shadow: none; border-radius: 0; padding: 16px; }
    .stat:first-child { background: #fff; color: var(--ink); border-color: var(--line); }
    .stat:first-child .stat-label, .stat:first-child .stat-note { color: var(--muted); }
    .comparison, figure, .stat { break-inside: avoid; }
    details > * { display: block !important; }
    details > summary { list-style: none; margin-bottom: 10px; }
    pre { font-size: 9px; }
  }
</style>
"""
