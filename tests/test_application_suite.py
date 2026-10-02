"""Suite planning has separate autonomous and directed denominators."""


def test_six_cases_pin_versions_and_isolate_prepared_sessions():
    from scripts.run_application_suite import application_cases
    cases = application_cases("http://localhost:4001/", "http://localhost:4002/", "http://localhost:5231/",
                              {"todomvc": "todo.json", "memos-autonomous": "auto.json", "memos-directed": "directed.json"})
    assert len(cases) == 6
    assert len({case["id"] for case in cases}) == 6
    assert {case["mode"] for case in cases} == {"autonomous", "directed"}
    assert all(case["version"] and case["reset"] and case["max_actions"] == 4 for case in cases)
    assert cases[2]["entry_url"] != cases[3]["entry_url"]
    assert cases[4]["storage_state"] != cases[5]["storage_state"]
    assert not cases[0].get("storage_state")
    assert "storage_state" not in cases[1]
    assert "empty" in cases[1]["reset"].lower()
def test_targeted_case_selection_preserves_separate_action_budgets():
    from scripts.run_application_suite import select_cases
    rows=[{'id':'memos-directed','max_actions':4},{'id':'it-tools-directed','max_actions':4}]
    selected=select_cases(rows,['memos-directed'],['memos-directed=8'])
    assert selected==[{'id':'memos-directed','max_actions':8}]
    assert rows[0]['max_actions']==4
    assert [r['id'] for r in select_cases(rows,['it-tools-directed','memos-directed'])]==['it-tools-directed','memos-directed']
