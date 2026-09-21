"""Attached-terminal fallback for provenance-preserving human approval."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from typing import TextIO

from career_agent.approval.authority import ApprovalAttestation, ApprovalSummary
from career_agent.errors import CareerError, ErrorCode


class InteractiveApprovalAuthority:
    def __init__(
        self,
        *,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
    ) -> None:
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout

    def _terminal_session(self) -> str:
        try:
            terminal = os.ttyname(self.input.fileno())
        except (AttributeError, OSError):
            terminal = "attached-terminal"
        return terminal

    def request(
        self,
        summary: ApprovalSummary,
        payload_digest: str,
        nonce: str,
    ) -> ApprovalAttestation:
        if not self.input.isatty() or not self.output.isatty():
            raise CareerError(
                ErrorCode.NOT_READY,
                "Trusted approval requires an attached interactive terminal",
            )
        display = {
            "summary": summary.model_dump(mode="json"),
            "digest": f"sha256-v1:{payload_digest}",
            "nonce": nonce,
        }
        self.output.write(json.dumps(display, indent=2, sort_keys=True))
        self.output.write("\nApproving actor: ")
        self.output.flush()
        actor = self.input.readline().strip()
        if not actor:
            raise CareerError(ErrorCode.INVALID_INPUT, "Approving actor is required")
        challenge = f"APPROVE {nonce}"
        self.output.write(f"Type exactly '{challenge}' to approve: ")
        self.output.flush()
        response = self.input.readline().strip()
        if response != challenge:
            raise CareerError(ErrorCode.INVALID_INPUT, "Approval challenge did not match")
        session = self._terminal_session()
        provenance = hashlib.sha256(
            f"{session}\0{actor}\0{nonce}\0{payload_digest}".encode()
        ).hexdigest()
        return ApprovalAttestation(
            payload_digest=payload_digest,
            nonce=nonce,
            approving_actor=actor,
            runtime_session=session,
            authority="interactive-terminal-v1",
            approved_at=datetime.now(UTC),
            provenance_reference=f"terminal-attestation:{provenance}",
        )
