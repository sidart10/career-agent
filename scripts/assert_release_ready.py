"""Fail a CI step unless a JSON doctor envelope reports release readiness."""

from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        envelope = json.load(sys.stdin)
        ready = envelope["data"]["capability_report"]["release_ready"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print("doctor output is not a valid capability envelope", file=sys.stderr)
        return 1
    if ready is not True:
        print("doctor reports the installation is not release ready", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
