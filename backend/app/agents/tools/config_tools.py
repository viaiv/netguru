"""
Config tools para o agent LangGraph — parse_config e validate_config.

Operam em texto puro (nao precisam de db ou user_id).
"""
from __future__ import annotations

from langchain_core.tools import StructuredTool

from app.services.config_diff_service import ConfigDiffService
from app.services.config_parser_service import ConfigParserService
from app.services.pre_change_review_service import PreChangeReviewService
from app.services.config_validator_service import ConfigValidatorService


def create_parse_config_tool() -> StructuredTool:
    """Cria tool de parsing de configuracoes de rede."""

    async def _parse_config(config_text: str) -> str:
        """
        Parse and analyze a network device configuration (Cisco IOS/NX-OS or Juniper).
        Extracts interfaces, routing protocols, ACLs, VLANs, and general settings.

        Use this tool when the user pastes a device configuration or asks you to
        analyze/explain a config. The tool auto-detects the vendor (Cisco or Juniper).

        Args:
            config_text: The full or partial network device configuration text.
        """
        try:
            svc = ConfigParserService()
            parsed = svc.parse(config_text)
            return svc.format_analysis(parsed)
        except Exception as e:
            return f"Error parsing configuration: {e}"

    return StructuredTool.from_function(
        coroutine=_parse_config,
        name="parse_config",
        description=(
            "Parse and analyze a network device configuration (Cisco IOS/NX-OS, Juniper). "
            "Extracts interfaces, routing protocols (OSPF, BGP, EIGRP), ACLs, VLANs, and general settings. "
            "Use when the user pastes a configuration or asks to analyze/explain a config. "
            "Auto-detects vendor. Input: the configuration text."
        ),
    )


def create_validate_config_tool() -> StructuredTool:
    """Cria tool de validacao de configs contra best practices."""

    async def _validate_config(config_text: str) -> str:
        """
        Validate a network configuration against security, reliability, and performance
        best practices. Returns a report with issues grouped by severity (critical, warning, info).

        Use this tool when the user asks to validate, review, audit, or check a
        configuration for issues or best practices.

        Args:
            config_text: The full network device configuration text to validate.
        """
        try:
            parser = ConfigParserService()
            vendor = parser.detect_vendor(config_text)

            validator = ConfigValidatorService()
            issues = validator.validate(config_text, vendor)
            return validator.format_report(issues)
        except Exception as e:
            return f"Error validating configuration: {e}"

    return StructuredTool.from_function(
        coroutine=_validate_config,
        name="validate_config",
        description=(
            "Validate a network configuration against security, reliability, and performance "
            "best practices. Returns a report with issues grouped by severity. "
            "Checks for: telnet usage, weak passwords, SNMP security, OSPF/BGP authentication, "
            "NTP, logging, spanning-tree, and more. "
            "Use when the user asks to validate, review, audit, or check a config for issues."
        ),
    )


def create_diff_config_risk_tool() -> StructuredTool:
    """Cria tool de diff semantico com analise de risco (running x golden)."""

    async def _diff_config_risk(
        running_config: str,
        golden_config: str,
        running_label: str = "running",
        golden_label: str = "golden",
    ) -> str:
        """
        Compare current (running) and baseline (golden) configurations.
        Produces semantic diff by section and risk scoring (security/availability/performance).

        Use this tool when the user asks to compare two configs, assess change risk,
        detect drift, or prepare pre-change review/rollback guidance.

        Args:
            running_config: Current device configuration text.
            golden_config: Baseline/golden configuration text.
            running_label: Friendly name for running config in the report.
            golden_label: Friendly name for golden config in the report.
        """
        try:
            svc = ConfigDiffService()
            report = svc.compare_configs(
                running_config=running_config,
                golden_config=golden_config,
            )
            return svc.format_report(
                report=report,
                running_label=running_label,
                golden_label=golden_label,
            )
        except Exception as e:
            return f"Error comparing configurations: {e}"

    return StructuredTool.from_function(
        coroutine=_diff_config_risk,
        name="diff_config_risk",
        description=(
            "Compare running vs golden network configurations and return semantic diff "
            "by sections (interfaces, routing, ACL, VLAN, services), risk scores "
            "(security/availability/performance), critical changes, and rollback "
            "recommendations. Use for pre-change risk analysis and drift detection."
        ),
    )


def create_pre_change_review_tool() -> StructuredTool:
    """Cria tool de pre-change review com decisao assistida."""

    async def _pre_change_review(
        change_proposal: str,
        running_config: str = "",
        golden_config: str = "",
    ) -> str:
        """
        Review a proposed network change before execution.
        Produces impact matrix, pre-check/post-check lists, and go/no-go decision.

        Use this tool when the user asks for pre-change assessment, impact review,
        change advisory support, go/no-go recommendation, or risk validation.

        Args:
            change_proposal: Proposed command/config/text describing the change.
            running_config: Optional current config for deeper context.
            golden_config: Optional baseline/golden config for drift/risk enrichment.
        """
        try:
            svc = PreChangeReviewService()
            report = svc.review_change(
                change_proposal=change_proposal,
                running_config=running_config.strip() or None,
                golden_config=golden_config.strip() or None,
            )
            return svc.format_report(report)
        except Exception as e:
            return f"Error reviewing pre-change proposal: {e}"

    return StructuredTool.from_function(
        coroutine=_pre_change_review,
        name="pre_change_review",
        description=(
            "Evaluate a proposed network change before execution. Returns impact matrix "
            "(routing, security, convergence, observability), pre/post operational checks, "
            "automated post-change playbook, and assisted decision (go/no-go/go with mitigation). "
            "Use for CAB-style pre-change validation and risk control."
        ),
    )
