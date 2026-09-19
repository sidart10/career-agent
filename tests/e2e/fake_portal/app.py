from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from .scenarios import FakePortalReceipt, PortalScenario, PortalSubmission

SUBMITTED_AT = datetime(2026, 9, 18, 21, 0, tzinfo=UTC)


class FakeEmployerPortal:
    """In-memory employer boundary used only by the local release gate."""

    def __init__(self, scenario: PortalScenario) -> None:
        self.scenario = scenario
        self.app = FastAPI(title="Local Fake Employer Portal")
        self._receipts: dict[str, FakePortalReceipt] = {}
        self._accepted_without_confirmation: set[str] = set()
        self._submission_count = 0
        self._register_routes()

    @property
    def submission_count(self) -> int:
        return self._submission_count

    def receipt(self, token: str) -> FakePortalReceipt:
        return self._receipts[token]

    @staticmethod
    def _authorize(account: str | None, attestation: str | None) -> None:
        if account != "synthetic-candidate":
            raise HTTPException(status_code=401, detail="synthetic account required")
        if attestation != "local-release-gate":
            raise HTTPException(status_code=403, detail="test attestation required")

    @staticmethod
    def _digests(uploads: dict[str, str]) -> dict[str, str]:
        return {
            name: hashlib.sha256(contents.encode()).hexdigest()
            for name, contents in sorted(uploads.items())
        }

    def _make_receipt(self, submission: PortalSubmission) -> FakePortalReceipt:
        echoed = dict(submission.fields)
        anomalies: tuple[str, ...] = ()
        limitations: tuple[str, ...] = ()
        if self.scenario is PortalScenario.NORMALIZE_VALUE:
            echoed["contact.phone"] = re.sub(r"[^+\d]", "", echoed["contact.phone"])
            anomalies = ("contact.phone normalized",)
        if self.scenario is PortalScenario.PARTIAL_SUCCESS:
            echoed = {"contact.email": echoed["contact.email"]}
            limitations = ("phone and upload were not echoed",)
        return FakePortalReceipt.at(
            receipt_id=f"RCP-{submission.idempotency_token}",
            echoed_fields=echoed,
            received_file_digests=self._digests(submission.uploads),
            submitted_at=SUBMITTED_AT,
            anomalies=anomalies,
            evidence_limitations=limitations,
        )

    def _register_routes(self) -> None:
        @self.app.get("/", response_class=HTMLResponse)
        def application_page() -> str:
            template = Path(__file__).parent / "templates" / "application.html"
            return template.read_text(encoding="utf-8")

        @self.app.get("/receipts/{token}")
        def get_receipt(token: str) -> FakePortalReceipt:
            if token not in self._receipts:
                raise HTTPException(status_code=404, detail="receipt unavailable")
            return self._receipts[token]

        @self.app.post("/apply", response_model=None)
        def submit(
            submission: PortalSubmission,
            x_test_account: str | None = Header(default=None),
            x_test_attestation: str | None = Header(default=None),
        ) -> FakePortalReceipt | JSONResponse:
            self._authorize(x_test_account, x_test_attestation)
            token = submission.idempotency_token
            if token in self._receipts:
                return JSONResponse(
                    status_code=201,
                    content=self._receipts[token].model_dump(mode="json"),
                )
            if token in self._accepted_without_confirmation:
                return JSONResponse(
                    status_code=202,
                    content={"status": "accepted_without_confirmation"},
                )
            if self.scenario is PortalScenario.SESSION_EXPIRES:
                raise HTTPException(status_code=401, detail="session expired")
            if (
                self.scenario is PortalScenario.CONDITIONAL_AFTER_APPROVAL
                and not submission.fields.get("portfolio.url")
            ):
                raise HTTPException(
                    status_code=409,
                    detail={"required_fields": ["portfolio.url"]},
                )
            if self.scenario is PortalScenario.REJECT_UPLOAD:
                raise HTTPException(status_code=422, detail="resume.pdf rejected")

            self._submission_count += 1
            if self.scenario is PortalScenario.NO_CONFIRMATION:
                self._accepted_without_confirmation.add(token)
                return JSONResponse(
                    status_code=202,
                    content={"status": "accepted_without_confirmation"},
                )

            receipt = self._make_receipt(submission)
            self._receipts[token] = receipt
            if self.scenario is PortalScenario.NETWORK_FAIL_AFTER_SUBMIT:
                raise RuntimeError("connection lost after acceptance")
            if self.scenario is PortalScenario.DELAYED_SUBMIT:
                return JSONResponse(
                    status_code=202,
                    content={"status": "processing", "token": token},
                )
            return JSONResponse(status_code=201, content=receipt.model_dump(mode="json"))


def serve(
    scenario: PortalScenario = PortalScenario.HAPPY_PATH,
    *,
    port: int = 8765,
) -> None:
    """Run the fake portal on loopback only for a manual local release-gate session."""

    uvicorn.run(FakeEmployerPortal(scenario).app, host="127.0.0.1", port=port)
