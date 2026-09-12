"""
Telegram Notification Service for Attendance Events.
Sends notifications to Telegram when employees check in/out.
"""
import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
CAMBODIA_TZ = timezone(timedelta(hours=7))


def _to_cambodia_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=CAMBODIA_TZ)
    return value.astimezone(CAMBODIA_TZ)


def _now_cambodia() -> datetime:
    return datetime.now(CAMBODIA_TZ)


def _format_cambodia_when(value: Optional[datetime] = None) -> str:
    """Date and 12h time in Cambodia (UTC+7) only."""
    when_kh = _to_cambodia_time(value) if value is not None else _now_cambodia()
    return f"{when_kh.strftime('%d/%m/%Y')} · {_format_time_12h(when_kh)} (KH)"


def _format_time_12h(value: datetime) -> str:
    hour = value.hour % 12
    if hour == 0:
        hour = 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d} {suffix}"


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _format_duration(
    minutes: Optional[int] = None,
    seconds: Optional[int] = None,
) -> Optional[str]:
    if seconds is None:
        if minutes is None:
            return None
        seconds = int(minutes) * 60

    total = max(0, int(seconds))
    if total <= 0:
        return None

    hours = total // 3600
    mins = (total % 3600) // 60
    secs = total % 60

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    if secs:
        parts.append(f"{secs}s")
    return " ".join(parts)


class TelegramNotificationService:
    """Service for sending Telegram notifications."""

    TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    @staticmethod
    async def send_checkin_security_alert(
        bot_token: str,
        chat_id: str,
        *,
        employee_name: str,
        username: str,
        user_id: int,
        event_type: str,
        severity: str,
        message: str,
        client_ip: Optional[str] = None,
    ) -> bool:
        """Send a sanitized attendance security event to administrators."""
        try:
            severity_key = str(severity or "info").lower()
            severity_icon = {
                "critical": "🚨",
                "warning": "⚠️",
                "info": "ℹ️",
            }.get(severity_key, "ℹ️")
            message_text = (
                f"<b>{severity_icon} Check-In Security Alert</b>\n\n"
                f"├ <b>Severity:</b> {_escape_html(severity_key.title())}\n"
                f"├ <b>Event:</b> <code>{_escape_html(event_type)}</code>\n"
                f"├ <b>Employee:</b> {_escape_html(employee_name)}\n"
                f"├ <b>Account:</b> {_escape_html(username)} · #{int(user_id)}"
            )
            if client_ip:
                message_text += (
                    f"\n├ <b>Network:</b> <code>{_escape_html(client_ip)}</code>"
                )
            message_text += (
                f"\n├ <b>Details:</b> {_escape_html(message.strip()[:500])}"
                f"\n└ <b>Detected:</b> {_format_cambodia_when(None)}"
            )

            url = TelegramNotificationService.TELEGRAM_API_URL.format(
                token=bot_token,
            )
            payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "text": message_text,
                "parse_mode": "HTML",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
            if response.status_code == 200:
                return True
            logger.error(
                "Failed to send check-in security alert: %s - %s",
                response.status_code,
                response.text,
            )
            return False
        except Exception as exc:
            logger.error("Error sending check-in security alert: %s", exc)
            return False

    @staticmethod
    async def send_attendance_problem_report(
        bot_token: str,
        chat_id: str,
        *,
        employee_name: str,
        username: str,
        user_id: int,
        issue_label: str,
        issue_code: str,
        surface: str,
        technical_message: Optional[str] = None,
        app_version: Optional[str] = None,
        device_type: Optional[str] = None,
    ) -> bool:
        """Send a user-requested, sanitized attendance diagnostic report."""
        try:
            message = (
                "<b>🛠 Attendance Problem Report</b>\n\n"
                f"├ <b>Employee:</b> {_escape_html(employee_name)}\n"
                f"├ <b>Account:</b> {_escape_html(username)} · #{int(user_id)}\n"
                f"├ <b>Problem:</b> {_escape_html(issue_label)}\n"
                f"├ <b>Code:</b> <code>{_escape_html(issue_code)}</code>\n"
                f"├ <b>Screen:</b> {_escape_html(surface)}"
            )
            if app_version:
                message += f"\n├ <b>App:</b> {_escape_html(app_version)}"
            if device_type:
                message += f"\n├ <b>Device:</b> {_escape_html(device_type)}"
            if technical_message:
                message += (
                    "\n├ <b>Detail:</b> "
                    f"{_escape_html(technical_message.strip()[:500])}"
                )
            message += (
                f"\n└ <b>Sent:</b> {_format_cambodia_when(None)}\n\n"
                "<i>No GPS coordinates or authentication data were included.</i>"
            )

            url = TelegramNotificationService.TELEGRAM_API_URL.format(
                token=bot_token,
            )
            payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
            if response.status_code == 200:
                return True
            logger.error(
                "Failed to send attendance problem report: %s - %s",
                response.status_code,
                response.text,
            )
            return False
        except Exception as exc:
            logger.error("Error sending attendance problem report: %s", exc)
            return False

    @staticmethod
    async def send_attendance_notification(
        bot_token: str,
        chat_id: str,
        employee_name: str,
        action_type: str,  # 'check_in' or 'check_out'
        check_time: datetime,
        location_name: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        notes: Optional[str] = None,
        status: Optional[str] = None,  # 'late', 'early_leave', 'present', etc.
        late_minutes: Optional[int] = None,
        duration_seconds: Optional[int] = None,
    ) -> bool:
        """
        Send attendance notification to Telegram.

        Args:
            bot_token: Telegram bot token
            chat_id: Target chat ID
            employee_name: Name of the employee
            action_type: 'check_in' or 'check_out'
            check_time: Time of check-in/out
            location_name: Optional location/branch name
            latitude: Optional GPS latitude
            longitude: Optional GPS longitude
            notes: Optional notes (late reason, etc.)
            status: Attendance status ('late', 'early_leave', 'present', etc.)
            late_minutes: Number of minutes late (legacy fallback)
            duration_seconds: Exact late/early duration in seconds (if applicable)

        Returns:
            True if notification sent successfully, False otherwise
        """
        try:
            # Build message with clean tree-style formatting
            # Use distinct emojis for header to avoid confusion with status
            header_emoji = "➡️" if action_type == "check_in" else "🏁"
            action_text = "Check-In" if action_type == "check_in" else "Check-Out"

            # Format time in Cambodia timezone using 12-hour display.
            check_time_kh = _to_cambodia_time(check_time)
            time_str = _format_time_12h(check_time_kh)
            date_str = check_time_kh.strftime("%d/%m/%Y")

            # Determine status with emoji based on status parameter and notes
            status_text = action_text
            status_emoji = "✅"

            # Check status parameter first (from backend)
            if status:
                status_lower = status.lower()
                if "late" in status_lower:
                    status_text = f"Late {action_text}"
                    status_emoji = "⚠️"
                elif "early" in status_lower:
                    status_text = f"Early {action_text}"
                    status_emoji = "🏃"
                elif "absent" in status_lower:
                    status_text = f"{action_text} (Absent)"
                    status_emoji = "❌"
            
            # Fallback: check notes if status not provided
            if status_emoji == "✅" and notes:
                notes_lower = notes.lower()
                if "late" in notes_lower:
                    status_text = f"Late {action_text}"
                    status_emoji = "⚠️"
                elif "early" in notes_lower:
                    status_text = f"Early {action_text}"
                    status_emoji = "🏃"

            # Build compact tree-style message
            message = f"""{header_emoji} <b>Attendance notification</b>
<b>👤 Employee</b>
├ Name: {_escape_html(str(employee_name))}
├ Action: {status_emoji} {status_text}"""

            duration_label = _format_duration(
                minutes=late_minutes,
                seconds=duration_seconds,
            )
            if duration_label:
                if "late" in status_text.lower():
                    message += f"\n├ Late: {duration_label}"
                elif "early" in status_text.lower():
                    message += f"\n├ Early: {duration_label}"

            message += f"""
├ Time: {time_str}
├ Date: {date_str}"""

            if location_name:
                message += f"\n├ Location: {_escape_html(str(location_name))}"

            if latitude is not None and longitude is not None:
                map_link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
                message += f"\n├ Map: <a href='{map_link}'>View Location</a>"

            message += f"\n└ {action_text} Successful"

            # Note always at the bottom, after everything
            if notes:
                message += (
                    "\n\n<b>📌 Note</b>\n└ "
                    f"{_escape_html(str(notes).strip()[:800])}"
                )

            message += "\n\n<i>━━━━━━━━━━━━━━━━━━━━</i>"
            message += "\n<i>PAMA Attendance System</i>"

            # Send to Telegram
            url = TelegramNotificationService.TELEGRAM_API_URL.format(token=bot_token)
            payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)

                if response.status_code == 200:
                    logger.info(
                        f"Telegram notification sent for {employee_name} ({action_type})"
                    )
                    return True
                else:
                    logger.error(
                        f"Failed to send Telegram notification: {response.status_code} - {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error sending Telegram notification: {str(e)}")
            return False

    @staticmethod
    async def send_parent_registration_notification(
        bot_token: str,
        chat_id: str,
        *,
        parent_id: int,
        username: str,
        father_name: Optional[str] = None,
        mother_name: Optional[str] = None,
        father_phone: Optional[str] = None,
        mother_phone: Optional[str] = None,
        guardian_name: Optional[str] = None,
        guardian_phone: Optional[str] = None,
    ) -> bool:
        """
        Send a Telegram alert when a parent completes self-registration (pending approval).
        Uses the same bot token and chat id as attendance notifications.
        """
        try:
            # Cambodia (UTC+7) only — use send time, not server/DB local time.
            when_label = _format_cambodia_when(None)

            display_name = (
                (father_name or "").strip()
                or (mother_name or "").strip()
                or (guardian_name or "").strip()
                or (username or "").strip()
                or f"#{parent_id}"
            )
            name = _escape_html(display_name)
            user = _escape_html((username or "—").strip())
            phone = (
                (father_phone or "").strip()
                or (mother_phone or "").strip()
                or (guardian_phone or "").strip()
            )

            message = (
                f"<b>👨‍👩‍👧 Parent Registration</b>\n"
                f"⏳ <i>Pending approval</i>\n\n"
                f"├ <b>{name}</b>\n"
                f"├ {user} · #{parent_id}"
            )

            if phone:
                message += f"\n├ 📞 {_escape_html(phone)}"

            message += (
                f"\n├ 🕐 {when_label}\n"
                f"└ Awaiting admin approval\n\n"
                f"<i>━━━━━━━━━━━━━━━━━━━━</i>\n"
                f"<i>PAMA</i>"
            )

            url = TelegramNotificationService.TELEGRAM_API_URL.format(token=bot_token)
            payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    logger.info(
                        "Telegram parent registration notification sent for parent_id=%s",
                        parent_id,
                    )
                    return True
                logger.error(
                    "Failed to send parent registration Telegram notification: %s - %s",
                    response.status_code,
                    response.text,
                )
                return False
        except Exception as e:
            logger.error(
                "Error sending parent registration Telegram notification: %s", e
            )
            return False

    @staticmethod
    async def validate_bot_token(bot_token: str) -> Dict[str, Any]:
        """
        Validate Telegram bot token by calling getMe API.

        Args:
            bot_token: Telegram bot token to validate

        Returns:
            Dict with 'valid' boolean and optional 'bot_info' dict
        """
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getMe"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        bot_info = data.get("result", {})
                        return {
                            "valid": True,
                            "bot_info": {
                                "id": bot_info.get("id"),
                                "username": bot_info.get("username"),
                                "first_name": bot_info.get("first_name"),
                            },
                        }

                return {"valid": False, "error": "Invalid bot token"}

        except Exception as e:
            logger.error(f"Error validating bot token: {str(e)}")
            return {"valid": False, "error": str(e)}

    @staticmethod
    async def send_test_message(
        bot_token: str,
        chat_id: str,
    ) -> Dict[str, Any]:
        """
        Send a test message to verify Telegram configuration.

        Args:
            bot_token: Telegram bot token
            chat_id: Target chat ID

        Returns:
            Dict with 'success' boolean and optional 'error' message
        """
        try:
            url = TelegramNotificationService.TELEGRAM_API_URL.format(token=bot_token)
            payload = {
                "chat_id": chat_id,
                "text": (
                    "✅ <b>Telegram connection successful</b>\n\n"
                    "🔔 <b>Status:</b> Notifications are ready\n"
                    "🏫 <b>System:</b> PAMA Attendance\n\n"
                    "ℹ️ <i>You can now use this chat for configured PAMA "
                    "notifications.</i>"
                ),
                "parse_mode": "HTML",
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)

                if response.status_code == 200:
                    return {"success": True}
                else:
                    error_data = response.json()
                    error_msg = error_data.get("description", "Unknown error")
                    return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Error sending test message: {str(e)}")
            return {"success": False, "error": str(e)}
