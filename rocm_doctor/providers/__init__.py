"""Diagnosis providers — rules engine plus pluggable LLM brains.

Public surface (preserved from the pre-refactor single-file module):

  - Provider protocol
  - ProviderError, OptionalProviderUnavailable
  - RulesProvider, FakeProvider
  - OpenAIResponsesProvider, AnthropicProvider, OpenAICompatibleDiagnosisProvider
  - get_provider, diagnose_with_provider, plan_with_provider
"""

from __future__ import annotations

from .anthropic import AnthropicProvider
from .base import LLMDiagnosisProvider, OptionalProviderUnavailable, Provider, ProviderError
from .fake import FakeProvider
from .openai_compat import OpenAICompatibleDiagnosisProvider
from .openai_responses import OpenAIResponsesProvider
from .registry import (
    classify_intent_with_provider,
    diagnose_with_provider,
    get_provider,
    plan_with_provider,
)
from .rules import RulesProvider

__all__ = [
    "Provider",
    "ProviderError",
    "OptionalProviderUnavailable",
    "LLMDiagnosisProvider",
    "RulesProvider",
    "FakeProvider",
    "OpenAIResponsesProvider",
    "AnthropicProvider",
    "OpenAICompatibleDiagnosisProvider",
    "get_provider",
    "diagnose_with_provider",
    "plan_with_provider",
    "classify_intent_with_provider",
]
