import asyncio
import inspect
from types import SimpleNamespace

from app.api.v1.certificates import get_public_certificates


class _EmptyResult:
    def scalar(self):
        return 0

    def mappings(self):
        return self

    def all(self):
        return []


class _RecordingDb:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        return _EmptyResult()

    @property
    def certificate_call(self):
        return next(call for call in self.calls if "FROM demo_cert dc" in call[0])


def _student_user(student_id):
    return SimpleNamespace(id=student_id, role="student")


def test_parent_certificate_query_defaults_to_all_academic_years():
    db = _RecordingDb()

    result = asyncio.run(
        get_public_certificates(
            student_id=17,
            academic_id=None,
            db=db,
            current_user=_student_user(17),
        )
    )

    sql, params = db.certificate_call
    assert result == []
    assert "AND dc.academic_id = :academic_id" not in sql
    assert params == {"student_id": 17}


def test_parent_certificate_query_can_filter_one_academic_year():
    db = _RecordingDb()

    asyncio.run(
        get_public_certificates(
            student_id=17,
            academic_id=2025,
            db=db,
            current_user=_student_user(17),
        )
    )

    sql, params = db.certificate_call
    assert "AND dc.academic_id = :academic_id" in sql
    assert params == {"student_id": 17, "academic_id": 2025}


def test_parent_certificate_query_reads_student_avatar_url_not_legacy_blob():
    source = inspect.getsource(get_public_certificates)

    assert "FROM users_resource ur" in source
    assert "ur.user_type = 'student'" in source
    assert "s.image," not in source
