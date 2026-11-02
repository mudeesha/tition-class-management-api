"""Setup commands.

uv run python -m app.cli setup                  # permissions + default plans
uv run python -m app.cli sync-permissions
uv run python -m app.cli seed-plans
uv run python -m app.cli create-admin --name "..." --email you@example.com
"""

import argparse
import getpass
import sys

import app.models  # noqa: F401
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.platform.service import seed_default_plans
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.service import sync_permissions


def cmd_sync_permissions(_: argparse.Namespace) -> None:
    with SessionLocal() as db:
        print(f"Permissions synced ({sync_permissions(db)} new).")


def cmd_seed_plans(_: argparse.Namespace) -> None:
    with SessionLocal() as db:
        print(f"Default plans added: {seed_default_plans(db)}.")


def cmd_setup(args: argparse.Namespace) -> None:
    cmd_sync_permissions(args)
    cmd_seed_plans(args)


def cmd_create_admin(args: argparse.Namespace) -> None:
    password = args.password or getpass.getpass("Password (min 8 characters): ")
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters.")
    with SessionLocal() as db:
        users = UserRepository(db)
        user = users.get_by_email(args.email)
        if user is None:
            user = users.add(
                User(
                    name=args.name, email=args.email.lower(), password_hash=hash_password(password)
                )
            )
        user.is_platform_admin = True
        db.commit()
        print(f"Platform admin ready: {user.email}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(required=True)

    sub.add_parser("setup", help="Sync permissions and add default plans").set_defaults(
        func=cmd_setup
    )
    sub.add_parser("sync-permissions").set_defaults(func=cmd_sync_permissions)
    sub.add_parser("seed-plans").set_defaults(func=cmd_seed_plans)
    admin = sub.add_parser("create-admin", help="Create (or promote) a platform admin")
    admin.add_argument("--name", required=True)
    admin.add_argument("--email", required=True)
    admin.add_argument("--password", help="Prompted for when left out")
    admin.set_defaults(func=cmd_create_admin)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
