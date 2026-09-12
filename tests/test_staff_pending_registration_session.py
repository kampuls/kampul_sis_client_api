from pathlib import Path

from app.schemas import StaffRegisterResponse, UserResponse


ROOT = Path(__file__).resolve().parents[1]


def test_public_staff_registration_forces_pending_teacher_account():
    source = (ROOT / "app/api/v1/auth.py").read_text(encoding="utf-8")
    registration = source.split("async def register(", 1)[1].split(
        '@router.post("/register-parent"',
        1,
    )[0]

    assert 'user.model_copy(update={"role": 2, "status": 2})' in registration
    assert '"role": "teacher"' in registration
    assert '"token_version": getattr(new_user, "token_version", 1) or 1' in registration
    assert "StaffRegisterResponse(" in registration
    assert "pending_approval=True" in registration


def test_staff_registration_response_extends_existing_user_contract():
    assert issubclass(StaffRegisterResponse, UserResponse)
    fields = StaffRegisterResponse.model_fields

    for inherited in ("id", "username", "status", "role", "created_at"):
        assert inherited in fields
    assert fields["access_token"].is_required()
    assert fields["token_type"].default == "bearer"
    assert fields["pending_approval"].default is True
