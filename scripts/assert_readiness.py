"""Assert one readiness layer from a Career Agent Doctor JSON envelope."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Literal

Layer = Literal["core", "document", "submission"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", choices=("core", "document", "submission"), required=True)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        ready = payload["data"]["capability_report"][f"{args.layer}_ready"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"invalid doctor report: {error}", file=sys.stderr)
        return 2
    if ready is not True:
        print(f"{args.layer} readiness failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
