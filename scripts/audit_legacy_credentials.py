#!/usr/bin/env python
"""Find accounts left insecure by bugs that are now fixed.

Fixing the code does not fix data the bugs already wrote. Two things to look for:

1. Students whose password is still the shared default "123456". Every profile
   save used to reset it, so this may be most of the school. Anyone who guesses
   a classmate's name-derived username can sign in as them.
2. Usernames that exist in BOTH the employees and parents tables. Parent
   registration used to check uniqueness only within parents, so a parent could
   register an existing teacher's username.

Read-only by default. Pass --fix-student-passwords to replace the shared default
with a per-student random password, which is printed once so the office can hand
them out. Nothing else is ever written.

    venv/bin/python scripts/audit_legacy_credentials.py
    venv/bin/python scripts/audit_legacy_credentials.py --csv legacy.csv
    venv/bin/python scripts/audit_legacy_credentials.py --fix-student-passwords
"""

import argparse
import csv
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402

SHARED_DEFAULT = b"123456"


def find_default_password_students(db):
    """Students whose stored hash still verifies against '123456'.

    bcrypt hashes are salted, so this cannot be a SQL comparison — every row has
    to be checked individually.
    """
    rows = db.execute(text(
        "SELECT id, username, kName, eName, password FROM students "
        "WHERE password IS NOT NULL AND password <> ''"
    )).fetchall()

    hits = []
    for sid, username, kname, ename, hashed in rows:
        try:
            if bcrypt.checkpw(SHARED_DEFAULT, hashed.encode("utf-8")):
                hits.append({
                    "id": sid,
                    "username": username or "",
                    "name": (ename or kname or "").strip(),
                })
        except ValueError:
            # Not a bcrypt hash at all — also worth reporting.
            hits.append({
                "id": sid,
                "username": username or "",
                "name": (ename or kname or "").strip() + "  [INVALID HASH]",
            })
    return hits


def find_username_collisions(db):
    """Usernames held by an employee and a parent at the same time."""
    return db.execute(text("""
        SELECT u.username, u.id AS user_id, p.id AS parent_id
        FROM users u
        JOIN parents p ON p.username = u.username
        WHERE u.username IS NOT NULL AND u.username <> ''
        ORDER BY u.username
    """)).fetchall()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", metavar="PATH", help="write the student list to CSV")
    ap.add_argument(
        "--fix-student-passwords",
        action="store_true",
        help="replace the shared default with a random per-student password",
    )
    args = ap.parse_args()

    db = SessionLocal()
    try:
        print("=" * 68)
        print("1. Students still using the shared default password")
        print("=" * 68)
        students = find_default_password_students(db)
        if not students:
            print("None. ✓")
        else:
            print(f"{len(students)} student(s) can be signed into by anyone who "
                  "guesses the username:\n")
            for s in students[:40]:
                print(f"  id={s['id']:<8} {s['username']:<24} {s['name']}")
            if len(students) > 40:
                print(f"  ... and {len(students) - 40} more")

            if args.csv:
                with open(args.csv, "w", newline="", encoding="utf-8") as fh:
                    w = csv.DictWriter(fh, fieldnames=["id", "username", "name", "new_password"])
                    w.writeheader()
                    for s in students:
                        w.writerow({**s, "new_password": ""})
                print(f"\nWrote {args.csv}")

        print()
        print("=" * 68)
        print("2. Usernames held by both an employee and a parent")
        print("=" * 68)
        collisions = find_username_collisions(db)
        if not collisions:
            print("None. ✓")
        else:
            print(f"{len(collisions)} collision(s) — rename the PARENT account:\n")
            for username, user_id, parent_id in collisions:
                print(f"  {username:<24} users.id={user_id}  parents.id={parent_id}")

        if args.fix_student_passwords and students:
            print()
            print("=" * 68)
            print("Assigning new random passwords")
            print("=" * 68)
            issued = []
            for s in students:
                if "[INVALID HASH]" in s["name"]:
                    continue  # leave broken rows for a human to look at
                new_password = secrets.token_urlsafe(9)
                hashed = bcrypt.hashpw(
                    new_password.encode("utf-8"), bcrypt.gensalt()
                ).decode("utf-8")
                db.execute(
                    text("UPDATE students SET password = :p WHERE id = :sid"),
                    {"p": hashed, "sid": s["id"]},
                )
                issued.append({**s, "new_password": new_password})
            db.commit()

            for s in issued:
                print(f"  id={s['id']:<8} {s['username']:<24} {s['new_password']}")
            print(f"\n{len(issued)} password(s) changed. These are shown ONCE — "
                  "save this output now.")

            if args.csv:
                with open(args.csv, "w", newline="", encoding="utf-8") as fh:
                    w = csv.DictWriter(fh, fieldnames=["id", "username", "name", "new_password"])
                    w.writeheader()
                    w.writerows(issued)
                print(f"Wrote {args.csv}")
        elif students:
            print("\nRe-run with --fix-student-passwords to replace them with "
                  "random ones (printed once).")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
