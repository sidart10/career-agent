"""Export deterministic JSON Schemas for persisted career workspace records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from career_agent.documents.pdf_validation import ValidationReport
from career_agent.documents.render import RenderResult
from career_agent.models.answer import AnswerRecord
from career_agent.models.application import ApplicationManifest, RecruitingEvent
from career_agent.models.operation import OperationRecord
from career_agent.models.opportunity import Opportunity
from career_agent.models.profile import ProfileFact
from career_agent.models.release import DocumentRelease, UploadArtifact
from career_agent.models.submission import ApprovalRecord, SubmissionAttempt
from career_agent.services.answers import (
    AnswerResolution,
    AnswerState,
    DeletionPreview,
    DeletionResult,
)
from career_agent.services.applications import ApplicationIndex
from career_agent.services.approvals import ApprovalConsumption
from career_agent.services.evaluation import EvaluationState, FitEvaluation
from career_agent.services.imports import ImportPreview, ImportResult
from career_agent.services.opportunities import MergeRecord, OpportunityState
from career_agent.services.payloads import CanonicalSubmissionPayload
from career_agent.services.postings import PostingChangeSet, PostingSnapshot
from career_agent.services.profile import ProfileState

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "answer-record.schema.json": AnswerRecord,
    "answer-resolution.schema.json": AnswerResolution,
    "answer-state.schema.json": AnswerState,
    "application-manifest.schema.json": ApplicationManifest,
    "application-index.schema.json": ApplicationIndex,
    "approval-consumption.schema.json": ApprovalConsumption,
    "approval-record.schema.json": ApprovalRecord,
    "canonical-submission-payload.schema.json": CanonicalSubmissionPayload,
    "document-release.schema.json": DocumentRelease,
    "deletion-preview.schema.json": DeletionPreview,
    "deletion-result.schema.json": DeletionResult,
    "evaluation-state.schema.json": EvaluationState,
    "fit-evaluation.schema.json": FitEvaluation,
    "import-preview.schema.json": ImportPreview,
    "import-result.schema.json": ImportResult,
    "operation-record.schema.json": OperationRecord,
    "opportunity.schema.json": Opportunity,
    "opportunity-state.schema.json": OpportunityState,
    "merge-record.schema.json": MergeRecord,
    "profile-fact.schema.json": ProfileFact,
    "profile-state.schema.json": ProfileState,
    "posting-change-set.schema.json": PostingChangeSet,
    "posting-snapshot.schema.json": PostingSnapshot,
    "recruiting-event.schema.json": RecruitingEvent,
    "render-result.schema.json": RenderResult,
    "submission-attempt.schema.json": SubmissionAttempt,
    "upload-artifact.schema.json": UploadArtifact,
    "validation-report.schema.json": ValidationReport,
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
