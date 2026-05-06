from __future__ import annotations

from typing import Any, Mapping

from ..schemas import DiagnosisResult, EvidenceBundle, RepairPlan
from .rules import RulesProvider


class FakeProvider:
    """Deterministic provider for tests / safety scenarios.

    Composes the rules engine for happy-path output, then layers
    injection modes on top to exercise executor safety gates.
    """

    def __init__(self, name: str, spec: dict[str, Any]) -> None:
        self.name = name
        self.spec = spec
        self._rules = RulesProvider(name)

    def diagnose(self, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult | Mapping[str, Any]:
        if self._mode() == "invalid_schema":
            return {"failure_class": "tool_parser_mismatch"}
        diagnosis = self._rules.diagnose(evidence, config)
        diagnosis.provider = self.name
        return diagnosis

    def plan(
        self, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]
    ) -> RepairPlan | Mapping[str, Any]:
        mode = self._mode()
        plan = self._rules.plan(diagnosis, evidence, config)
        plan.provider = self.name
        if mode == "unknown_recipe":
            plan.recipe_id = "unknown_recipe_id"
            return plan
        if mode == "unsafe_command":
            plan.command_preview = ["rm -rf /tmp/rocm-doctor-demo"]
            return plan
        if mode == "path_traversal":
            plan.config_patch["path"] = "../outside.yaml"
            return plan
        if mode == "credential_modification":
            plan.config_patch["changes"] = {"credentials.openai_api_key": "not-allowed"}
            return plan
        if mode == "malformed_plan":
            return {"recipe_id": "set_tool_parser"}
        return plan

    def _mode(self) -> str:
        return str(self.spec.get("mode", "normal"))
