from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .builder import build
from .packaging import check_release, package
from .project import release_info
from .validation import validate_repository


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and validate a Codex pet project")
    parser.add_argument(
        "command",
        choices=("build", "validate", "package", "check-release", "release-info"),
    )
    parser.add_argument("--strict", action="store_true", help="Require release QA evidence")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Pet project root")
    parser.add_argument("--output-dir", type=Path, help="Artifact or validation output directory")
    parser.add_argument("--check-tag", action="store_true", help="Require the tag to match project.version")
    parser.add_argument("--tag", help="Git release tag to check with release-info")
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else None
    try:
        if args.command == "build":
            build(root, output_dir)
        elif args.command == "validate":
            validate_repository(root, strict=args.strict, output_dir=output_dir)
        elif args.command == "package":
            package(root, output_dir)
        elif args.command == "check-release":
            check_release(root, output_dir)
        else:
            print(json.dumps(release_info(root, tag=args.tag, check_tag=args.check_tag), ensure_ascii=True, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
