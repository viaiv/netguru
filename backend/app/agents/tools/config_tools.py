"""
Config tools para o agent LangGraph — parse_config e validate_config.

Operam em texto puro (nao precisam de db ou user_id).
"""
from __future__ import annotations

from langchain_core.tools import StructuredTool

from app.services.config_parser_service import ConfigParserService
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
