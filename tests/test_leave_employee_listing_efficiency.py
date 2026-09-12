from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "api"
    / "v1"
    / "leave_management.py"
).read_text(encoding="utf-8")


def _function_source(name: str, next_name: str) -> str:
    start = SOURCE.index(f"async def {name}(")
    end = SOURCE.index(f"async def {next_name}(", start)
    return SOURCE[start:end]


def test_colleague_listing_supports_stable_offset_pagination():
    function = _function_source(
        "list_colleagues",
        "list_manual_leave_employee_filter_options",
    )

    assert "offset: int = Query(0, ge=0)" in function
    assert "User.eName.asc(), User.id.asc()" in function
    assert ".offset(offset).limit(limit)" in function


def test_manual_employee_listing_pages_in_the_database_and_can_skip_avatars():
    function = _function_source(
        "list_manual_leave_employees",
        "list_balance_adjustment_employee_filter_options",
    )

    assert "include_avatar: bool = Query(True)" in function
    assert "total = query.order_by(None).count()" in function
    assert ".offset((page - 1) * limit)" in function
    assert ".limit(limit)" in function
    assert "if include_avatar:" in function
    assert "eligible =" not in function
    assert "_manual_leave_employee_scope_query(db, current_user, approver)" in function


def test_manual_employee_filter_options_use_the_same_authorized_scope():
    function = _function_source(
        "list_manual_leave_employee_filter_options",
        "list_manual_leave_employees",
    )

    assert "_manual_leave_approver(db, current_user)" in function
    assert "_manual_leave_employee_scope_query(db, current_user, approver)" in function
    assert ".with_entities(User.departmentId, User.workplace)" in function
    assert ".distinct()" in function
    assert "_department_name_map(db, department_ids)" in function
    assert "db.query(Branch)" in function
    assert "_current_workplace_id(current_user)" in function
    assert '"current_branch_id": current_branch_id' in function


def test_balance_employee_filter_options_use_the_same_authorized_scope():
    function = _function_source(
        "list_balance_adjustment_employee_filter_options",
        "list_balance_adjustment_employees",
    )

    assert "_balance_adjustment_approver(db, current_user)" in function
    assert "_balance_adjustment_employee_scope_query(db, current_user, approver)" in function
    assert ".with_entities(User.departmentId, User.workplace)" in function
    assert ".distinct()" in function
    assert "_department_name_map(db, department_ids)" in function
    assert "db.query(Branch)" in function
    assert "_current_workplace_id(current_user)" in function
    assert '"current_branch_id": current_branch_id' in function


def test_balance_employee_listing_pages_in_the_database_and_can_skip_avatars():
    function = _function_source(
        "list_balance_adjustment_employees",
        "balance_adjustment_context",
    )

    assert "include_avatar: bool = Query(True)" in function
    assert "total = query.order_by(None).count()" in function
    assert ".offset((page - 1) * limit)" in function
    assert ".limit(limit)" in function
    assert "if include_avatar:" in function
    assert "eligible =" not in function
    assert "_balance_adjustment_employee_scope_query(db, current_user, approver)" in function
