"""Compliance gate.

Outbound cannot bypass this. Cross-border compliance failure is a legal
kill condition, not a warning.

CASL applies based on where the message is ACCESSED, not where the sender
sits. A US-parented shop with an Ontario branch -> CASL governs the send.
Ambiguous locality -> apply every applicable ruleset simultaneously.

PIPEDA governs the data. CASL governs the send. Both are gates.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import Prospect

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)

# Consent bases we will actually stand on. Express consent is NEVER assumed.
IMPLIED_PUBLISHED = "implied_published_business_contact"
EXPRESS = "express"

# Permitted provenance for contact data. Anything else is refused outright.
PERMITTED_SOURCES = {
    "company_website", "directory_listing", "places_listing",
    "registry_record", "team_page", "trade_press",
}
FORBIDDEN_SOURCES = {
    "purchased_list", "breach_data", "scraped_personal_inbox",
    "tos_circumvention", "private_group", "direct_message",
}


class ComplianceFailure(Exception):
    """Raised when a send is blocked. This halts the cycle and alerts."""


@dataclass
class SenderIdentity:
    """CASL s.6(2): mandatory identification on every commercial message."""
    legal_name: str
    physical_address: str
    phone: str
    email: str

    def block(self) -> str:
        return (f"{self.legal_name}\n{self.physical_address}\n"
                f"{self.phone} | {self.email}")

    def validate(self) -> None:
        for f_ in ("legal_name", "physical_address", "phone", "email"):
            if not getattr(self, f_):
                raise ComplianceFailure(f"SenderIdentity.{f_} is required by CASL.")


@dataclass
class SuppressionList:
    """Unsubscribes, complaints, bounces, do-not-contact. Checked before EVERY send."""
    _hashes: set[str] = field(default_factory=set)
    path: Path | None = None

    @staticmethod
    def _h(email: str) -> str:
        return hashlib.sha256(email.strip().lower().encode()).hexdigest()

    def add(self, email: str) -> None:
        self._hashes.add(self._h(email))
        self._persist()

    def contains(self, email: str) -> bool:
        return self._h(email) in self._hashes

    def load(self) -> None:
        if self.path and self.path.exists():
            self._hashes = set(json.loads(self.path.read_text()))

    def _persist(self) -> None:
        if self.path:
            self.path.write_text(json.dumps(sorted(self._hashes)))


@dataclass
class AuditRecord:
    prospect_id: str
    company: str
    email_hash: str
    jurisdictions: list[str]
    jurisdiction_rule: str
    consent_basis: str
    sender: str
    unsubscribe_url: str
    sent_at: str
    gate_passed: bool
    evidence_count: int


class ComplianceGate:
    """Hard gate. Every check must pass or the send is blocked and logged."""

    def __init__(self, sender: SenderIdentity, suppression: SuppressionList,
                 unsubscribe_base: str, audit_log: Path | None = None):
        sender.validate()
        self.sender = sender
        self.suppression = suppression
        self.unsubscribe_base = unsubscribe_base.rstrip("/")
        self.audit_log = audit_log

    # -- individual checks -------------------------------------------------
    def _check_contact_provenance(self, p: Prospect) -> None:
        src = p.contact.owner_source
        if src in FORBIDDEN_SOURCES:
            raise ComplianceFailure(
                f"Contact provenance '{src}' is forbidden. "
                "No purchased lists, breach data, or ToS circumvention."
            )
        if src not in PERMITTED_SOURCES:
            raise ComplianceFailure(
                f"Contact provenance '{src}' is not on the permitted list."
            )

    def _check_consent(self, p: Prospect) -> None:
        basis = p.contact.consent_basis
        if basis == EXPRESS:
            raise ComplianceFailure(
                "Express consent must be proven, never assumed. "
                "Downgrade to implied or do not send."
            )
        if basis != IMPLIED_PUBLISHED:
            raise ComplianceFailure(f"Unrecognised consent basis: {basis!r}")
        if not p.contact.business_email or not EMAIL_RE.match(p.contact.business_email):
            raise ComplianceFailure("No valid published business email.")

    def _check_suppression(self, p: Prospect) -> None:
        if self.suppression.contains(p.contact.business_email or ""):
            raise ComplianceFailure("Recipient is on the suppression list.")
        p.contact.suppression_checked = True

    def _check_gated(self, p: Prospect, quality_passed: bool) -> None:
        if not quality_passed:
            raise ComplianceFailure(
                "Demo did not pass the quality gate. Nothing broken ships "
                "under the company name."
            )
        if p.decision.value != "BUILD":
            raise ComplianceFailure(f"Prospect decision is {p.decision.value}, not BUILD.")
        if not p.evidence:
            raise ComplianceFailure("No evidence dossier. Uncited prospects never ship.")

    # -- the gate ----------------------------------------------------------
    def authorize(self, p: Prospect, *, quality_passed: bool) -> AuditRecord:
        """Returns an AuditRecord on pass. Raises ComplianceFailure on block."""
        try:
            self._check_gated(p, quality_passed)
            self._check_contact_provenance(p)
            self._check_consent(p)
            self._check_suppression(p)
        except ComplianceFailure:
            self._log(p, passed=False)
            raise

        rec = self._log(p, passed=True)
        return rec

    def unsubscribe_url(self, p: Prospect) -> str:
        token = SuppressionList._h(p.contact.business_email or p.prospect_id)[:32]
        return f"{self.unsubscribe_base}/u/{token}"

    def footer(self, p: Prospect) -> str:
        """Mandatory on every commercial electronic message."""
        return (
            f"{self.sender.block()}\n\n"
            f"Unsubscribe: {self.unsubscribe_url(p)}\n"
            f"You received this because your business contact information is "
            f"published publicly and this message relates to your business role. "
            f"Unsubscribe requests are honoured within 10 days."
        )

    def _log(self, p: Prospect, *, passed: bool) -> AuditRecord:
        rec = AuditRecord(
            prospect_id=p.prospect_id,
            company=p.company,
            email_hash=SuppressionList._h(p.contact.business_email or ""),
            jurisdictions=p.locality.jurisdictions,
            jurisdiction_rule=p.locality.jurisdiction_rule,
            consent_basis=p.contact.consent_basis or "none",
            sender=self.sender.legal_name,
            unsubscribe_url=self.unsubscribe_url(p),
            sent_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            gate_passed=passed,
            evidence_count=len(p.evidence),
        )
        if self.audit_log:
            with self.audit_log.open("a") as fh:
                fh.write(json.dumps(rec.__dict__) + "\n")
        return rec
