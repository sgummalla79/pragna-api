"""
Migration naming and cross-version contamination checker.

Naming convention (enforced):
  {seq}_v1_{description}.py     — touches v1-only tables
  {seq}_v2_{description}.py     — touches v2-only tables
  {seq}_shared_{description}.py — touches shared tables (no version restriction)

Rules:
  - Every migration file must start with {seq}_v1_, {seq}_v2_, or {seq}_shared_
  - v1_ migrations must not reference v2-only tables
  - v2_ migrations must not reference v1-only tables

Run:
  python scripts/check_migrations.py               # check all migrations
  python scripts/check_migrations.py --new-only    # check only files not in git HEAD~1
"""

import os
import re
import sys
import subprocess
from pathlib import Path

VERSIONS_DIR = Path(__file__).parent.parent / "alembic" / "versions"

V1_ONLY_TABLES: set = set()  # all v1-only tables have been dropped

V2_ONLY_TABLES = {
    "user_skills_v2",
    "user_skill_versions_v2",
    "user_skill_agents_v2",
}

VALID_PREFIX_RE = re.compile(r"^\d{4}_(v1|v2|shared)_")


def get_migration_files(new_only: bool) -> list[Path]:
    files = sorted(VERSIONS_DIR.glob("*.py"))
    if not new_only:
        return files

    # Only files changed/added vs HEAD~1
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD", "--", "alembic/versions/"],
        capture_output=True, text=True,
    )
    changed = {Path(p).name for p in result.stdout.splitlines()}
    return [f for f in files if f.name in changed]


def check_naming(path: Path) -> list[str]:
    if not VALID_PREFIX_RE.match(path.name):
        return [
            f"{path.name}: invalid name — must match {{seq}}_v1_|v2_|shared_{{description}}.py"
        ]
    return []


def check_contamination(path: Path) -> list[str]:
    name  = path.name
    text  = path.read_text()
    errors = []

    if re.match(r"^\d{4}_v2_", name):
        for table in V1_ONLY_TABLES:
            if re.search(rf'\b{re.escape(table)}\b', text):
                errors.append(
                    f"{name}: v2 migration references v1-only table '{table}' — "
                    f"use {name.replace('v2_', 'shared_')} if this is intentional"
                )

    elif re.match(r"^\d{4}_v1_", name):
        for table in V2_ONLY_TABLES:
            if re.search(rf'\b{re.escape(table)}\b', text):
                errors.append(
                    f"{name}: v1 migration references v2-only table '{table}' — "
                    f"use {name.replace('v1_', 'shared_')} if this is intentional"
                )

    return errors


def main() -> int:
    new_only = "--new-only" in sys.argv
    files    = get_migration_files(new_only)

    if not files:
        print("No migration files to check.")
        return 0

    all_errors: list[str] = []
    for f in files:
        all_errors.extend(check_naming(f))
        all_errors.extend(check_contamination(f))

    if all_errors:
        print("Migration check FAILED:\n")
        for err in all_errors:
            print(f"  ✗ {err}")
        print()
        return 1

    print(f"Migration check passed — {len(files)} file(s) OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
