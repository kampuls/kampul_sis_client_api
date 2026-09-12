import ast
from pathlib import Path
import unittest


_ROOT = Path(__file__).resolve().parents[1]


def _imports_from(source_path: Path) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class LeaveAttendanceParticipationIndependenceTests(unittest.TestCase):
    def test_leave_api_does_not_depend_on_attendance_participation_access(self):
        modules = _imports_from(
            _ROOT / "app" / "api" / "v1" / "leave_management.py"
        )

        self.assertFalse(
            any(
                module.endswith("attendance_processing_access_service")
                for module in modules
            )
        )

    def test_leave_notifications_do_not_filter_by_attendance_participation(self):
        modules = _imports_from(
            _ROOT / "app" / "services" / "leave_notification_service.py"
        )

        self.assertFalse(
            any(
                module.endswith("attendance_processing_access_service")
                for module in modules
            )
        )


if __name__ == "__main__":
    unittest.main()
