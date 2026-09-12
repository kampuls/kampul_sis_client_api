from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "api"
    / "desktop"
    / "leave.py"
).read_text(encoding="utf-8")


def _function_source(name: str, next_name: str) -> str:
    start = SOURCE.index(f"def {name}(")
    end = SOURCE.index(f"def {next_name}(", start)
    return SOURCE[start:end]


def test_desktop_employee_options_filter_by_search_and_branch():
    function = _function_source(
        "desktop_leave_employee_options",
        "desktop_leave_scope_options",
    )

    assert "branch_id: Optional[int] = Query(None)" in function
    assert "User.workplace == branch_id" in function
    assert "User.eName.like(term)" in function
    assert "User.kName.like(term)" in function
    assert "User.id == int(value)" in function
    assert "offset: int = Query(0, ge=0)" in function
    assert ".offset(offset)" in function
    assert ".limit(limit)" in function


def test_desktop_scope_options_include_current_workplace():
    start = SOURCE.index("def desktop_leave_scope_options(")
    function = SOURCE[start:]
    assert "_current_workplace_id(current_user)" in function
    assert '"current_branch_id": _current_workplace_id(current_user)' in function
