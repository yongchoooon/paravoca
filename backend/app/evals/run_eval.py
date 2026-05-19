from __future__ import annotations

import argparse
import json
import logging
import os

from app.evals.runner import run_evaluation

LOG_PREFIX = "[EVAL]"
RESET = "\033[0m"
COLORS = {
    "gray": "\033[90m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "magenta": "\033[35m",
    "red": "\033[31m",
}
TAG_COLORS = {
    "EVAL-RUN": "cyan",
    "EVAL-CASE": "blue",
    "EVAL-STOP": "yellow",
    "LLM-RETRY": "yellow",
    "LLM-JSON": "magenta",
    "LLM-ERROR": "red",
    "HTTP-GEMINI": "yellow",
    "HTTP-KTO": "yellow",
    "HTTP-FAIL": "yellow",
    "GEO-FILTER": "magenta",
    "API-FAIL": "red",
    "RETRIEVAL": "magenta",
    "WORKFLOW-FAIL": "red",
    "CANCEL": "yellow",
    "ERROR": "red",
    "APP-WARN": "yellow",
    "INFO": "gray",
}


class EvaluationHttpNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _is_eval_log_noise(record)


class EvaluationLogFormatter(logging.Formatter):
    def __init__(self, *, use_color: bool | None = None) -> None:
        super().__init__("%(eval_prefix)s%(eval_tag)s %(asctime)s %(levelname)s %(name)s: %(message)s")
        self.use_color = _should_color_logs() if use_color is None else use_color

    def format(self, record: logging.LogRecord) -> str:
        tag = _eval_log_tag(record)
        record.eval_prefix = _colored(LOG_PREFIX, "gray", self.use_color)
        record.eval_tag = _colored(f"[{tag}]", TAG_COLORS.get(tag, "gray"), self.use_color)
        return super().format(record)


def _is_eval_log_noise(record: logging.LogRecord) -> bool:
    if record.name.startswith("sentence_transformers") and record.levelno < logging.WARNING:
        return True
    if record.name == "httpx":
        return _is_http_noise(record)
    return False


def _is_http_noise(record: logging.LogRecord) -> bool:
    message = record.getMessage()
    if "HTTP Request:" not in message:
        return False
    if "https://huggingface.co/" in message:
        return record.levelno < logging.WARNING
    if "https://apis.data.go.kr/" in message or "https://generativelanguage.googleapis.com/" in message:
        return '"HTTP/1.1 200 OK"' in message
    return False


def _eval_log_tag(record: logging.LogRecord) -> str:
    message = record.getMessage()
    lower_message = message.lower()

    if record.name == "eval.runner":
        if "Evaluation case " in message:
            return "EVAL-CASE"
        if "Evaluation stopped" in message:
            return "EVAL-STOP"
        if "Evaluation started" in message or "Evaluation completed" in message:
            return "EVAL-RUN"
        return "INFO"

    if "Dropped " in message and "off-region" in message:
        return "GEO-FILTER"

    if (
        "Gemini retryable response" in message
        or "Gemini retryable transport error" in message
        or "Retrying Gemini call" in message
        or "compact prompt after Gemini timeout" in message
    ):
        return "LLM-RETRY"

    if "Gemini JSON handling failed" in message or "[gemini-json-failed]" in message or "invalid JSON" in message:
        return "LLM-JSON"

    if "Gemini" in message and ("failed" in lower_message or "error" in lower_message or "timed out" in lower_message):
        return "LLM-ERROR"

    if record.name == "httpx" and "HTTP Request:" in message:
        if "generativelanguage.googleapis.com" in message:
            return "HTTP-GEMINI"
        if "apis.data.go.kr" in message:
            return "HTTP-KTO"
        return "HTTP-FAIL"

    if "[workflow-run-failed]" in message or "Workflow execution failed" in message:
        return "WORKFLOW-FAIL"

    if (
        ("TourAPI" in message or "KTO" in message or "enrichment" in lower_message)
        and ("failed" in lower_message or "timeout" in lower_message or "retry" in lower_message)
    ):
        return "API-FAIL"

    if (
        "Chroma" in message
        or "source document" in lower_message
        or "vector search" in lower_message
        or "insufficient_source_data" in message
        or "retrieved documents" in lower_message
    ):
        return "RETRIEVAL"

    if "cancel" in lower_message or "중지" in message or "interrupted" in lower_message:
        return "CANCEL"

    if record.levelno >= logging.ERROR:
        return "ERROR"
    if record.levelno >= logging.WARNING:
        return "APP-WARN"
    return "INFO"


def _should_color_logs() -> bool:
    return os.getenv("NO_COLOR") is None and os.getenv("EVAL_LOG_COLOR", "1").lower() not in {"0", "false", "no"}


def _colored(value: str, color: str, use_color: bool) -> str:
    if not use_color:
        return value
    color_code = COLORS.get(color)
    if not color_code:
        return value
    return f"{color_code}{value}{RESET}"


def _format_eval_console_line(tag: str, message: str) -> str:
    use_color = _should_color_logs()
    return f"{_colored(LOG_PREFIX, 'gray', use_color)}{_colored(f'[{tag}]', TAG_COLORS.get(tag, 'gray'), use_color)} {message}"


def configure_eval_logging() -> None:
    formatter = EvaluationLogFormatter()
    logging.basicConfig(level=logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
        _install_eval_filter(handler)
    uvicorn_logger = logging.getLogger("uvicorn.error")
    uvicorn_logger.setLevel(logging.INFO)
    for handler in uvicorn_logger.handlers:
        handler.setFormatter(formatter)
        _install_eval_filter(handler)


def _install_eval_filter(handler: logging.Handler) -> None:
    if not any(isinstance(log_filter, EvaluationHttpNoiseFilter) for log_filter in handler.filters):
        handler.addFilter(EvaluationHttpNoiseFilter())


def main() -> None:
    configure_eval_logging()
    parser = argparse.ArgumentParser(description="Run PARAVOCA workflow evaluation dataset.")
    parser.add_argument("--dataset", default="smoke", help="Dataset name under app/evals/datasets without .jsonl")
    parser.add_argument("--name", default=None, help="Human-readable evaluation run name shown in the Evaluation UI")
    parser.add_argument("--limit", type=int, default=None, help="Limit cases to the first N selected rows")
    parser.add_argument("--case-id", default=None, help="Run only one case_id")
    parser.add_argument("--no-live-api", action="store_true", help="Skip cases requiring live KTO/TourAPI data")
    parser.add_argument("--reuse-run-id", default=None, help="Evaluate an existing workflow run instead of creating one")
    parser.add_argument("--output-json", action="store_true", help="Print the full evaluation report JSON")
    parser.add_argument("--output-md", action="store_true", help="Write a Markdown report next to the JSON report")
    parser.add_argument(
        "--sleep-between-cases",
        type=float,
        default=2.0,
        help="Seconds to wait between live workflow cases to reduce API/LLM burst load",
    )
    parser.add_argument(
        "--stop-on-first-failure",
        action="store_true",
        help="Stop the eval run after the first failed case",
    )
    parser.add_argument(
        "--enable-llm-judge",
        action="store_true",
        help="Run optional Gemini LLM-as-a-Judge quality metrics after each workflow result",
    )
    args = parser.parse_args()

    report, path = run_evaluation(
        dataset=args.dataset,
        name=args.name,
        limit=args.limit,
        case_id=args.case_id,
        no_live_api=args.no_live_api,
        reuse_run_id=args.reuse_run_id,
        output_md=args.output_md,
        sleep_between_cases=args.sleep_between_cases,
        stop_on_first_failure=args.stop_on_first_failure,
        enable_llm_judge=args.enable_llm_judge,
    )
    if args.output_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = report.get("summary") or {}
        print(
            _format_eval_console_line(
                "EVAL-RUN",
                "Evaluation {eval_id} ({name}) status={status}: passed={passed} failed={failed} skipped={skipped} report={path}".format(
                    eval_id=report.get("eval_id"),
                    name=report.get("name") or report.get("dataset"),
                    status=report.get("status"),
                    passed=summary.get("passed_count"),
                    failed=summary.get("failed_count"),
                    skipped=summary.get("skipped_count"),
                    path=path,
                ),
            )
        )


if __name__ == "__main__":
    main()
