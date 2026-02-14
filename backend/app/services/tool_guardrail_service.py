"""
ToolGuardrailService — role/plan authorization and critical-action confirmation for agent tools.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_log_service import AuditLogService
from app.services.system_settings_service import SystemSettingsService


GUARDRAIL_SETTINGS_KEY = "agent_tool_guardrails_policy"

DEFAULT_GUARDRAIL_POLICY: dict[str, Any] = {
    "version": 1,
    "confirmation_phrases": [
        "confirmo",
        "confirmado",
        "autorizo",
        "aprovado",
        "pode executar",
        "i confirm",
        "approved",
    ],
    "tools": {
        "pre_change_review": {
            "sensitive": True,
            "require_confirmation": True,
            "allowed_roles": ["owner", "admin", "member"],
            "allowed_plans": ["solo", "team", "enterprise"],
        },
        "diff_config_risk": {
            "sensitive": True,
            "require_confirmation": False,
            "allowed_roles": ["owner", "admin", "member"],
            "allowed_plans": ["solo", "team", "enterprise"],
        },
        "analyze_pcap": {
            "sensitive": True,
            "require_confirmation": True,
            "allowed_roles": ["owner", "admin", "member"],
            "allowed_plans": ["team", "enterprise"],
        },
    },
}


@dataclass(frozen=True)
class GuardrailDecision:
    """Decision for one tool invocation attempt."""

    allowed: bool
    reason_code: str | None = None
    message: str | None = None
    policy_source: str = "default"


class ToolGuardrailService:
    """
    Enforces per-tool guardrails based on role/plan and explicit confirmation.
    """

    def __init__(
        self,
        *,
        db: AsyncSession,
        user_id: UUID,
        user_role: str | None,
        plan_tier: str | None,
        user_message: str,
    ) -> None:
        self._db = db
        self._user_id = user_id
        self._user_role = self._normalize_token(user_role)
        self._plan_tier = self._normalize_token(plan_tier)
        self._user_message = self._normalize_text(user_message)
        self._policy_cache: tuple[dict[str, Any], str] | None = None

    def wrap_tools(self, tools: list[BaseTool]) -> list[BaseTool]:
        """
        Wrap tool list with guardrail checks while preserving tool schemas.
        """
        return [self.wrap_tool(tool) for tool in tools]

    def wrap_tool(self, tool: BaseTool) -> BaseTool:
        """
        Wrap one LangChain tool with guardrail enforcement.
        """

        async def _guarded(**kwargs: Any) -> str:
            decision = await self.authorize_tool(tool_name=tool.name)
            if not decision.allowed:
                return decision.message or "BLOCKED_BY_GUARDRAIL"

            try:
                payload: Any = kwargs
                if len(kwargs) == 1 and not getattr(tool, "args_schema", None):
                    payload = next(iter(kwargs.values()))
                result = await tool.ainvoke(payload)
                return str(result)
            except Exception as exc:  # pragma: no cover - defensive fallback
                return f"Error executing tool '{tool.name}': {exc}"

        return StructuredTool.from_function(
            coroutine=_guarded,
            name=tool.name,
            description=tool.description,
            args_schema=getattr(tool, "args_schema", None),
            return_direct=getattr(tool, "return_direct", False),
        )

    async def authorize_tool(self, *, tool_name: str) -> GuardrailDecision:
        """
        Evaluate access for a tool call and return allow/deny decision.
        """
        policy, policy_source = await self._load_policy()
        tools_policy = policy.get("tools", {}) if isinstance(policy, dict) else {}
        if not isinstance(tools_policy, dict):
            tools_policy = {}

        tool_policy = tools_policy.get(tool_name, {})
        if not isinstance(tool_policy, dict):
            tool_policy = {}

        allowed_roles = self._normalize_tokens(tool_policy.get("allowed_roles"))
        allowed_plans = self._normalize_tokens(tool_policy.get("allowed_plans"))
        require_confirmation = bool(tool_policy.get("require_confirmation", False))

        if allowed_roles and self._user_role not in allowed_roles:
            return await self._deny(
                tool_name=tool_name,
                policy_source=policy_source,
                reason_code="role_denied",
                details={
                    "user_role": self._user_role,
                    "allowed_roles": sorted(allowed_roles),
                    "user_plan": self._plan_tier,
                },
                next_step=(
                    "Solicite acesso a um administrador com role adequado para esta tool."
                ),
            )

        if allowed_plans and self._plan_tier not in allowed_plans:
            return await self._deny(
                tool_name=tool_name,
                policy_source=policy_source,
                reason_code="plan_denied",
                details={
                    "user_plan": self._plan_tier,
                    "allowed_plans": sorted(allowed_plans),
                    "user_role": self._user_role,
                },
                next_step=(
                    "Solicite upgrade de plano para liberar esta capacidade sensivel."
                ),
            )

        if require_confirmation and not self._has_explicit_confirmation(
            tool_name=tool_name,
            policy=policy,
        ):
            return await self._deny(
                tool_name=tool_name,
                policy_source=policy_source,
                reason_code="confirmation_required",
                details={
                    "user_role": self._user_role,
                    "user_plan": self._plan_tier,
                },
                next_step=(
                    f"Responda com 'confirmo executar {tool_name}' e reenvie a solicitacao."
                ),
            )

        return GuardrailDecision(allowed=True, policy_source=policy_source)

    async def _deny(
        self,
        *,
        tool_name: str,
        policy_source: str,
        reason_code: str,
        details: dict[str, Any],
        next_step: str,
    ) -> GuardrailDecision:
        await self._record_denied_attempt(
            tool_name=tool_name,
            reason_code=reason_code,
            policy_source=policy_source,
            details=details,
            next_step=next_step,
        )

        message = (
            f"BLOCKED_BY_GUARDRAIL: Tool '{tool_name}' bloqueada por politica de seguranca "
            f"({reason_code}). Proximo passo: {next_step}"
        )
        return GuardrailDecision(
            allowed=False,
            reason_code=reason_code,
            message=message,
            policy_source=policy_source,
        )

    async def _record_denied_attempt(
        self,
        *,
        tool_name: str,
        reason_code: str,
        policy_source: str,
        details: dict[str, Any],
        next_step: str,
    ) -> None:
        try:
            await AuditLogService.record(
                self._db,
                actor_id=self._user_id,
                action="guardrail.tool_denied",
                target_type="tool",
                target_id=tool_name,
                changes={
                    "reason_code": reason_code,
                    "policy_source": policy_source,
                    "details": details,
                    "next_step": next_step,
                },
            )
        except Exception:
            # Guardrail logging must never break the user response flow.
            return

    async def _load_policy(self) -> tuple[dict[str, Any], str]:
        if self._policy_cache is not None:
            return self._policy_cache

        raw_policy = await SystemSettingsService.get(self._db, GUARDRAIL_SETTINGS_KEY)
        if raw_policy:
            try:
                parsed = json.loads(raw_policy)
                if isinstance(parsed, dict):
                    normalized = self._normalize_policy(parsed)
                    self._policy_cache = (normalized, "system_settings")
                    return self._policy_cache
            except json.JSONDecodeError:
                pass

        default_policy = self._normalize_policy(DEFAULT_GUARDRAIL_POLICY)
        self._policy_cache = (default_policy, "default")
        return self._policy_cache

    def _has_explicit_confirmation(self, *, tool_name: str, policy: dict[str, Any]) -> bool:
        phrases = self._normalize_tokens(policy.get("confirmation_phrases"))
        if not phrases:
            phrases = self._normalize_tokens(DEFAULT_GUARDRAIL_POLICY.get("confirmation_phrases"))

        if not self._user_message:
            return False

        message = self._user_message
        if (
            "nao confirmo" in message
            or "não confirmo" in message
            or "nao autorizo" in message
            or "não autorizo" in message
        ):
            return False

        tool_name_normalized = self._normalize_token(tool_name)
        confirmation_by_phrase = any(phrase in message for phrase in phrases)
        confirmation_by_tool = (
            "confirmo executar" in message and tool_name_normalized in message
        )
        return confirmation_by_phrase or confirmation_by_tool

    def _normalize_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {
            "version": int(policy.get("version", 1)),
            "confirmation_phrases": sorted(
                self._normalize_tokens(policy.get("confirmation_phrases"))
            ),
            "tools": {},
        }

        tools = policy.get("tools", {})
        if not isinstance(tools, dict):
            return normalized

        for tool_name, raw_tool_policy in tools.items():
            if not isinstance(raw_tool_policy, dict):
                continue
            normalized_tool_name = self._normalize_token(tool_name)
            if not normalized_tool_name:
                continue

            normalized["tools"][normalized_tool_name] = {
                "sensitive": bool(raw_tool_policy.get("sensitive", False)),
                "require_confirmation": bool(
                    raw_tool_policy.get("require_confirmation", False)
                ),
                "allowed_roles": sorted(
                    self._normalize_tokens(raw_tool_policy.get("allowed_roles"))
                ),
                "allowed_plans": sorted(
                    self._normalize_tokens(raw_tool_policy.get("allowed_plans"))
                ),
            }
        return normalized

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.strip().lower().split())

    @classmethod
    def _normalize_token(cls, value: str | None) -> str:
        return cls._normalize_text(value).replace("-", "_")

    @classmethod
    def _normalize_tokens(cls, value: object) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, list):
            return {
                cls._normalize_token(str(item))
                for item in value
                if cls._normalize_token(str(item))
            }
        if isinstance(value, tuple):
            return {
                cls._normalize_token(str(item))
                for item in value
                if cls._normalize_token(str(item))
            }
        if isinstance(value, str):
            normalized = cls._normalize_token(value)
            return {normalized} if normalized else set()
        return set()
