#!/usr/bin/env python
"""Fail the build if a known security mistake comes back.

Every check here corresponds to a real bug that was in this codebase. Tests
cover the fixed code paths; this covers the *shape* of the mistake, so a new
endpoint written next year cannot quietly reintroduce it.

    venv/bin/python scripts/security_guard.py
"""

import ast
import pathlib
import re
import sys
from typing import List, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = ROOT / "app" / "api"

Finding = Tuple[str, int, str, str]  # file, line, rule, message


def _py_files(base: pathlib.Path):
    for f in sorted(base.rglob("*.py")):
        if "__pycache__" not in str(f):
            yield f


def _rel(f: pathlib.Path) -> str:
    return str(f.relative_to(ROOT))


def check_membership_queries_carry_user_type() -> List[Finding]:
    """`user_id` alone is ambiguous: parents, students and staff share integers.

    Any filter on a table that has a user_type column must constrain both.
    """
    out: List[Finding] = []
    tables = ("MessageGroupMember", "MessageGroupBan", "MessageReaction")
    for f in _py_files(API):
        lines = f.read_text(errors="ignore").splitlines()
        for i, line in enumerate(lines, 1):
            for t in tables:
                if f"{t}.user_id ==" not in line:
                    continue
                # user_type must appear in the same filter(...) call — look at a
                # small window rather than the single line.
                window = "\n".join(lines[max(0, i - 6): i + 6])
                if f"{t}.user_type" not in window:
                    out.append((
                        _rel(f), i, "membership-needs-user-type",
                        f"{t}.user_id filtered without {t}.user_type",
                    ))
    return out


def check_raw_filenames_not_forwarded_to_storage() -> List[Finding]:
    """A client filename reaching os.path.join is an arbitrary file write.

    StorageService.safe_filename() is the sanitiser; callers may still pass a
    raw name only because that function now cleans it. Flag any NEW direct use
    of a raw filename in a path join.
    """
    out: List[Finding] = []
    pattern = re.compile(r"os\.path\.join\([^)]*\.filename")
    for f in _py_files(ROOT / "app"):
        for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
            if pattern.search(line):
                out.append((
                    _rel(f), i, "raw-filename-in-path",
                    "client filename joined into a path without sanitising",
                ))
    return out


def check_upload_endpoints_are_authenticated() -> List[Finding]:
    """An unauthenticated upload writes attacker-controlled bytes to our disk."""
    out: List[Finding] = []
    for f in _py_files(API):
        src = f.read_text(errors="ignore")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            deco = "\n".join(ast.get_source_segment(src, d) or "" for d in n.decorator_list)
            if "@router" not in deco:
                continue
            seg = ast.get_source_segment(src, n) or ""
            sig = seg.split("):")[0]
            if "UploadFile" not in sig:
                continue
            if not re.search(r"Depends\(\s*(get_current|require_admin|require_)", sig):
                out.append((
                    _rel(f), n.lineno, "upload-needs-auth",
                    f"{n.name}() accepts an upload with no authentication dependency",
                ))
    return out


def check_admin_guards_verify_role() -> List[Finding]:
    """Resolving a token's user_id against `users` without checking the role
    claim hands a parent the employee account sharing their ID."""
    out: List[Finding] = []
    for f in _py_files(ROOT / "app"):
        src = f.read_text(errors="ignore")
        if "jwt.decode" not in src:
            continue
        lines = src.splitlines()
        for i, line in enumerate(lines, 1):
            if "jwt.decode" not in line:
                continue
            window = "\n".join(lines[max(0, i - 3): i + 45])
            queries_users = "query(User)" in window
            checks_role = ('payload.get("role")' in window or "get('role')" in window)
            # A scope check is an equally strong guard: only the desktop login
            # mints a desktop-scoped token, and it authenticates against `users`
            # alone, so a parent token can never carry that scope.
            checks_scope = ('payload.get("scope")' in window or "get('scope')" in window)
            if queries_users and not checks_role and not checks_scope:
                out.append((
                    _rel(f), i, "token-needs-role-check",
                    "token resolved against the users table without reading the role claim",
                ))
    return out


CHECKS = (
    ("membership queries carry user_type", check_membership_queries_carry_user_type),
    ("no raw client filename in path joins", check_raw_filenames_not_forwarded_to_storage),
    ("upload endpoints are authenticated", check_upload_endpoints_are_authenticated),
    ("token lookups verify the role claim", check_admin_guards_verify_role),
)


def main() -> int:
    all_findings: List[Finding] = []
    print("Security guard\n" + "=" * 60)
    for label, fn in CHECKS:
        found = fn()
        status = f"FAIL ({len(found)})" if found else "ok"
        print(f"  {status:<10} {label}")
        all_findings.extend(found)

    if not all_findings:
        print("\nAll checks passed.")
        return 0

    print("\n" + "=" * 60)
    for f, line, rule, msg in all_findings:
        print(f"{f}:{line}\n    [{rule}] {msg}")
    print(f"\n{len(all_findings)} problem(s). These are shapes of bugs this "
          "codebase has already had — please do not reintroduce them.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
