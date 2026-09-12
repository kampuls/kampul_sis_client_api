import unittest

from app.api.v1.version_compat import read_ota_updates_enabled


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeDb:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.rolled_back = False

    def execute(self, _statement):
        if self.error is not None:
            raise self.error
        return _ScalarResult(self.value)

    def rollback(self):
        self.rolled_back = True


class OtaUpdateConfigTests(unittest.TestCase):
    def test_ota_is_disabled_by_default(self):
        self.assertFalse(read_ota_updates_enabled(_FakeDb(value=None)))
        self.assertFalse(read_ota_updates_enabled(_FakeDb(value=0)))

    def test_ota_is_enabled_only_for_explicit_database_true(self):
        self.assertTrue(read_ota_updates_enabled(_FakeDb(value=True)))
        self.assertTrue(read_ota_updates_enabled(_FakeDb(value=1)))

    def test_database_or_migration_failure_fails_closed(self):
        db = _FakeDb(error=RuntimeError("missing column"))

        self.assertFalse(read_ota_updates_enabled(db))
        self.assertTrue(db.rolled_back)


if __name__ == "__main__":
    unittest.main()
