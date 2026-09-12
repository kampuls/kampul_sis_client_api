import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.v1 import employee_attendance
from app.models.telegram_attendance_settings import TelegramAttendanceSettings
from app.schemas.employee_attendance import AttendanceProblemReportRequest


class _Query:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value


class _Db:
    def __init__(self, telegram_settings):
        self.telegram_settings = telegram_settings
        self.queried_models = []

    def query(self, model):
        self.queried_models.append(model)
        if model is TelegramAttendanceSettings:
            return _Query(self.telegram_settings)
        raise AssertionError(f"Unexpected settings query: {model}")


class AttendanceProblemReportRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_report_is_sent_only_to_attendance_group(self):
        settings = SimpleNamespace(
            id=1,
            bot_token="token",
            chat_id="-100-attendance",
            leave_chat_id="-100-leave",
            leave_routing_mode="separate",
            branch_routing_mode="all",
        )
        db = _Db(settings)
        current_user = SimpleNamespace(
            id=7,
            eName="Employee",
            kName="",
            username="employee",
            workplace=3,
        )
        request = SimpleNamespace(headers={})
        report = AttendanceProblemReportRequest(
            issue_code="outside_workplace",
            surface="quick_attendance",
            technical_message="Outside allowed radius",
        )

        with (
            patch.object(
                employee_attendance,
                "enforce_attendance_support_report_rate_limit",
                AsyncMock(return_value="127.0.0.1"),
            ),
            patch.object(
                employee_attendance,
                "record_checkin_security_event",
            ),
            patch.object(
                employee_attendance.TelegramNotificationService,
                "send_attendance_problem_report",
                AsyncMock(return_value=True),
            ) as send_report,
        ):
            result = await employee_attendance.report_attendance_problem(
                report=report,
                http_request=request,
                db=db,
                current_user=current_user,
            )

        self.assertEqual(result, {"success": True})
        self.assertEqual(db.queried_models, [TelegramAttendanceSettings])
        send_report.assert_awaited_once()
        self.assertEqual(
            send_report.await_args.kwargs["chat_id"],
            "-100-attendance",
        )
        self.assertNotEqual(
            send_report.await_args.kwargs["chat_id"],
            settings.leave_chat_id,
        )


if __name__ == "__main__":
    unittest.main()
