import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "app" / "api" / "desktop" / "employee_attendance.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _class_fields(name: str) -> set[str]:
    class_node = next(
        node
        for node in TREE.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )
    return {
        target.id
        for node in class_node.body
        if isinstance(node, ast.AnnAssign)
        and isinstance((target := node.target), ast.Name)
    }


def test_desktop_telegram_settings_contract_never_exposes_bot_token():
    assert "bot_token" not in _class_fields("DesktopTelegramSettingsUpdate")
    assert "bot_token" not in _class_fields("DesktopTelegramSettingsResponse")
    assert "bot_configured" in _class_fields("DesktopTelegramSettingsResponse")


def test_desktop_telegram_settings_replaces_shared_credential_routes():
    assert 'shared_route.path == "/admin/telegram-settings"' in SOURCE
    assert "router.include_router(shared_employee_attendance_router)" not in SOURCE
    assert "update_shared_telegram_settings" in SOURCE
    assert "get_shared_telegram_settings" in SOURCE


def test_desktop_telegram_management_contains_flutter_management_features():
    required_fragments = {
        "tracked-chats",
        "member-verification",
        "moderation",
        "auto-replies",
        "auth-code/generate",
        "auth-code/status",
    }
    for fragment in required_fragments:
        assert fragment in SOURCE


def test_desktop_telegram_management_is_admin_only_and_server_token_filtered():
    assert SOURCE.count("_require_telegram_admin(current_user)") >= 11
    assert "bot_token = get_active_bot_token(db)" in SOURCE
    assert "bot_token=bot_token" in SOURCE
