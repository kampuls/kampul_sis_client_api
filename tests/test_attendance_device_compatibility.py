import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "attendance_device_compatibility.py"
)
SPEC = importlib.util.spec_from_file_location(
    "attendance_device_compatibility",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AttendanceDeviceCompatibilityTests(unittest.TestCase):
    def test_official_legacy_version_remains_compatible(self):
        self.assertFalse(
            MODULE.requires_attendance_device_identity(
                "1.2.7",
                "PAMA-School-App/1.0.0",
            )
        )

    def test_new_version_requires_device_identity(self):
        self.assertTrue(
            MODULE.requires_attendance_device_identity(
                "1.2.8",
                "PAMA-School-App/1.0.0",
            )
        )

    def test_official_build_without_version_header_remains_compatible(self):
        self.assertFalse(
            MODULE.requires_attendance_device_identity(
                None,
                "PAMA-School-App/1.0.0",
            )
        )

    def test_unknown_or_malformed_clients_fail_closed(self):
        self.assertTrue(
            MODULE.requires_attendance_device_identity(None, "curl/8.0")
        )
        self.assertTrue(
            MODULE.requires_attendance_device_identity(
                "not-a-version",
                "PAMA-School-App/1.0.0",
            )
        )

    def test_server_switch_can_end_legacy_compatibility(self):
        self.assertTrue(
            MODULE.requires_attendance_device_identity(
                "1.2.7",
                "PAMA-School-App/1.0.0",
                allow_legacy_compatibility=False,
            )
        )


if __name__ == "__main__":
    unittest.main()
