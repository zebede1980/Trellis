import argparse
import getpass
import logging
import sys

from trellis import config, db


def _open():
    s = config.load()
    conn = db.connect(s.db_path)
    db.migrate(conn)
    return s, conn


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

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
