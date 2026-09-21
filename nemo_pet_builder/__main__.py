from __future__ import annotations

import argparse
from pathlib import Path

from .builder import build
from .packaging import check_release, package
from .validation import validate_repository


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and validate the Nemo Dango Codex pet")
    parser.add_argument("command", choices=("build", "validate", "package", "check-release"))
    parser.add_argument("--strict", action="store_true", help="Require release QA evidence")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    args = parser.parse_args()

    root = args.root.resolve()
    if args.command == "build":
        build(root)
    elif args.command == "validate":
        validate_repository(root, strict=args.strict)
    elif args.command == "package":
        package(root)
    else:
        check_release(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
