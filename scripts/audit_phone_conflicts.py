#!/usr/bin/env python
"""Report every account that the phone-conflict lock will block.

Run this BEFORE deploying the lock. It is read-only and changes nothing — it
just tells you how many people will be locked out on the next app launch, and
who they are, so the office can fix the numbers first.

    venv/bin/python scripts/audit_phone_conflicts.py
    venv/bin/python scripts/audit_phone_conflicts.py --csv conflicts.csv
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal  # noqa: E402
from app.models import Parent, User  # noqa: E402
from app.services.phone_conflict import list_all_conflicts  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", metavar="PATH", help="also write the rows to a CSV file")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        conflicts = list_all_conflicts(db)

        if not conflicts:
            print("No phone conflicts. Nobody will be locked out.")
            return 0

        rows = []
        for c in conflicts:
            if c.account_type == "parent":
                found = (
                    db.query(
                        Parent.id, Parent.username, Parent.fatherName,
                        Parent.motherName, Parent.myChilds,
                    )
                    .filter(Parent.id.in_(c.account_ids))
                    .all()
                )
                for r in found:
                    rows.append({
                        "type": "parent", "phone": c.phone, "id": r[0],
                        "username": r[1] or "",
                        "name": (r[2] or r[3] or "").strip(),
                        "extra": f"children={r[4] or ''}",
                    })
            else:
                found = (
                    db.query(User.id, User.username, User.eName, User.kName, User.role)
                    .filter(User.id.in_(c.account_ids))
                    .all()
                )
                for r in found:
                    rows.append({
                        "type": "staff", "phone": c.phone, "id": r[0],
                        "username": r[1] or "",
                        "name": (r[2] or r[3] or "").strip(),
                        "extra": f"role={r[4]}",
                    })

        print(f"{len(conflicts)} conflicting phone number(s)")
        print(f"{len(rows)} account(s) will be locked out\n")

        header = f"{'TYPE':<7} {'PHONE':<18} {'ID':<10} {'USERNAME':<20} NAME"
        print(header)
        print("-" * len(header))
        last = None
        for r in sorted(rows, key=lambda x: (x["type"], x["phone"], x["id"])):
            if last is not None and r["phone"] != last:
                print()
            print(
                f"{r['type']:<7} {r['phone']:<18} {r['id']:<10} "
                f"{r['username']:<20} {r['name']}  ({r['extra']})"
            )
            last = r["phone"]

        if args.csv:
            with open(args.csv, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(
                    fh, fieldnames=["type", "phone", "id", "username", "name", "extra"]
                )
                w.writeheader()
                w.writerows(rows)
            print(f"\nWrote {args.csv}")

        print(
            "\nGive each account its own number, then these people can sign in again "
            "(within a minute, or immediately once an admin saves the change)."
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
