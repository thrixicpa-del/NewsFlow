from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "docs" / "obsidian" / "NewsFlow"
ARCHITECTURE = VAULT / "01 - Architecture"


class EngineeringDocumentationTests(unittest.TestCase):
    def test_engineering_workflow_links_to_each_required_current_policy(self) -> None:
        workflow = ARCHITECTURE / "Engineering Delivery Workflow.md"
        expected = {
            "Engineering Architecture": ARCHITECTURE / "Runtime Topology.md",
            "Git Workflow": ARCHITECTURE / "Git Workflow and Governance.md",
            "Testing Strategy": ARCHITECTURE / "Testing Strategy.md",
            "Environment Isolation": ARCHITECTURE / "Environment Isolation Contract.md",
            "Release Process": ARCHITECTURE / "Release Artifact Policy.md",
            "Release Gate": ARCHITECTURE / "Release Gate.md",
            "Build Manifest": ARCHITECTURE / "Build Manifest and Verification.md",
            "Visual Testing": ARCHITECTURE / "Visual Testing.md",
            "Security": ARCHITECTURE / "Security Gates.md",
            "Observability": ARCHITECTURE / "Observability.md",
            "Backup/Restore": ARCHITECTURE / "Backup and Restore.md",
            "Migration Policy": ARCHITECTURE / "Migration Policy.md",
            "Incident Runbook": ARCHITECTURE / "Incident Runbook.md",
            "Provider Failure Runbook": ARCHITECTURE / "Provider Failure Runbook.md",
        }

        self.assertTrue(workflow.is_file(), workflow)
        text = workflow.read_text(encoding="utf-8")
        for name, document in expected.items():
            self.assertTrue(document.is_file(), document)
            self.assertIn(name, text)

    def test_engineering_decision_records_delivery_authority(self) -> None:
        decision = VAULT / "18 - Decisions" / "ADR-003 Production Engineering Workflow.md"
        self.assertTrue(decision.is_file(), decision)
        text = decision.read_text(encoding="utf-8")
        self.assertIn("current verified runtime", text)
        self.assertIn("release-gate.ps1", text)
        self.assertIn("production", text)
