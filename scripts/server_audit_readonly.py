#!/usr/bin/env python
"""Read-only production audit that needs nothing new deployed.

The proper scripts (audit_phone_conflicts.py, audit_legacy_credentials.py) live
on the security branch and only reach the server once it is merged. This one is
deliberately self-contained — it imports only `app.core.database`, which is
already in the running image — so the numbers can be checked BEFORE deciding
whether it is safe to merge.

It writes nothing. Run it inside the api container:

    docker compose --env-file .env.lightnode exec -T api python - < server_audit_readonly.py
"""

import sys

try:
    import bcrypt
    from sqlalchemy import text
    from app.core.database import SessionLocal
except Exception as exc:  # pragma: no cover - diagnostic path
    print(f"Could not load the application: {exc}")
    sys.exit(1)


def canonical(phone):
    """096555444 / 96555444 / +855 96 555 444 all collapse to 96555444."""
    if not phone:
        return None
    digits = "".join(c for c in str(phone) if c.isdigit())
    if not digits:
        return None
    if digits.startswith("855"):
        digits = digits[3:]
    digits = digits.lstrip("0")
    return digits or None


def phone_conflicts(db):
    """Same number on two or more accounts OF THE SAME KIND.

    Staff+parent is not a conflict — that is a teacher whose own child attends
    the school, and the role button resolves it.
    """
    staff = {}
    for uid, phone in db.execute(text("SELECT id, phone FROM users")).fetchall():
        key = canonical(phone)
        if key:
            staff.setdefault(key, []).append(uid)

    parents = {}
    rows = db.execute(text(
        "SELECT id, fatherPhone, motherPhone, gPhone FROM parents"
    )).fetchall()
    for pid, father, mother, guardian in rows:
        # One row holding the same number twice is not a conflict.
        for key in {k for k in (canonical(father), canonical(mother), canonical(guardian)) if k}:
            parents.setdefault(key, []).append(pid)

    staff_bad = {k: v for k, v in staff.items() if len(v) > 1}
    parent_bad = {k: v for k, v in parents.items() if len(v) > 1}
    return staff_bad, parent_bad


def default_password_students(db):
    """Students whose hash still verifies against the shared '123456'.

    bcrypt is salted, so this cannot be a SQL comparison.
    """
    rows = db.execute(text(
        "SELECT id, username FROM students "
        "WHERE password IS NOT NULL AND password <> ''"
    )).fetchall()
    ids = [r[0] for r in rows]
    if not ids:
        return [], []

    hits, broken = [], []
    for sid, username in rows:
        pw = db.execute(
            text("SELECT password FROM students WHERE id = :i"), {"i": sid}
        ).scalar()
        try:
            if bcrypt.checkpw(b"123456", pw.encode("utf-8")):
                hits.append((sid, username))
        except ValueError:
            broken.append((sid, username))
    return hits, broken


def username_collisions(db):
    return db.execute(text(
        "SELECT u.username, u.id, p.id FROM users u "
        "JOIN parents p ON p.username = u.username "
        "WHERE u.username IS NOT NULL AND u.username <> ''"
    )).fetchall()


def main():
    db = SessionLocal()
    try:
        total_staff = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
        total_parents = db.execute(text("SELECT COUNT(*) FROM parents")).scalar()
        total_students = db.execute(text("SELECT COUNT(*) FROM students")).scalar()

        print("=" * 60)
        print("PAMA read-only security audit (nothing is written)")
        print("=" * 60)
        print(f"staff={total_staff}  parents={total_parents}  students={total_students}")
        print()

        staff_bad, parent_bad = phone_conflicts(db)
        locked = sum(len(v) for v in staff_bad.values()) + sum(len(v) for v in parent_bad.values())
        print("1. PHONE CONFLICTS  (these accounts get locked by the new build)")
        print(f"   duplicate numbers : {len(staff_bad)} staff, {len(parent_bad)} parent")
        print(f"   ACCOUNTS LOCKED   : {locked}")
        if locked:
            print("   sample:")
            for k, v in list(parent_bad.items())[:5]:
                print(f"     parent ids {v} share a number")
            for k, v in list(staff_bad.items())[:5]:
                print(f"     staff  ids {v} share a number")
        print()

        hits, broken = default_password_students(db)
        pct = (100.0 * len(hits) / total_students) if total_students else 0
        print("2. STUDENTS STILL ON THE SHARED PASSWORD '123456'")
        print(f"   affected          : {len(hits)} of {total_students}  ({pct:.0f}%)")
        if broken:
            print(f"   unreadable hashes : {len(broken)} (need a look by hand)")
        print()

        collisions = username_collisions(db)
        print("3. USERNAMES HELD BY BOTH AN EMPLOYEE AND A PARENT")
        print(f"   collisions        : {len(collisions)}")
        for username, uid, pid in collisions[:10]:
            print(f"     {username}  users.id={uid}  parents.id={pid}")
        print()

        print("=" * 60)
        if locked == 0:
            print("Phone lock: SAFE TO MERGE — nobody is locked out.")
        else:
            print(f"Phone lock: {locked} account(s) will be blocked on next app")
            print("launch. Fix those numbers first, or expect support calls.")
        print("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    main()
