from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Any

from ..schemas import EvidenceBundle
from ..templates import TemplateRenderError, render_template
from .base import LLMDiagnosisProvider, OptionalProviderUnavailable, ProviderError


class CodexCliProvider(LLMDiagnosisProvider):
    """Diagnosis brain that shells out to the Codex CLI binary.

    Auth is whatever ``codex login`` already established on this machine —
    a ChatGPT subscription session or an OpenAI API key inside Codex's own
    config — so this provider never reads OPENAI_API_KEY from the env.
    The CLI is run with ``--sandbox read-only --ephemeral --ignore-user-config``
    so the model only produces a JSON answer; it never writes files or runs
    shell commands during diagnosis.
    """

    label = "Codex CLI"

    def __init__(self, name: str, spec: dict[str, Any]) -> None:
        self.name = name
        self.spec = spec
        binary = str(os.environ.get("ROCM_DOCTOR_CODEX_BINARY") or spec.get("binary") or "codex")
        resolved = shutil.which(binary)
        if not resolved:
            raise OptionalProviderUnavailable(f"{binary} binary not found on PATH")
        self.binary = resolved
        model_env = os.environ.get(str(spec.get("model_env", "")))
        self.model = (model_env or str(spec.get("model") or "")).strip()
        self.api_key = None
        self._timeout = float(spec.get("timeout_seconds", 60.0))
        self._sandbox = str(spec.get("sandbox") or "read-only")
        self._extra_config = list(spec.get("extra_config") or [])

    def _api_key_env(self) -> str:
        return ""

    def _require_api_key(self) -> bool:
        return False

    def _endpoint_url(self) -> str:
        return self.binary

    def _build_body(self, instructions, schema_name, schema, data):
        raise NotImplementedError("Codex CLI provider does not build HTTP bodies")

    def _build_headers(self):
        raise NotImplementedError("Codex CLI provider does not build HTTP headers")

    def _extract_text(self, payload, schema_name):
        raise NotImplementedError("Codex CLI provider does not parse HTTP payloads")

    def _invoke(
        self,
        evidence: EvidenceBundle,
        schema_name: str,
        schema: dict[str, Any],
        template_ref: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            instructions = render_template(
                evidence.config_path,
                template_ref,
                {"provider_name": self.name, "schema_name": schema_name, "data": data},
            )
        except TemplateRenderError as exc:
            raise ProviderError(str(exc)) from exc

        prompt = (
            f"{instructions.strip()}\n\n"
            f"## Input ({schema_name})\n\n"
            f"```json\n{json.dumps(data, sort_keys=True, indent=2)}\n```\n\n"
            "Return only JSON conforming to the provided output schema. "
            "Do not run shell commands, do not edit files, do not ask follow-up questions."
        )

        with tempfile.TemporaryDirectory(prefix="rocm-doctor-codex-") as tmp:
            schema_path = os.path.join(tmp, "schema.json")
            output_path = os.path.join(tmp, "last.json")
            with open(schema_path, "w", encoding="utf-8") as fh:
                json.dump(schema, fh)

            cmd = [
                self.binary,
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "--ignore-user-config",
                "--sandbox",
                self._sandbox,
                "--color",
                "never",
                "--output-schema",
                schema_path,
                "--output-last-message",
                output_path,
            ]
            if self.model:
                cmd.extend(["--model", self.model])
            for override in self._extra_config:
                cmd.extend(["-c", str(override)])
            cmd.extend(["-C", tmp])
            cmd.append("-")

            try:
                proc = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ProviderError(f"{self.label} timed out after {self._timeout:.0f}s") from exc
            except FileNotFoundError as exc:
                raise OptionalProviderUnavailable(f"{self.label} binary missing: {exc}") from exc

            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip()
                stdout_tail = (proc.stdout or "").strip()[-400:]
                if "Not logged in" in stderr or "codex login" in stderr or "401" in stderr:
                    raise OptionalProviderUnavailable(f"{self.label} not authenticated: {stderr[:200]}")
                detail = stderr or stdout_tail or f"exit {proc.returncode}"
                raise ProviderError(f"{self.label} exited {proc.returncode}: {detail[:400]}")

            if not os.path.exists(output_path):
                raise ProviderError(f"{self.label} did not produce {schema_name} output")
            with open(output_path, "r", encoding="utf-8") as fh:
                text = fh.read().strip()

        if not text:
            raise ProviderError(f"{self.label} produced empty {schema_name} output")
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.label} returned non-JSON content: {exc}") from exc
        if not isinstance(value, dict):
            raise ProviderError(f"{self.label} returned non-object JSON")
        return value
