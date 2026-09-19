"""Export deterministic JSON Schemas for persisted career workspace records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from career_agent.models.answer import AnswerRecord
from career_agent.models.application import ApplicationManifest
from career_agent.models.operation import OperationRecord
from career_agent.models.opportunity import Opportunity
from career_agent.models.profile import ProfileFact
from career_agent.models.release import DocumentRelease
from career_agent.models.submission import ApprovalRecord, SubmissionAttempt

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "answer-record.schema.json": AnswerRecord,
    "application-manifest.schema.json": ApplicationManifest,
    "approval-record.schema.json": ApprovalRecord,
    "document-release.schema.json": DocumentRelease,
    "operation-record.schema.json": OperationRecord,
    "opportunity.schema.json": Opportunity,
    "profile-fact.schema.json": ProfileFact,
    "submission-attempt.schema.json": SubmissionAttempt,
}


def encoded_schema(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


def export_schemas(output_dir: Path, *, check: bool) -> int:
    expected = {name: encoded_schema(model) for name, model in SCHEMA_MODELS.items()}

    if check:
        drifted: list[str] = []
        for name, content in expected.items():
            path = output_dir / name
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                drifted.append(name)
        if output_dir.is_dir():
            unexpected = {path.name for path in output_dir.glob("*.schema.json")} - set(expected)
            drifted.extend(sorted(unexpected))
        for name in sorted(set(drifted)):
            print(f"schema drift: {name}", file=sys.stderr)
        return 1 if drifted else 0

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        (output_dir / name).write_text(content, encoding="utf-8")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("schemas"))
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return export_schemas(args.output_dir, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
