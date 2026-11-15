import argparse
import getpass
import logging
import sqlite3
import sys

from trellis import config, db


def _open():
    s = config.load()
    conn = db.connect(s.db_path)
    db.migrate(conn)
    return s, conn


def _ask_password(prompt: str) -> str:
    pw = getpass.getpass(prompt)
    if pw != getpass.getpass("again: "):
        raise SystemExit("passwords did not match")
    return pw


def cmd_user_add(args):
    from trellis import auth

    _, conn = _open()
    try:
        uid = auth.create_user(conn, args.username, _ask_password(f"password for {args.username}: "),
                               is_admin=args.admin, display_name=args.display_name)
    except (ValueError, sqlite3.IntegrityError) as e:
        raise SystemExit(f"error: {e}")
    print(f"user {args.username} created (id {uid}){' as admin' if args.admin else ''}")


def cmd_user_passwd(args):
    from trellis import auth

    _, conn = _open()
    row = conn.execute("SELECT user_id FROM app_user WHERE username = ?", (auth.norm_username(args.username),)).fetchone()
    if row is None:
        raise SystemExit(f"no user {args.username}")
    try:
        auth.set_password(conn, row[0], _ask_password(f"new password for {args.username}: "))
    except ValueError as e:
        raise SystemExit(f"error: {e}")
    print("password updated")


def cmd_user_list(args):
    _, conn = _open()
    for r in conn.execute("SELECT user_id, username, is_admin, disabled, created_at FROM app_user ORDER BY user_id"):
        print(f"{r['user_id']:>3}  {r['username']:<20} {'admin' if r['is_admin'] else '':<6} "
              f"{'disabled' if r['disabled'] else '':<9} {r['created_at']}")


def cmd_serve(args):
    import uvicorn

    # One worker only: the job thread lives in this process and must not be duplicated.
    uvicorn.run("trellis.api.app:create_app", factory=True, host=args.host, port=args.port, workers=1,
                proxy_headers=True, forwarded_allow_ips="*")


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="trellis")
    sub = p.add_subparsers(required=True)

    sp = sub.add_parser("serve")
    sp.add_argument("--host", default="0.0.0.0")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(fn=cmd_serve)

    up = sub.add_parser("user").add_subparsers(required=True)
    sp = up.add_parser("add", help="create a user (prompts for the password)")
    sp.add_argument("username")
    sp.add_argument("--admin", action="store_true")
    sp.add_argument("--display-name")
    sp.set_defaults(fn=cmd_user_add)
    sp = up.add_parser("passwd", help="reset a user's password (prompts)")
    sp.add_argument("username")
    sp.set_defaults(fn=cmd_user_passwd)
    up.add_parser("list").set_defaults(fn=cmd_user_list)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
