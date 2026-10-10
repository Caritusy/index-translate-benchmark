#!/usr/bin/env python3
"""Reproduce the Index-Translate comparison with Python 3.10+ and no dependencies.

Prompts are read verbatim from data/cases.json. Requests are sequential, with
rotating model order. Timings are observed by the client and include transport,
queueing and generation. Existing request records are skipped on resumption,
including failed records; use a fresh output directory for a new trial.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_MODELS = ["index-mt-2b", "index-mt-9b", "index-mt-35b"]
DEFAULT_API_BASE = "https://index-translate.bilibili.com/v1"
SPEED_CASES = [
    ("short", "everyday_en_zh"),
    ("medium", "technical"),
    ("long", "long_en_zh"),
]


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def positive_float(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def endpoint_from_base(base):
    parts = urllib.parse.urlsplit(base)
    if (parts.scheme not in ("http", "https") or not parts.netloc
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment):
        raise ValueError("api-base must be an HTTP(S) URL without credentials, query or fragment")
    return base.rstrip("/") + "/chat/completions"


def load_cases():
    cases = json.loads((ROOT / "data" / "cases.json").read_text(encoding="utf-8-sig"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases.json must contain a nonempty list")
    ids = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each case must be an object")
        for name in ("id", "source", "target", "text", "prompt"):
            if not isinstance(case.get(name), str) or not case[name]:
                raise ValueError("each case needs nonempty id, source, target, text and prompt strings")
        if case["id"] in ids:
            raise ValueError("case IDs must be unique")
        ids.add(case["id"])
    return cases


def make_payload(model, case, max_tokens):
    return {
        "model": model,
        "messages": [{"role": "user", "content": case["prompt"]}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }


def config_hash(endpoint, payload):
    encoded = json.dumps({"endpoint": endpoint, "payload": payload},
                         ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def request_key(row):
    return row.get("phase"), row.get("repeat"), row.get("case_id"), row.get("model")


def read_rows(path):
    """Keep valid records even if an interrupted append left a malformed line."""
    rows, issues = [], []
    if not path.exists():
        return rows, issues
    with path.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if (not isinstance(row, dict)
                        or row.get("phase") not in ("quality", "speed")
                        or not isinstance(row.get("repeat"), int)
                        or not isinstance(row.get("case_id"), str)
                        or not isinstance(row.get("model"), str)):
                    raise ValueError("invalid record")
                rows.append(row)
            except (ValueError, TypeError):
                issues.append({"line": number, "error": "invalid_jsonl_record"})
    return rows, issues


def make_plan(cases, models, repeats, quality=True, speed=True):
    if quality:
        for index, case in enumerate(cases):
            shift = index % len(models)
            for model in models[shift:] + models[:shift]:
                yield "quality", 0, case, model, None
    if speed:
        by_id = {case["id"]: case for case in cases}
        if any(case_id not in by_id for _, case_id in SPEED_CASES):
            raise ValueError("cases.json lacks a required speed case")
        for repeat in range(repeats):
            for index, (group, case_id) in enumerate(SPEED_CASES):
                shift = (repeat + index) % len(models)
                for model in models[shift:] + models[:shift]:
                    yield "speed", repeat, by_id[case_id], model, group


def iter_sse_data(response):
    """Parse SSE data fields, including multiline events and a final EOF event."""
    lines = []
    for raw in response:
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if lines:
                yield "\n".join(lines)
                lines = []
        elif line.startswith("data:"):
            value = line[5:]
            lines.append(value[1:] if value.startswith(" ") else value)
    if lines:
        yield "\n".join(lines)


def request(endpoint, model, case, phase, repeat, group, max_tokens, timeout):
    payload = make_payload(model, case, max_tokens)
    row = {
        "phase": phase,
        "repeat": repeat,
        "case_id": case["id"],
        "model": model,
        "timestamp": utc_timestamp(),
        "input_chars": len(case["text"]),
        "prompt_sha256": hashlib.sha256(case["prompt"].encode("utf-8")).hexdigest(),
        "request_config_sha256": config_hash(endpoint, payload),
        "request_parameters": {
            "temperature": 0.0, "max_tokens": max_tokens, "stream": True,
            "enable_thinking": False, "include_usage": True,
        },
        "http_status": None,
        "ttft_seconds": None,
        "done_seconds": None,
        "stream_done": False,
        "finish_reason": None,
        "usage": None,
        "error": None,
    }
    if group is not None:
        row["length_group"] = group
    contents, returned_models = [], set()
    started = time.perf_counter()
    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "User-Agent": "Index-Translate-Client/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            row["http_status"] = response.status
            for body in iter_sse_data(response):
                if body.strip() == "[DONE]":
                    row["stream_done"] = True
                    row["done_seconds"] = time.perf_counter() - started
                    break
                chunk = json.loads(body)
                if not isinstance(chunk, dict):
                    raise ValueError("invalid SSE chunk")
                if chunk.get("error"):
                    row["error"] = "api_stream_error"
                if isinstance(chunk.get("model"), str):
                    returned_models.add(chunk["model"])
                if isinstance(chunk.get("usage"), dict):
                    row["usage"] = chunk["usage"]
                choices = chunk.get("choices") or []
                if choices:
                    choice = choices[0]
                    content = (choice.get("delta") or {}).get("content")
                    if isinstance(content, str) and content:
                        if row["ttft_seconds"] is None:
                            row["ttft_seconds"] = time.perf_counter() - started
                        contents.append(content)
                    if choice.get("finish_reason") is not None:
                        row["finish_reason"] = choice["finish_reason"]
    except urllib.error.HTTPError as error:
        row["http_status"] = error.code
        row["error"] = "http_error"
        error.close()
    except TimeoutError:
        row["error"] = "timeout"
    except urllib.error.URLError as error:
        row["error"] = "timeout" if isinstance(error.reason, TimeoutError) else "connection_error"
    except (ValueError, TypeError, AttributeError, UnicodeError):
        row["error"] = "invalid_stream"
    except Exception as error:
        # Do not publish exception messages: they can contain local paths or hosts.
        row["error"] = "request_failed"
        row["error_type"] = type(error).__name__
    row["total_seconds"] = (row["done_seconds"] if row["done_seconds"] is not None
                            else time.perf_counter() - started)
    row["output"] = "".join(contents)
    row["output_chars"] = len(row["output"])
    row["returned_models"] = sorted(returned_models)
    if row["error"] is None:
        if not row["stream_done"]:
            row["error"] = "missing_done"
        elif not row["output"]:
            row["error"] = "empty_output"
        elif row["finish_reason"] != "stop":
            row["error"] = "non_stop_finish"
    tokens = (row["usage"] or {}).get("completion_tokens")
    row["completion_tokens_per_e2e_second"] = (
        tokens / row["total_seconds"]
        if isinstance(tokens, (int, float)) and not isinstance(tokens, bool)
        and math.isfinite(tokens) and tokens >= 0 and row["total_seconds"] > 0 else None
    )
    return row


def successful(row):
    return (not row.get("error") and row.get("stream_done") is True
            and row.get("finish_reason") == "stop"
            and isinstance(row.get("output"), str) and bool(row["output"]))


def numbers(rows, field):
    return [value for row in rows if isinstance(value := row.get(field), (int, float))
            and not isinstance(value, bool) and math.isfinite(value) and value >= 0]


def median_or_none(values):
    return statistics.median(values) if values else None


def build_summary(rows, models, issues=None, expected_requests=None):
    """Pure aggregation: empty or failed groups get null timing statistics."""
    issues = issues or []
    latest = {request_key(row): row for row in rows}
    unique = list(latest.values())
    observed_models = list(dict.fromkeys(models + [row["model"] for row in rows]))
    good = [row for row in unique if successful(row)]
    report = {
        "generated_at": utc_timestamp(),
        "request_count": len(rows),
        "unique_request_count": len(unique),
        "duplicate_request_records": len(rows) - len(unique),
        "expected_request_count": expected_requests,
        "successes": len(good),
        "failures": len(unique) - len(good),
        "input_issues": issues,
        "models": observed_models,
        "quality_case_count": len({r["case_id"] for r in unique if r["phase"] == "quality"}),
        "speed_repetitions_observed": len({r["repeat"] for r in unique if r["phase"] == "speed"}),
        "method": (
            "Sequential requests, rotating model order. Client timing includes HTTP/TLS, "
            "network, queueing and generation. TTFT is the first nonempty content delta; "
            "total_seconds is receipt of [DONE] on completed streams, or elapsed time on "
            "failure. Successful requests only contribute to timing statistics. "
            "No automatic retries. No network requests during summarization."
        ),
        "models_stats": {},
    }
    for model in observed_models:
        own = [row for row in unique if row["model"] == model]
        good_own = [row for row in own if successful(row)]
        quality = [row for row in good_own if row["phase"] == "quality"]
        stat = {
            "requests": len(own),
            "successes": len(good_own),
            "errors": [{"phase": row["phase"], "repeat": row["repeat"],
                        "case_id": row["case_id"], "error": row.get("error") or "incomplete_record"}
                       for row in own if not successful(row)],
            "returned_models": sorted({name for row in good_own
                                       for name in row.get("returned_models", [])
                                       if isinstance(name, str)}),
            "quality_median_total_seconds": median_or_none(numbers(quality, "total_seconds")),
            "quality_median_ttft_seconds": median_or_none(numbers(quality, "ttft_seconds")),
            "speed": {},
        }
        for group, case_id in SPEED_CASES:
            selected = [row for row in good_own if row["phase"] == "speed"
                        and row["case_id"] == case_id]
            all_selected = [row for row in own if row["phase"] == "speed"
                            and row["case_id"] == case_id]
            totals = numbers(selected, "total_seconds")
            char_rates = [row["output_chars"] / row["total_seconds"]
                          for row in selected
                          if numbers([row], "output_chars")
                          and numbers([row], "total_seconds") and row["total_seconds"] > 0]
            stat["speed"][group] = {
                "n": len(selected), "failed_n": len(all_selected) - len(selected),
                "median_total_seconds": median_or_none(totals),
                "median_ttft_seconds": median_or_none(numbers(selected, "ttft_seconds")),
                "min_total_seconds": min(totals) if totals else None,
                "max_total_seconds": max(totals) if totals else None,
                "median_output_chars": median_or_none(numbers(selected, "output_chars")),
                "median_chars_per_e2e_second": median_or_none(char_rates),
                "median_completion_tokens_per_e2e_second": median_or_none(
                    numbers(selected, "completion_tokens_per_e2e_second")),
            }
        for case_id in ("long_en_zh", "long_zh_en"):
            selected = [row for row in quality if row["case_id"] == case_id]
            stat[case_id] = ({name: selected[-1].get(name)
                             for name in ("total_seconds", "ttft_seconds", "output_chars", "usage")}
                            if selected else None)
        report["models_stats"][model] = stat
    return report


def write_summary(output_dir, rows, models, issues, expected_requests=None):
    report = build_summary(rows, models, issues, expected_requests)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"requests": report["unique_request_count"],
                      "successes": report["successes"], "failures": report["failures"],
                      "invalid_lines": len(issues)}, ensure_ascii=False), flush=True)
    return report


def append_row(path, row):
    # Separate an incomplete final line from the next complete record on resume.
    needs_newline = False
    if path.exists() and path.stat().st_size:
        with path.open("rb") as stream:
            stream.seek(-1, 2)
            needs_newline = stream.read(1) != b"\n"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        if needs_newline:
            stream.write("\n")
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
    print(json.dumps({name: row.get(name) for name in (
        "phase", "repeat", "case_id", "model", "ttft_seconds", "total_seconds", "error")},
        ensure_ascii=False), flush=True)


def run(args, output_dir):
    cases = load_cases()
    if args.cases:
        if args.speed_only:
            raise ValueError("--case selects quality cases and cannot be combined with --speed-only")
        available = {case["id"] for case in cases}
        if any(case_id not in available for case_id in args.cases):
            raise ValueError("unknown --case ID; see data/cases.json for available IDs")
        selected = set(args.cases)
        cases = [case for case in cases if case["id"] in selected]
    endpoint = endpoint_from_base(args.api_base)
    plan = list(make_plan(cases, args.models, args.repeats,
                          quality=not args.speed_only,
                          speed=not args.quality_only and not args.cases))
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "results.jsonl"
    rows, issues = read_rows(results_path)
    completed = {request_key(row): row for row in rows}
    for phase, repeat, case, model, _ in plan:
        old = completed.get((phase, repeat, case["id"], model))
        if old and old.get("request_config_sha256") is not None:
            new_hash = config_hash(endpoint, make_payload(model, case, args.max_tokens))
            if old["request_config_sha256"] != new_hash:
                raise ValueError("existing requests use different settings; choose a new output directory")
    interrupted = False
    try:
        for phase, repeat, case, model, group in plan:
            key = (phase, repeat, case["id"], model)
            if key in completed:
                continue
            row = request(endpoint, model, case, phase, repeat, group, args.max_tokens, args.timeout)
            append_row(results_path, row)
            rows.append(row)
            completed[key] = row
    except KeyboardInterrupt:
        interrupted = True
        print("Interrupted; recorded requests will be skipped on the next run.", file=sys.stderr)
    report = write_summary(output_dir, rows, args.models, issues, len(plan))
    if interrupted:
        return 130
    return 1 if report["failures"] or issues else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    phase = parser.add_mutually_exclusive_group()
    phase.add_argument("--quality-only", action="store_true", help="one request per case and model")
    phase.add_argument("--speed-only", action="store_true", help="repeat the three speed cases only")
    parser.add_argument("--repeats", type=positive_int, default=5, help="speed repetitions (default: 5)")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS, help="model IDs in initial order")
    parser.add_argument("--case", dest="cases", action="append", metavar="CASE_ID",
                        help="quality case ID; repeat this option to select several cases")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="API base URL ending in /v1")
    parser.add_argument("--timeout", type=positive_float, default=45.0,
                        help="HTTP socket timeout in seconds (default: 45)")
    parser.add_argument("--max-tokens", type=positive_int, default=2048,
                        help="maximum output tokens per request (default: 2048)")
    parser.add_argument("--output-dir", default="output",
                        help="result directory; relative paths resolve from the repository root")
    parser.add_argument("--summarize", action="store_true",
                        help="read results.jsonl and write summary.json only; makes no requests")
    args = parser.parse_args(argv)
    if len(set(args.models)) != len(args.models) or any(not model.strip() for model in args.models):
        parser.error("model IDs must be nonempty and unique")
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    try:
        if args.summarize:
            rows, issues = read_rows(output_dir / "results.jsonl")
            report = write_summary(output_dir, rows, args.models, issues)
            return 1 if not rows or report["failures"] or issues else 0
        return run(args, output_dir)
    except ValueError as error:
        # All messages raised here are fixed validation messages, never paths.
        print("Validation error: " + str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted; previously recorded requests are preserved.", file=sys.stderr)
        return 130
    except Exception as error:
        print("Benchmark failed (" + type(error).__name__ + ").", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
