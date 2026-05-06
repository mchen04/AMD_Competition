from __future__ import annotations

from typing import Any, Callable

from ..config import ConfigError, get_diagnosis_provider_config
from ..schemas import (
    DiagnosisResult,
    EvidenceBundle,
    IntentClassification,
    RepairPlan,
    SchemaError,
    provider_output_invalid,
    provider_skipped,
)
from .anthropic import AnthropicProvider
from .base import OptionalProviderUnavailable, Provider, ProviderError
from .codex_cli import CodexCliProvider
from .fake import FakeProvider
from .openai_compat import OpenAICompatibleDiagnosisProvider
from .openai_responses import OpenAIResponsesProvider
from .rules import RulesProvider


_FACTORIES: dict[str, Callable[[str, dict[str, Any]], Provider]] = {
    "rules": lambda name, spec: RulesProvider(name),
    "fake": lambda name, spec: FakeProvider(name, spec),
    "openai-responses": lambda name, spec: OpenAIResponsesProvider(name, spec),
    "anthropic-messages": lambda name, spec: AnthropicProvider(name, spec),
    "openai-chat-completions": lambda name, spec: OpenAICompatibleDiagnosisProvider(name, spec),
    "codex-cli": lambda name, spec: CodexCliProvider(name, spec),
}


def get_provider(name: str, config: dict[str, Any]) -> Provider:
    try:
        spec = get_diagnosis_provider_config(config, name)
    except ConfigError as exc:
        raise ProviderError(str(exc)) from exc
    provider_type = str(spec.get("type", name))
    factory = _FACTORIES.get(provider_type)
    if factory is None:
        raise ProviderError(f"unknown diagnosis provider type: {provider_type}")
    return factory(name, spec)


def diagnose_with_provider(name: str, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult:
    try:
        provider = get_provider(name, config)
        raw = provider.diagnose(evidence, config)
        if isinstance(raw, DiagnosisResult):
            return raw
        return DiagnosisResult.from_mapping(raw, provider=name)
    except OptionalProviderUnavailable as exc:
        return provider_skipped(str(exc), name)
    except (ProviderError, SchemaError, TypeError, ValueError) as exc:
        return provider_output_invalid(str(exc), name)


def classify_intent_with_provider(
    name: str,
    diagnosis: DiagnosisResult,
    evidence: EvidenceBundle,
    config: dict[str, Any],
    baseline_diff: dict[str, Any],
    activity_log: list[dict[str, Any]],
    baseline_kind: str,
) -> IntentClassification:
    """Run the intent classifier; on any provider error fall back to the rules engine.

    Intent is advisory, not load-bearing for safety — never let an LLM hiccup
    block a heal. If the configured brain fails, the deterministic rules
    engine produces a defensible classification from the diff alone.
    """
    try:
        provider = get_provider(name, config)
        classifier = getattr(provider, "classify_intent", None)
        if classifier is None:
            raise ProviderError(f"provider {name} does not implement classify_intent")
        raw = classifier(diagnosis, evidence, config, baseline_diff, activity_log, baseline_kind)
    except (OptionalProviderUnavailable, ProviderError, SchemaError, TypeError, ValueError):
        provider = RulesProvider(name)
        raw = provider.classify_intent(
            diagnosis, evidence, config, baseline_diff, activity_log, baseline_kind
        )
    if isinstance(raw, IntentClassification):
        return raw
    return IntentClassification.from_mapping(raw, provider=name)


def plan_with_provider(
    name: str, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]
) -> RepairPlan:
    try:
        provider = get_provider(name, config)
        raw = provider.plan(diagnosis, evidence, config)
    except OptionalProviderUnavailable as exc:
        raise ProviderError(str(exc)) from exc
    if isinstance(raw, RepairPlan):
        return raw
    try:
        return RepairPlan.from_mapping(raw, provider=name)
    except (SchemaError, TypeError, ValueError) as exc:
        raise ProviderError(f"provider repair plan invalid: {exc}") from exc
