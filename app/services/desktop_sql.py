"""Validation and compatibility helpers for the always-online desktop API.

The WinForms application historically executed MySQL and SQLite statements
directly.  During the desktop API migration the UI still owns a large amount
of proven query/report logic, so the desktop-only endpoint accepts that legacy
SQL behind staff authentication.  This module keeps the compatibility surface
small, auditable, and unavailable to mobile/web tokens.
"""

from __future__ import annotations

import base64
import binascii
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Mapping


class DesktopSqlRejected(ValueError):
    """Raised when a desktop statement is outside the compatibility policy."""


_ALLOWED_FIRST_KEYWORDS = {
    "select",
    "with",
    "insert",
    "update",
    "delete",
    "replace",
    "show",
    "set",
}

_FORBIDDEN_PATTERNS = (
    re.compile(r"\b(load\s+data|into\s+outfile|into\s+dumpfile|load_file)\b", re.I),
    re.compile(r"\b(sleep|benchmark)\s*\(", re.I),
    re.compile(r"\b(mysql|performance_schema|information_schema|sys)\s*\.", re.I),
    re.compile(r"\b(grant|revoke|create|alter|drop|truncate|rename|lock|unlock)\b", re.I),
    re.compile(r"\b(prepare|execute|deallocate)\s+[A-Za-z0-9_`]+", re.I),
    re.compile(r"\b(handler\s+[A-Za-z0-9_`]+\s+(open|read|close))\b", re.I),
    re.compile(r"\b(shutdown|kill|flush|reset)\b", re.I),
)

_PARAMETER_RE = re.compile(r"(?<!@)@([A-Za-z_][A-Za-z0-9_]*)")
_LAST_INSERT_ID_SUFFIX_RE = re.compile(
    r";\s*select\s+last_insert_id\s*\(\s*\)\s*;?\s*$",
    re.I,
)
_LEGACY_STUDENT_MUTATION_RE = re.compile(
    r"^\s*(?:insert\s+into|replace\s+into|update)\s+`?students`?\b",
    re.I,
)
_LEGACY_STUDENT_IMAGE_TYPE = "legacy_student_image"
_LEGACY_STUDENT_IMAGE_MAX_BYTES = 20 * 1024 * 1024
_SQL_ALIAS_KEYWORDS = {
    "where", "join", "inner", "left", "right", "full", "cross", "on",
    "order", "group", "having", "limit", "union", "set", "values",
}
_STUDENTS_TABLE_RE = re.compile(
    r"\b(?:from|join)\s+`?students`?"
    r"(?:\s+(?:as\s+)?`?([A-Za-z_][A-Za-z0-9_]*)`?)?",
    re.I,
)


def _mask_quoted_text(sql: str) -> str:
    """Return SQL with quoted/comment contents blanked for policy checks."""

    output: list[str] = []
    i = 0
    quote: str | None = None
    while i < len(sql):
        char = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if quote:
            output.append(" ")
            if char == "\\" and nxt:
                output.append(" ")
                i += 2
                continue
            if char == quote:
                # SQL escapes a quote by doubling it.
                if nxt == quote:
                    output.append(" ")
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        if char in ("'", '"', "`"):
            quote = char
            output.append(" ")
            i += 1
            continue
        if (char == "-" and nxt == "-") or char == "#":
            skip = 2 if char == "-" else 1
            end = sql.find("\n", i + skip)
            if end < 0:
                output.extend(" " * (len(sql) - i))
                break
            output.extend(" " * (end - i))
            i = end
            continue
        if char == "/" and nxt == "*":
            end = sql.find("*/", i + 2)
            if end < 0:
                raise DesktopSqlRejected("Unterminated SQL comment")
            output.extend(" " * (end + 2 - i))
            i = end + 2
            continue

        output.append(char)
        i += 1

    if quote:
        raise DesktopSqlRejected("Unterminated SQL string")
    return "".join(output)


def validate_desktop_sql(sql: str) -> str:
    """Validate and normalize one legacy desktop statement.

    The only accepted multi-statement form is the legacy
    ``INSERT ...; SELECT LAST_INSERT_ID();`` pattern.  The suffix is removed;
    the execution response already returns ``last_insert_id``.
    """

    if not sql or not sql.strip():
        raise DesktopSqlRejected("SQL is required")
    if len(sql) > 250_000:
        raise DesktopSqlRejected("SQL exceeds the desktop API limit")

    normalized = _LAST_INSERT_ID_SUFFIX_RE.sub("", sql.strip())
    masked = _mask_quoted_text(normalized).strip()
    masked_without_trailing_semicolon = masked[:-1] if masked.endswith(";") else masked
    if ";" in masked_without_trailing_semicolon:
        raise DesktopSqlRejected("Only one SQL statement is allowed")

    keyword_match = re.match(r"^\s*([A-Za-z]+)", masked_without_trailing_semicolon)
    keyword = keyword_match.group(1).lower() if keyword_match else ""
    if keyword not in _ALLOWED_FIRST_KEYWORDS:
        raise DesktopSqlRejected(f"Desktop SQL operation '{keyword or 'unknown'}' is not allowed")

    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(masked_without_trailing_semicolon):
            raise DesktopSqlRejected("Desktop SQL contains a forbidden operation")

    if keyword == "set" and not re.fullmatch(
        r"\s*set\s+foreign_key_checks\s*=\s*[01]\s*",
        masked_without_trailing_semicolon,
        re.I,
    ):
        raise DesktopSqlRejected("Only the controlled foreign-key setting is allowed")
    if keyword == "show" and not re.match(
        r"^\s*show\s+(tables|columns|fields)\b",
        masked_without_trailing_semicolon,
        re.I,
    ):
        raise DesktopSqlRejected("Only table and column metadata may be shown")

    return normalized.rstrip().rstrip(";").rstrip()


def translate_sqlite_compatibility(sql: str) -> str:
    """Translate the small SQLite dialect subset used by legacy read paths."""

    translated = sql
    translated = re.sub(r"\bINSERT\s+OR\s+IGNORE\b", "INSERT IGNORE", translated, flags=re.I)
    translated = re.sub(r"\bINSERT\s+OR\s+REPLACE\b", "REPLACE", translated, flags=re.I)
    translated = re.sub(r"\bCOLLATE\s+NOCASE\b", "", translated, flags=re.I)
    translated = re.sub(r"\bAS\s+INTEGER\b", "AS SIGNED", translated, flags=re.I)
    translated = re.sub(r"\bAS\s+REAL\b", "AS DECIMAL(65,10)", translated, flags=re.I)
    translated = re.sub(r"\bdatetime\s*\(\s*'now'\s*\)", "NOW()", translated, flags=re.I)
    translated = re.sub(r"\bdate\s*\(\s*'now'\s*\)", "CURDATE()", translated, flags=re.I)
    translated = re.sub(
        r"\bdatetime\s*\(\s*'now'\s*,\s*'localtime'\s*\)",
        "NOW()",
        translated,
        flags=re.I,
    )
    translated = re.sub(
        r"\bdate\s*\(\s*'now'\s*,\s*'-(\d+)\s+(day|days|month|months|year|years)'\s*\)",
        lambda match: (
            f"DATE_SUB(CURDATE(), INTERVAL {match.group(1)} "
            f"{match.group(2).rstrip('s').upper()})"
        ),
        translated,
        flags=re.I,
    )

    # These are the formats currently used by the dashboard/report queries.
    translated = re.sub(
        r"strftime\s*\(\s*'%Y-%m'\s*,\s*([^\)]+)\)",
        r"DATE_FORMAT(\1, '%Y-%m')",
        translated,
        flags=re.I,
    )
    translated = re.sub(
        r"strftime\s*\(\s*'%Y'\s*,\s*([^\)]+)\)",
        r"DATE_FORMAT(\1, '%Y')",
        translated,
        flags=re.I,
    )
    translated = re.sub(
        r"strftime\s*\(\s*'%m'\s*,\s*([^\)]+)\)",
        r"DATE_FORMAT(\1, '%m')",
        translated,
        flags=re.I,
    )
    return translated


def bind_named_parameters(sql: str, parameters: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Convert ADO.NET ``@name`` parameters to SQLAlchemy ``:name`` binds."""

    # ADO.NET parameter collections are case-insensitive, while SQLAlchemy bind
    # names are case-sensitive. Legacy queries sometimes use @AcademicId and
    # @academicid in the same statement. Resolve every spelling to the casing
    # supplied by the client so one ADO parameter remains one server bind.
    parameter_names: dict[str, str] = {}
    clean_parameters: dict[str, Any] = {}
    for key, value in parameters.items():
        clean_name = str(key).lstrip("@:$?")
        canonical_name = parameter_names.setdefault(clean_name.lower(), clean_name)
        clean_parameters[canonical_name] = value

    def replace_parameter(match: re.Match[str]) -> str:
        source_name = match.group(1)
        bind_name = parameter_names.get(source_name.lower(), source_name)
        return f":{bind_name}"

    translated = _PARAMETER_RE.sub(replace_parameter, sql)
    return translated, clean_parameters


def _student_avatar_expression(outer_reference: str) -> str:
    safe_suffix = re.sub(r"[^A-Za-z0-9_]", "_", outer_reference)
    resource_alias = f"desktop_student_resource_{safe_suffix}"
    return (
        "(SELECT "
        f"{resource_alias}.avatar FROM users_resource {resource_alias} "
        f"WHERE {resource_alias}.user_id = {outer_reference}.id "
        f"AND {resource_alias}.user_type = 'student' LIMIT 1)"
    )


def rewrite_student_image_reads(sql: str) -> str:
    """Route current desktop student-photo reads to the URL-only resource field."""

    if statement_kind(sql) not in {"select", "with"}:
        return sql

    table_matches = list(_STUDENTS_TABLE_RE.finditer(sql))
    if not table_matches:
        return sql

    rewritten = sql
    outer_references: list[str] = []
    for match in table_matches:
        candidate = str(match.group(1) or "").strip("`")
        outer_reference = (
            candidate
            if candidate and candidate.lower() not in _SQL_ALIAS_KEYWORDS
            else "students"
        )
        if outer_reference.lower() not in {value.lower() for value in outer_references}:
            outer_references.append(outer_reference)

    for outer_reference in outer_references:
        expression = _student_avatar_expression(outer_reference)
        reference_pattern = re.compile(
            rf"(?<![A-Za-z0-9_])`?{re.escape(outer_reference)}`?\s*\.\s*`?image`?\b"
            r"(?P<alias>\s+AS\s+`?[A-Za-z_][A-Za-z0-9_]*`?)?",
            re.I,
        )
        rewritten = reference_pattern.sub(
            lambda match: expression + (match.group("alias") or " AS image"),
            rewritten,
        )

    # A few established statements use an unqualified ``image`` column with
    # students as their primary table. Keep their returned column name stable.
    primary_students = re.search(r"\bfrom\s+`?students`?\b", rewritten, re.I)
    if primary_students:
        prefix = rewritten[:primary_students.start()]
        suffix = rewritten[primary_students.start():]
        outer_reference = outer_references[0]
        expression = _student_avatar_expression(outer_reference)
        unqualified_pattern = re.compile(
            r"(?<![A-Za-z0-9_.])(?<!AS )`?image`?\b"
            r"(?P<alias>\s+AS\s+`?[A-Za-z_][A-Za-z0-9_]*`?)?",
            re.I,
        )
        prefix = unqualified_pattern.sub(
            lambda match: expression + (match.group("alias") or " AS image"),
            prefix,
        )
        rewritten = prefix + suffix

    return rewritten


def _is_supported_student_image(content: bytes) -> bool:
    return (
        content.startswith(b"\x89PNG\r\n\x1a\n")
        or content.startswith(b"\xff\xd8\xff")
        or content.startswith((b"GIF87a", b"GIF89a"))
        or (len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP")
        or content.startswith(b"BM")
        or content.startswith((b"II*\x00", b"MM\x00*"))
    )


def decode_desktop_parameters(
    sql: str,
    parameters: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str | None]]:
    """Decode the one temporary binary parameter allowed for old student builds.

    The current desktop uploads the image resource first, then includes the
    original bytes in a tagged value only when mutating ``students.image``.
    Arbitrary structured/binary SQL parameters remain rejected.
    """

    decoded: dict[str, Any] = {}
    student_resources: dict[str, str | None] = {}
    parameter_references = {
        match.group(1).lower() for match in _PARAMETER_RE.finditer(sql)
    }
    is_student_mutation = bool(_LEGACY_STUDENT_MUTATION_RE.search(sql))
    sql_without_parameters = _PARAMETER_RE.sub("", sql)
    mentions_student_image = bool(re.search(r"\bimage\b", sql_without_parameters, re.I))

    for raw_name, value in parameters.items():
        name = str(raw_name).lstrip("@:$?")
        if not isinstance(value, dict):
            if isinstance(value, (bytes, bytearray, memoryview, list)):
                raise DesktopSqlRejected(
                    "Binary and structured SQL parameters are not allowed; upload a resource URL first"
                )
            decoded[raw_name] = value
            continue

        value_type = str(value.get("$type") or "")
        allowed = (
            value_type == _LEGACY_STUDENT_IMAGE_TYPE
            and name.lower() == "image"
            and name.lower() in parameter_references
            and is_student_mutation
            and mentions_student_image
        )
        if not allowed:
            raise DesktopSqlRejected("Structured SQL parameters are not allowed")

        if value.get("remove") is True:
            decoded[raw_name] = None
            student_resources[name.lower()] = None
            continue

        resource_url = str(value.get("resource_url") or "").strip()
        if not resource_url.startswith(("http://", "https://", "/uploads/", "uploads/")):
            raise DesktopSqlRejected("The legacy student image has no managed resource URL")

        encoded = value.get("base64")
        if not isinstance(encoded, str) or not encoded:
            raise DesktopSqlRejected("The legacy student image payload is missing")
        if len(encoded) > ((_LEGACY_STUDENT_IMAGE_MAX_BYTES + 2) // 3) * 4 + 4:
            raise DesktopSqlRejected("The legacy student image exceeds the 20 MB limit")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise DesktopSqlRejected("The legacy student image payload is invalid") from exc
        if not content or len(content) > _LEGACY_STUDENT_IMAGE_MAX_BYTES:
            raise DesktopSqlRejected("The legacy student image exceeds the 20 MB limit")
        if not _is_supported_student_image(content):
            raise DesktopSqlRejected("The legacy student image payload is not a supported image")

        decoded[raw_name] = content
        student_resources[name.lower()] = resource_url

    return decoded, student_resources


def encode_desktop_value(value: Any) -> Any:
    """Encode DBAPI values without ever serializing database BLOB bytes."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return {"$type": "decimal", "value": format(value, "f")}
    if isinstance(value, datetime):
        return {"$type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"$type": "time", "value": value.isoformat()}
    if isinstance(value, timedelta):
        total_microseconds = (
            (value.days * 86_400 + value.seconds) * 1_000_000
            + value.microseconds
        )
        sign = "-" if total_microseconds < 0 else ""
        total_microseconds = abs(total_microseconds)
        day_microseconds = 86_400 * 1_000_000
        hour_microseconds = 3_600 * 1_000_000
        minute_microseconds = 60 * 1_000_000
        days, remainder = divmod(total_microseconds, day_microseconds)
        hours, remainder = divmod(remainder, hour_microseconds)
        minutes, remainder = divmod(remainder, minute_microseconds)
        seconds, microseconds = divmod(remainder, 1_000_000)
        day_prefix = f"{days}." if days else ""
        fraction = f".{microseconds:06d}" if microseconds else ""
        return {
            "$type": "timespan",
            "value": (
                f"{sign}{day_prefix}{hours:02d}:{minutes:02d}:"
                f"{seconds:02d}{fraction}"
            ),
        }
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise DesktopSqlRejected(
            "A legacy database BLOB was read. Run the resource migration before enabling the desktop API."
        )
    return str(value)


def statement_kind(sql: str) -> str:
    masked = _mask_quoted_text(sql).lstrip()
    match = re.match(r"([A-Za-z]+)", masked)
    return match.group(1).lower() if match else ""


def is_mutation(sql: str) -> bool:
    return statement_kind(sql) in {"insert", "update", "delete", "replace", "set"}


_PROTECTED_ADMIN_TABLES = {"users", "roles", "role_permissions", "system_settings", "global_settings"}
_PROTECTED_TABLE_MUTATION_RE = re.compile(
    r"\b(?:insert\s+into|replace\s+into|update|delete\s+from)\s+[`\"]?("
    + "|".join(_PROTECTED_ADMIN_TABLES)
    + r")[`\"]?\b",
    re.I,
)


def requires_admin_privilege(sql: str) -> bool:
    """Return True if the statement mutates security-critical administrative tables."""
    if not is_mutation(sql):
        return False
    return bool(_PROTECTED_TABLE_MUTATION_RE.search(sql))


_SENSITIVE_CREDENTIAL_COLUMNS = {
    "password",
    "password_hash",
    "token_hash",
    "secret_key",
    "remember_token",
}


def is_sensitive_credential_column(column_name: str) -> bool:
    """Return True if the column contains security credentials that must be redacted."""
    return str(column_name).strip().lower() in _SENSITIVE_CREDENTIAL_COLUMNS


_UPDATE_OR_DELETE_RE = re.compile(
    r"\b(?:update\s+`?[A-Za-z0-9_]+`?|delete\s+from\s+`?[A-Za-z0-9_]+`?)\b",
    re.I,
)
_WHERE_CLAUSE_RE = re.compile(r"\bwhere\b", re.I)


def validate_safe_mutation(sql: str) -> None:
    """Ensure UPDATE and DELETE statements specify a WHERE clause to prevent full-table wipes."""
    kind = statement_kind(sql)
    masked = _mask_quoted_text(sql)
    if kind in {"update", "delete"} or _UPDATE_OR_DELETE_RE.search(masked):
        if not _WHERE_CLAUSE_RE.search(masked):
            raise DesktopSqlRejected(
                f"{kind.upper() or 'Mutation'} statements must include a WHERE clause for safety."
            )


_MUTATION_TABLE_RE = re.compile(
    r"\b(?:insert\s+into|replace\s+into|update|delete\s+from)\s+[`\"]?([A-Za-z0-9_]+)[`\"]?\b",
    re.I,
)


def extract_mutation_tables(sql: str) -> list[str]:
    """Extract table names affected by an INSERT, UPDATE, DELETE, or REPLACE statement."""
    return [match.group(1).lower() for match in _MUTATION_TABLE_RE.finditer(sql)]
