"""
BYO-LLM usage analytics service.

Aggregates assistant message metadata to provide:
- usage totals (messages/tokens/latency/error rate)
- breakdown by provider/model and by tool
- budget/quality alerts
- export rows for CSV/JSON
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message
from app.services.system_settings_service import SystemSettingsService


class ByoLlmUsageService:
    """Compute BYO-LLM usage analytics from chat message metadata."""

    @classmethod
    async def build_report(
        cls,
        db: AsyncSession,
        *,
        start_date: date,
        end_date: date,
        provider_filter: str | None = None,
        user_id: UUID | None = None,
    ) -> dict[str, Any]:
        """
        Build full usage report for admin/user dashboards.
        """
        records = await cls._load_assistant_records(
            db=db,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
        )
        aggregated = cls.aggregate_records(records, provider_filter=provider_filter)

        token_budget = cls._safe_int(
            await cls._safe_get_setting(db, "byollm_daily_token_budget"),
            default=0,
        )
        error_rate_alert_pct = cls._safe_float(
            await cls._safe_get_setting(db, "byollm_error_rate_alert_pct"),
            default=15.0,
        )

        aggregated["alerts"] = cls.build_alerts(
            totals=aggregated["totals"],
            daily_token_budget=token_budget,
            error_rate_alert_pct=error_rate_alert_pct,
        )
        return {
            "start_date": start_date,
            "end_date": end_date,
            "provider_filter": provider_filter,
            **aggregated,
        }

    @classmethod
    async def _load_assistant_records(
        cls,
        *,
        db: AsyncSession,
        start_date: date,
        end_date: date,
        user_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date + timedelta(days=1), time.min)

        stmt = (
            select(
                Message.id.label("message_id"),
                Message.conversation_id,
                Message.created_at,
                Message.tokens_used,
                Message.content,
                Message.message_metadata,
                Conversation.user_id,
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Message.role == "assistant",
                Message.created_at >= start_dt,
                Message.created_at < end_dt,
            )
            .order_by(Message.created_at.asc())
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)

        result = await db.execute(stmt)
        rows = result.mappings().all()
        return [dict(row) for row in rows]

    @classmethod
    def aggregate_records(
        cls,
        records: list[dict[str, Any]],
        *,
        provider_filter: str | None = None,
    ) -> dict[str, Any]:
        """
        Aggregate records into totals, provider/model breakdown, and tool breakdown.
        """
        provider_filter_norm = provider_filter.lower().strip() if provider_filter else None

        total_messages = 0
        total_tokens = 0
        message_latencies: list[int] = []
        attempts_total = 0
        attempts_failed = 0
        tool_calls_total = 0
        tool_calls_failed = 0

        provider_model_stats: dict[tuple[str, str], dict[str, Any]] = {}
        tool_stats: dict[str, dict[str, Any]] = {}
        export_rows: list[dict[str, Any]] = []

        for record in records:
            metadata = record.get("message_metadata")
            metadata = metadata if isinstance(metadata, dict) else {}

            llm_execution = metadata.get("llm_execution")
            llm_execution = llm_execution if isinstance(llm_execution, dict) else {}
            provider = str(llm_execution.get("selected_provider") or "unknown").lower()
            model = str(llm_execution.get("selected_model") or "default")
            if provider_filter_norm and provider != provider_filter_norm:
                continue

            tokens_used = record.get("tokens_used")
            if isinstance(tokens_used, int) and tokens_used > 0:
                tokens = tokens_used
            else:
                tokens = cls._estimate_tokens(str(record.get("content") or ""))

            attempts = llm_execution.get("attempts")
            attempts = attempts if isinstance(attempts, list) else []
            attempts_count = max(1, len(attempts))
            failed_attempt_count = sum(
                1
                for attempt in attempts
                if isinstance(attempt, dict)
                and str(attempt.get("status", "")).startswith("failed")
            )
            latency_ms = sum(
                int(attempt.get("duration_ms", 0) or 0)
                for attempt in attempts
                if isinstance(attempt, dict)
            )
            if latency_ms > 0:
                message_latencies.append(latency_ms)

            tool_calls = metadata.get("tool_calls")
            tool_calls = tool_calls if isinstance(tool_calls, list) else []
            row_tool_calls = 0
            row_tool_failures = 0
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                tool_name = str(tool_call.get("tool") or "unknown")
                tool_status = str(tool_call.get("status") or "unknown")
                tool_duration = int(tool_call.get("duration_ms", 0) or 0)

                stats = tool_stats.setdefault(
                    tool_name,
                    {
                        "tool": tool_name,
                        "calls": 0,
                        "failed_calls": 0,
                        "durations_ms": [],
                    },
                )
                stats["calls"] += 1
                row_tool_calls += 1
                if tool_duration > 0:
                    stats["durations_ms"].append(tool_duration)
                if tool_status == "failed":
                    stats["failed_calls"] += 1
                    row_tool_failures += 1

            total_messages += 1
            total_tokens += tokens
            attempts_total += attempts_count
            attempts_failed += failed_attempt_count
            tool_calls_total += row_tool_calls
            tool_calls_failed += row_tool_failures

            pm_key = (provider, model)
            pm_stats = provider_model_stats.setdefault(
                pm_key,
                {
                    "provider": provider,
                    "model": model,
                    "messages": 0,
                    "tokens": 0,
                    "latencies_ms": [],
                    "attempts_total": 0,
                    "attempts_failed": 0,
                },
            )
            pm_stats["messages"] += 1
            pm_stats["tokens"] += tokens
            pm_stats["attempts_total"] += attempts_count
            pm_stats["attempts_failed"] += failed_attempt_count
            if latency_ms > 0:
                pm_stats["latencies_ms"].append(latency_ms)

            export_rows.append(
                {
                    "message_id": record.get("message_id"),
                    "conversation_id": record.get("conversation_id"),
                    "user_id": record.get("user_id"),
                    "created_at": record.get("created_at"),
                    "provider": provider,
                    "model": model,
                    "tokens": tokens,
                    "latency_ms": latency_ms,
                    "attempts_total": attempts_count,
                    "attempts_failed": failed_attempt_count,
                    "tool_calls_total": row_tool_calls,
                    "tool_calls_failed": row_tool_failures,
                    "fallback_triggered": llm_execution.get("fallback_triggered") is True,
                }
            )

        error_rate_pct = (
            round((attempts_failed / attempts_total) * 100, 2)
            if attempts_total > 0
            else 0.0
        )

        by_provider_model = sorted(
            [
                {
                    "provider": stats["provider"],
                    "model": stats["model"],
                    "messages": stats["messages"],
                    "tokens": stats["tokens"],
                    "avg_latency_ms": round(cls._avg(stats["latencies_ms"]), 2),
                    "error_rate_pct": round(
                        (stats["attempts_failed"] / stats["attempts_total"]) * 100, 2
                    )
                    if stats["attempts_total"] > 0
                    else 0.0,
                }
                for stats in provider_model_stats.values()
            ],
            key=lambda row: row["messages"],
            reverse=True,
        )

        by_tool = sorted(
            [
                {
                    "tool": stats["tool"],
                    "calls": stats["calls"],
                    "failed_calls": stats["failed_calls"],
                    "avg_duration_ms": round(cls._avg(stats["durations_ms"]), 2),
                    "error_rate_pct": round(
                        (stats["failed_calls"] / stats["calls"]) * 100, 2
                    )
                    if stats["calls"] > 0
                    else 0.0,
                }
                for stats in tool_stats.values()
            ],
            key=lambda row: row["calls"],
            reverse=True,
        )

        totals = {
            "messages": total_messages,
            "tokens": total_tokens,
            "latency_p50_ms": round(cls._percentile(message_latencies, 50), 2),
            "latency_p95_ms": round(cls._percentile(message_latencies, 95), 2),
            "error_rate_pct": error_rate_pct,
            "attempts_total": attempts_total,
            "attempts_failed": attempts_failed,
            "tool_calls_total": tool_calls_total,
            "tool_calls_failed": tool_calls_failed,
        }

        return {
            "totals": totals,
            "by_provider_model": by_provider_model,
            "by_tool": by_tool,
            "export_rows": export_rows,
        }

    @staticmethod
    def build_alerts(
        *,
        totals: dict[str, Any],
        daily_token_budget: int,
        error_rate_alert_pct: float,
    ) -> list[dict[str, Any]]:
        """Build simple budget/quality alerts from aggregated totals."""
        alerts: list[dict[str, Any]] = []

        tokens = int(totals.get("tokens", 0) or 0)
        if daily_token_budget > 0 and tokens >= daily_token_budget:
            alerts.append(
                {
                    "code": "daily_token_budget_exceeded",
                    "severity": "warning",
                    "message": (
                        f"Consumo de tokens ({tokens}) ultrapassou limite diario ({daily_token_budget})."
                    ),
                    "current_value": float(tokens),
                    "threshold": float(daily_token_budget),
                }
            )

        error_rate = float(totals.get("error_rate_pct", 0.0) or 0.0)
        if error_rate_alert_pct > 0 and error_rate >= error_rate_alert_pct:
            alerts.append(
                {
                    "code": "error_rate_threshold_exceeded",
                    "severity": "critical",
                    "message": (
                        f"Taxa de erro ({error_rate:.2f}%) acima do limite ({error_rate_alert_pct:.2f}%)."
                    ),
                    "current_value": error_rate,
                    "threshold": float(error_rate_alert_pct),
                }
            )
        return alerts

    @classmethod
    def report_to_csv(cls, report: dict[str, Any]) -> str:
        """
        Render export rows as CSV payload.
        """
        output = io.StringIO()
        fieldnames = [
            "message_id",
            "conversation_id",
            "user_id",
            "created_at",
            "provider",
            "model",
            "tokens",
            "latency_ms",
            "attempts_total",
            "attempts_failed",
            "tool_calls_total",
            "tool_calls_failed",
            "fallback_triggered",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for row in report.get("export_rows", []):
            if not isinstance(row, dict):
                continue
            created_at = row.get("created_at")
            normalized_created_at = (
                created_at.isoformat()
                if isinstance(created_at, datetime)
                else str(created_at or "")
            )
            writer.writerow(
                {
                    **row,
                    "created_at": normalized_created_at,
                }
            )

        return output.getvalue()

    @staticmethod
    async def _safe_get_setting(db: AsyncSession, key: str) -> str | None:
        try:
            return await SystemSettingsService.get(db, key)
        except Exception:
            return None

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """
        Rough token estimation fallback when provider token usage is unavailable.
        """
        normalized = " ".join(text.split())
        if not normalized:
            return 0
        return max(1, (len(normalized) + 3) // 4)

    @staticmethod
    def _avg(values: list[int]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def _percentile(values: list[int], percentile: int) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return float(ordered[0])
        idx = (len(ordered) - 1) * (percentile / 100)
        lower = int(idx)
        upper = min(lower + 1, len(ordered) - 1)
        if lower == upper:
            return float(ordered[lower])
        weight = idx - lower
        return (ordered[lower] * (1 - weight)) + (ordered[upper] * weight)

    @staticmethod
    def _safe_int(value: str | None, *, default: int) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: str | None, *, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
