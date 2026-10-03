"""Offline choices, persistence and derived reports without a server or model."""
import json
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect

from alienqa.evidence import Evidence
from alienqa.review import Decision, ReportBuilder, ReviewState
from test_ui_browser_flow import page


@pytest.fixture
def offline_report(tmp_path):
    builder = ReportBuilder(SimpleNamespace())
    builder.roles.compose_report = lambda *args, **kwargs: '<p>旧编排提到了不采信的发现</p><script>window.PWN=1</script>'
    state = ReviewState()
    state.decide('EV-B', Decision.REJECTED, '原扫描备注')
    report = builder.build([
        Evidence(id='EV-A', expectation='保存应有反馈', observation_summary='没有反馈'),
        Evidence(id='EV-B', expectation='删除应可撤销', observation_summary='无法撤销'),
    ], state, mode='analysis', scan_context={'run_id': 'offline-test', 'status': 'partial', 'incomplete': True})
    path = tmp_path / 'analysis.html'
    path.write_text(report.html, encoding='utf-8')
    return path


def test_offline_default_choices_save_reload_and_exports(page, offline_report, tmp_path):
    tab, errors = page
    tab.context.set_offline(True)
    tab.goto(offline_report.as_uri())
    rows = tab.locator('[data-offline-review]')
    expect(rows).to_have_count(2)
    for row in (rows.nth(0), rows.nth(1)):
        expect(row.get_by_role('combobox')).to_have_value('confirmed')
    rows.nth(1).get_by_role('combobox').select_option('rejected')
    attack = '<img src=x onerror="window.PWN=2">用户备注 & 内容'
    rows.nth(0).get_by_role('textbox').fill(attack)
    tab.get_by_role('button', name='保存全部选择', exact=True).click()
    expect(tab.locator('[data-review-status]')).to_contain_text('已保存到此浏览器')
    tab.reload()
    expect(rows.nth(1).get_by_role('combobox')).to_have_value('rejected')
    expect(rows.nth(0).get_by_role('textbox')).to_have_value(attack)
    expect(tab.locator('[data-selected-count]').first).to_have_text('1')
    with tab.expect_download() as downloaded:
        tab.get_by_role('button', name='导出决定与备注', exact=True).click()
    choices = tmp_path / 'choices.json'
    downloaded.value.save_as(str(choices))
    saved = json.loads(choices.read_text())
    assert saved['run_id'] == 'offline-test'
    assert saved['decisions'] == [
        {'evidence_id': 'EV-A', 'decision': 'confirmed', 'note': attack},
        {'evidence_id': 'EV-B', 'decision': 'rejected', 'note': '原扫描备注'},
    ]
    with tab.expect_download() as downloaded:
        tab.get_by_role('button', name='生成最终报告', exact=True).click()
    final = tmp_path / 'final.html'
    downloaded.value.save_as(str(final))
    assert 'EV-B' in offline_report.read_text()  # The source is never overwritten.
    tab.goto(final.as_uri())
    expect(tab.locator('.finding')).to_have_count(1)
    expect(tab.locator('.finding')).to_contain_text('EV-A')
    expect(tab.locator('.review-result')).to_contain_text(attack)
    expect(tab.locator('.stat').nth(1)).to_contain_text('最终采信')
    expect(tab.locator('body')).not_to_contain_text('删除应可撤销')
    expect(tab.locator('body')).not_to_contain_text('旧编排提到了不采信的发现')
    expect(tab.locator('body')).to_contain_text('扫描不完整')
    assert tab.locator('script, [data-offline-review]').count() == 0
    assert tab.evaluate('window.PWN') is None
    assert errors == []


@pytest.mark.parametrize('failure', ['blocked', 'corrupt'])
def test_offline_storage_failure_keeps_edit_and_can_export(page, offline_report, tmp_path, failure):
    tab, errors = page
    if failure == 'blocked':
        tab.add_init_script("Storage.prototype.setItem = function () { throw new Error('blocked'); };")
    tab.goto(offline_report.as_uri())
    if failure == 'corrupt':
        tab.evaluate("localStorage.setItem(document.querySelector('[data-review-storage-key]').dataset.reviewStorageKey, '{broken')")
        tab.reload()
        expect(tab.locator('[data-review-status]')).to_contain_text('无法恢复')
    row = tab.locator('[data-offline-review]').first
    row.get_by_role('textbox').fill('未保存也可导出')
    row.get_by_role('button', name='保存此条', exact=True).click()
    if failure == 'blocked':
        expect(row.locator('[role="status"]')).to_contain_text('保存失败')
    else:
        expect(row.locator('[role="status"]')).to_contain_text('已保存')
    expect(row.get_by_role('textbox')).to_have_value('未保存也可导出')
    with tab.expect_download() as downloaded:
        tab.get_by_role('button', name='生成最终报告', exact=True).click()
    target = tmp_path / 'export.html'
    downloaded.value.save_as(str(target))
    assert '未保存也可导出' in target.read_text()
    assert errors == []


def test_offline_reject_all_exports_explained_empty_report(page, offline_report, tmp_path):
    tab, errors = page
    tab.goto(offline_report.as_uri())
    for row in tab.locator('[data-offline-review]').all():
        row.get_by_role('combobox').select_option('rejected')
    with tab.expect_download() as downloaded:
        tab.get_by_role('button', name='生成最终报告', exact=True).click()
    final = tmp_path / 'empty-final.html'
    downloaded.value.save_as(str(final))
    tab.goto(final.as_uri())
    expect(tab.locator('.finding')).to_have_count(0)
    expect(tab.locator('body')).to_contain_text('本次没有采信的发现')
    assert tab.locator('a[href^="#"]').evaluate_all('(links) => links.every(a => document.getElementById(a.hash.slice(1)))')
    assert errors == []


def test_save_one_does_not_save_other_unsaved_edits(page, offline_report):
    tab, errors = page
    tab.goto(offline_report.as_uri())
    rows = tab.locator('[data-offline-review]')
    rows.nth(0).get_by_role('textbox').fill('只保存第一条')
    rows.nth(1).get_by_role('combobox').select_option('rejected')
    rows.nth(0).get_by_role('button', name='保存此条', exact=True).click()
    tab.reload()
    expect(rows.nth(0).get_by_role('textbox')).to_have_value('只保存第一条')
    expect(rows.nth(1).get_by_role('combobox')).to_have_value('confirmed')
    assert errors == []
