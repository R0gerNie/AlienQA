"""01b 黑盒装载测试。"""
from alienqa.loader import ProjectLoader


def test_load_browser_returns_minimal_project():
    p = ProjectLoader().load_browser("http://localhost:3001")
    assert p.input_type == "browser"
    assert p.framework == "browser"
    assert p.base_url == "http://localhost:3001"
    assert p.routes == ["/"]
    assert p.entry_points == ["http://localhost:3001"]
    assert p.visible_files == []
    assert p.storage_state == ""


def test_load_browser_with_routes_and_session(tmp_path):
    session = tmp_path / "session.json"
    p = ProjectLoader().load_browser(
        "http://localhost:3001",
        routes=["/", "/login"],
        storage_state=str(session),
    )
    assert p.routes == ["/", "/login"]
    assert p.storage_state == str(session)
