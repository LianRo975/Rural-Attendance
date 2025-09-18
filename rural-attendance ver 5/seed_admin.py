# seed_admin.py
import argparse
import sys
from pathlib import Path
from werkzeug.security import generate_password_hash
from db import bootstrap, insert_user, get_user_by_login, DB_PATH

def main():
    p = argparse.ArgumentParser(
        description="Create a user in the SQLite DB",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--login", required=True, help="Login ID (e.g., admin@school.in)")
    p.add_argument("--password", required=True, help="Plain password (will be hashed)")
    p.add_argument("--role", default="Admin", choices=["Admin","Teacher","Student"])
    args = p.parse_args()

    print(f"→ Using database: {Path(DB_PATH).resolve()}")
    print("→ Bootstrapping schema (if needed)…")
    bootstrap()

    existing = get_user_by_login(args.login.strip())
    if existing:
        print(f"⚠ User already exists: {existing['login_id']} (role={existing['role']})")
        sys.exit(0)

    pwd_hash = generate_password_hash(args.password)
    ok = insert_user(args.login.strip(), pwd_hash, args.role)
    if not ok:
        print("⚠ Could not insert user (maybe duplicate).")
        sys.exit(1)

    created = get_user_by_login(args.login.strip())
    if created:
        print(f"✔ Created user: {created['login_id']} (role={created['role']})")
        print("   You can now log in at /login")
        sys.exit(0)
    else:
        print("✖ Unexpected: user not found after insert.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        # argparse uses SystemExit for usage errors; let it pass
        raise
    except Exception as e:
        print(f"✖ Error: {e.__class__.__name__}: {e}")
        sys.exit(1)
