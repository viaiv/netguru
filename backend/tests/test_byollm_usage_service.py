"""
Unit tests for BYO-LLM usage aggregation service.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from app.services.byollm_usage_service import ByoLlmUsageService


def _build_sample_records() -> list[dict]:
    now = datetime.utcnow()
    return [
        {
            "message_id": uuid4(),
            "conversation_id": uuid4(),
            "user_id": uuid4(),
            "created_at": now - timedelta(minutes=3),
            "tokens_used": None,
            "content": "diagnostico detalhado do uplink com validacao de ospf e bgp",
            "message_metadata": {
                "llm_execution": {
                    "selected_provider": "openai",
                    "selected_model": "gpt-4o",
                    "fallback_triggered": True,
                    "attempts": [
                        {"status": "failed_stream", "duration_ms": 120},
                        {"status": "success", "duration_ms": 350},
                    ],
                },
                "tool_calls": [
                    {"tool": "search_rag_global", "status": "completed", "duration_ms": 120},
                    {"tool": "parse_config", "status": "failed", "duration_ms": 200},
                ],
            },
        },
        {
            "message_id": uuid4(),
            "conversation_id": uuid4(),
            "user_id": uuid4(),
            "created_at": now - timedelta(minutes=2),
            "tokens_used": 80,
            "content": "ok",
            "message_metadata": {
                "llm_execution": {
                    "selected_provider": "openai",
                    "selected_model": "gpt-4o",
                    "fallback_triggered": False,
                    "attempts": [
                        {"status": "success", "duration_ms": 180},
                    ],
                },
                "tool_calls": [
                    {"tool": "search_rag_global", "status": "completed", "duration_ms": 100},
                ],
            },
        },
        {
            "message_id": uuid4(),
            "conversation_id": uuid4(),
            "user_id": uuid4(),
            "created_at": now - timedelta(minutes=1),
            "tokens_used": 40,
            "content": "resposta curta",
            "message_metadata": {
                "llm_execution": {
                    "selected_provider": "google",
                    "selected_model": "gemini-2.0-flash",
                    "fallback_triggered": False,
                    "attempts": [
                        {"status": "success", "duration_ms": 90},
                    ],
                },
                "tool_calls": [],
            },
        },
    ]


def test_aggregate_records_computes_totals_and_breakdowns() -> None:
    records = _build_sample_records()

    report = ByoLlmUsageService.aggregate_records(records)

    assert report["totals"]["messages"] == 3
    assert report["totals"]["tokens"] >= 120
    assert report["totals"]["attempts_total"] == 4
    assert report["totals"]["attempts_failed"] == 1
    assert report["totals"]["error_rate_pct"] == 25.0
    assert report["totals"]["tool_calls_total"] == 3
    assert report["totals"]["tool_calls_failed"] == 1
    assert report["totals"]["latency_p95_ms"] >= report["totals"]["latency_p50_ms"]

    by_provider = report["by_provider_model"]
    assert by_provider[0]["provider"] == "openai"
    assert by_provider[0]["messages"] == 2
    assert by_provider[1]["provider"] == "google"

    by_tool = {row["tool"]: row for row in report["by_tool"]}
    assert by_tool["search_rag_global"]["calls"] == 2
    assert by_tool["search_rag_global"]["failed_calls"] == 0
    assert by_tool["parse_config"]["calls"] == 1
    assert by_tool["parse_config"]["failed_calls"] == 1


def test_aggregate_records_applies_provider_filter() -> None:
    records = _build_sample_records()

    report = ByoLlmUsageService.aggregate_records(records, provider_filter="google")

    assert report["totals"]["messages"] == 1
    assert len(report["by_provider_model"]) == 1
    assert report["by_provider_model"][0]["provider"] == "google"


def test_build_alerts_and_csv_export() -> None:
    totals = {
        "tokens": 150,
        "error_rate_pct": 22.0,
    }
    alerts = ByoLlmUsageService.build_alerts(
        totals=totals,
        daily_token_budget=100,
        error_rate_alert_pct=10.0,
    )
    assert {alert["code"] for alert in alerts} == {
        "daily_token_budget_exceeded",
        "error_rate_threshold_exceeded",
    }

    records = _build_sample_records()
    report = ByoLlmUsageService.aggregate_records(records)
    csv_payload = ByoLlmUsageService.report_to_csv(report)
    lines = [line for line in csv_payload.splitlines() if line.strip()]
    assert lines[0].startswith("message_id,conversation_id,user_id")
    assert len(lines) == 4  # header + 3 rows
