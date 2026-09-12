import importlib.util
from pathlib import Path
import unittest


_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "attendance_gps_compatibility.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "attendance_gps_compatibility",
    _MODULE_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
requires_enhanced_gps_evidence = _MODULE.requires_enhanced_gps_evidence


class AttendanceGpsCompatibilityTests(unittest.TestCase):
    def test_current_store_build_uses_legacy_compatibility(self):
        self.assertFalse(
            requires_enhanced_gps_evidence(
                "1.2.6",
                "PAMA-School-App/1.0.0",
            )
        )

    def test_next_build_requires_enhanced_evidence(self):
        self.assertTrue(
            requires_enhanced_gps_evidence(
                "1.2.7",
                "PAMA-School-App/1.0.0",
            )
        )

    def test_build_metadata_is_supported(self):
        self.assertTrue(
            requires_enhanced_gps_evidence(
                "1.2.7+40",
                "PAMA-School-App/1.0.0",
            )
        )

    def test_old_official_client_without_version_header_is_compatible(self):
        self.assertFalse(
            requires_enhanced_gps_evidence(
                None,
                "PAMA-School-App/1.0.0",
            )
        )

    def test_unknown_client_without_version_fails_closed(self):
        self.assertTrue(requires_enhanced_gps_evidence(None, "curl/8.0"))

    def test_malformed_version_fails_closed(self):
        self.assertTrue(
            requires_enhanced_gps_evidence(
                "latest",
                "PAMA-School-App/1.0.0",
            )
        )


if __name__ == "__main__":
    unittest.main()
