from __future__ import annotations

import json
import sys
from typing import Any

from src.agent.config import (
    CONNECT_TIMEOUT_SECONDS,
    PROBE_TIMEOUT_SECONDS,
    reload_agent_config,
)
from src.agent.llm_client import ApiStyle, build_llm_check_result, LLMClient


def attempt_style(llm: LLMClient, api_style: ApiStyle, message: str) -> dict[str, Any]:
    attempt = {
        "api_style": api_style,
        "sent": True,
        "ok": False,
        "response_text": "",
        "error": "",
    }
    try:
        attempt["response_text"] = llm.run_basic_text_check_with_style(api_style, message)
        attempt["ok"] = bool(attempt["response_text"])
        if not attempt["ok"]:
            attempt["error"] = "Model returned no text."
    except Exception as exc:  # noqa: BLE001
        attempt["error"] = str(exc)
    return attempt


def build_report() -> dict[str, Any]:
    config = reload_agent_config()
    result = build_llm_check_result(config)
    hello_check: dict[str, Any] = {
        "sent": False,
        "ok": False,
        "user_message": "hello",
        "response_text": "",
        "error": "",
        "attempts": [],
    }

    llm = LLMClient(config)
    for api_style in ("chat_completions", "responses"):
        attempt = attempt_style(llm, api_style, "hello")
        hello_check["attempts"].append(attempt)
        if attempt["ok"] and not hello_check["ok"]:
            hello_check["sent"] = True
            hello_check["ok"] = True
            hello_check["response_text"] = attempt["response_text"]
        elif attempt["sent"]:
            hello_check["sent"] = True

    if not hello_check["ok"]:
        failed_attempts = [item for item in hello_check["attempts"] if item.get("error")]
        if failed_attempts:
            hello_check["error"] = "; ".join(
                f"{item['api_style']}={item['error']}" for item in failed_attempts
            )

    return {
        "config": {
            "api_base_url": config.api_base_url,
            "decision_model": config.decision_model,
            "support_model": config.support_model,
            "api_key_present": bool(config.api_key),
            "agent_mode": config.agent_mode,
            "request_timeout_seconds": config.request_timeout_seconds,
            "connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS,
            "probe_timeout_seconds": PROBE_TIMEOUT_SECONDS,
            "proposal_timeout_seconds": config.proposal_timeout_seconds,
            "max_retries": config.max_retries,
        },
        "runtime": result,
        "hello_check": hello_check,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    report = build_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    hello_check = report["hello_check"]
    return 0 if hello_check.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
