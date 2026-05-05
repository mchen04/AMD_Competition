from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ConfigError
from .failure_injection import SCENARIOS, inject_failure
from .fake_endpoint import serve_forever
from .operations import check_config, diagnose_config, heal_config, self_heal_config, verify_config
from .providers import ProviderError
from .reporting import generate_report
from .schemas import to_jsonable


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            health, evidence = check_config(args.config)
            _print({"health": health, "evidence": evidence})
            return 0 if health.healthy else 1
        if args.command == "diagnose":
            diagnosis = diagnose_config(args.config, provider_name=args.provider)
            _print(diagnosis)
            return 0 if diagnosis.failure_class != "provider_output_invalid" else 1
        if args.command == "heal":
            repair = heal_config(args.config, provider_name=args.provider)
            _print(repair)
            return 0 if not repair.rejected else 1
        if args.command == "self-heal":
            result = self_heal_config(args.config, provider_name=args.provider)
            _print(result)
            return 0 if result.healthy else 1
        if args.command == "verify":
            verification = verify_config(args.config)
            _print(verification)
            return 0 if verification.healthy else 1
        if args.command == "report":
            report, path = generate_report(args.config)
            _print({"report": report, "path": str(path)})
            return 0
        if args.command == "inject-failure":
            result = inject_failure(args.config, args.scenario)
            _print(result)
            return 0
        if args.command == "fake-endpoint":
            serve_forever(
                host=args.host,
                port=args.port,
                model_id=args.model_id,
                expected_tool_parser=args.expected_tool_parser,
                failure_mode=args.failure_mode,
            )
            return 0
    except (ConfigError, ProviderError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rocm-doctor", description="ROCm Doctor self-healing CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="collect health evidence")
    _add_config(check)

    diagnose = subparsers.add_parser("diagnose", help="classify the current failure")
    _add_config(diagnose)
    diagnose.add_argument("--provider", default="rules", help="diagnosis provider")

    heal = subparsers.add_parser("heal", help="apply a deterministic repair recipe")
    _add_config(heal)
    heal.add_argument("--provider", default="rules", help="diagnosis/planning provider")

    self_heal = subparsers.add_parser("self-heal", help="run check/diagnose/heal/verify until healthy or unrecoverable")
    _add_config(self_heal)
    self_heal.add_argument("--provider", default="rules", help="diagnosis/planning provider")

    verify = subparsers.add_parser("verify", help="rerun health checks after repair")
    _add_config(verify)

    report = subparsers.add_parser("report", help="write an incident report")
    _add_config(report)

    inject = subparsers.add_parser("inject-failure", help="mutate config into a known failure state")
    inject.add_argument("scenario", choices=sorted(SCENARIOS))
    _add_config(inject)

    fake = subparsers.add_parser("fake-endpoint", help="run a deterministic OpenAI-compatible endpoint")
    fake.add_argument("--host", default="127.0.0.1")
    fake.add_argument("--port", type=int, default=8000)
    fake.add_argument("--model-id", default="fake-qwen3")
    fake.add_argument("--expected-tool-parser", default="qwen3")
    fake.add_argument(
        "--failure-mode",
        default="healthy",
        choices=[
            "healthy",
            "models_500",
            "chat_500",
            "chat_invalid_json",
            "empty_response",
            "partial_response",
            "rate_limit",
            "rate_limit_once",
            "slow_response",
            "tool_wrong_name",
            "hallucinated_tool_call",
            "repetitive_output",
            "stream_interrupt",
        ],
    )
    return parser


def _add_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True, type=Path, help="path to ROCm Doctor config")


def _print(value: object) -> None:
    print(json.dumps(to_jsonable(value), indent=2, sort_keys=True))
