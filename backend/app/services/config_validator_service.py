"""
ConfigValidatorService — Validacao rule-based de configs contra best practices.

Regras cobrindo: security, reliability, performance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ValidationIssue:
    """Issue encontrada durante validacao."""

    severity: str  # "critical" | "warning" | "info"
    category: str  # "security" | "reliability" | "performance"
    description: str
    recommendation: str
    line_reference: str | None = None


# Tipo para funcoes de regra: recebem config_text e retornam lista de issues
RuleFunc = Callable[[str], list[ValidationIssue]]


class ConfigValidatorService:
    """Valida configs contra best practices de networking."""

    def __init__(self) -> None:
        self._rules: list[RuleFunc] = [
            # Security
            self._check_telnet_enabled,
            self._check_password_encryption,
            self._check_enable_password_vs_secret,
            self._check_snmp_version,
            self._check_ssh_version,
            self._check_console_password,
            self._check_vty_acl,
            # Reliability
            self._check_ospf_authentication,
            self._check_bgp_authentication,
            self._check_spanning_tree_mode,
            self._check_interface_descriptions,
            self._check_logging_buffered,
            self._check_ntp_configured,
            self._check_syslog_server,
            # Performance
            self._check_mtu_consistency,
            self._check_ip_route_cache,
        ]

    def validate(self, config_text: str, vendor: str = "cisco") -> list[ValidationIssue]:
        """Executa todas as regras e retorna issues encontradas.

        Args:
            config_text: Texto da configuracao.
            vendor: Vendor da config (apenas 'cisco' suportado para validacao).

        Returns:
            Lista de ValidationIssue ordenada por severity.
        """
        if vendor != "cisco":
            return [
                ValidationIssue(
                    severity="info",
                    category="general",
                    description=f"Validation rules are optimized for Cisco IOS. "
                    f"Vendor '{vendor}' may have false positives.",
                    recommendation="Review results considering vendor-specific syntax.",
                )
            ]

        issues: list[ValidationIssue] = []
        for rule in self._rules:
            issues.extend(rule(config_text))

        # Ordena: critical > warning > info
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        issues.sort(key=lambda i: severity_order.get(i.severity, 3))
        return issues

    def format_report(self, issues: list[ValidationIssue]) -> str:
        """Formata relatorio de validacao para o LLM.

        Args:
            issues: Lista de issues encontradas.

        Returns:
            Texto formatado com issues agrupadas por severity.
        """
        if not issues:
            return (
                "## Configuration Validation Report\n\n"
                "No issues found. The configuration follows best practices."
            )

        critical = [i for i in issues if i.severity == "critical"]
        warnings = [i for i in issues if i.severity == "warning"]
        info = [i for i in issues if i.severity == "info"]

        parts: list[str] = ["## Configuration Validation Report"]
        parts.append(
            f"\n**Summary:** {len(critical)} critical, "
            f"{len(warnings)} warnings, {len(info)} informational"
        )

        if critical:
            parts.append("\n### CRITICAL Issues")
            for i, issue in enumerate(critical, 1):
                parts.append(self._format_issue(i, issue))

        if warnings:
            parts.append("\n### Warnings")
            for i, issue in enumerate(warnings, 1):
                parts.append(self._format_issue(i, issue))

        if info:
            parts.append("\n### Informational")
            for i, issue in enumerate(info, 1):
                parts.append(self._format_issue(i, issue))

        return "\n".join(parts)

    @staticmethod
    def _format_issue(index: int, issue: ValidationIssue) -> str:
        line_ref = f" (near: `{issue.line_reference}`)" if issue.line_reference else ""
        return (
            f"{index}. **[{issue.category.upper()}]** {issue.description}{line_ref}\n"
            f"   → Recommendation: {issue.recommendation}"
        )

    # ─────────────────────────────────────────────────────────
    #  Security Rules
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _check_telnet_enabled(config: str) -> list[ValidationIssue]:
        """Telnet habilitado sem SSH."""
        issues: list[ValidationIssue] = []
        has_telnet = bool(re.search(r"transport input.*telnet", config, re.IGNORECASE))
        has_ssh = bool(re.search(r"transport input.*ssh", config, re.IGNORECASE))

        if has_telnet and not has_ssh:
            issues.append(
                ValidationIssue(
                    severity="critical",
                    category="security",
                    description="Telnet is enabled without SSH. Telnet transmits credentials in plaintext.",
                    recommendation="Replace 'transport input telnet' with 'transport input ssh' on all VTY lines.",
                    line_reference="transport input telnet",
                )
            )
        elif has_telnet and has_ssh:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="security",
                    description="Telnet is enabled alongside SSH. Telnet should be disabled.",
                    recommendation="Use 'transport input ssh' only. Remove telnet from transport input.",
                    line_reference="transport input telnet ssh",
                )
            )
        return issues

    @staticmethod
    def _check_password_encryption(config: str) -> list[ValidationIssue]:
        """Verifica service password-encryption."""
        issues: list[ValidationIssue] = []
        if re.search(r"^no service password-encryption", config, re.MULTILINE):
            issues.append(
                ValidationIssue(
                    severity="critical",
                    category="security",
                    description="Password encryption is explicitly disabled (no service password-encryption).",
                    recommendation="Enable with 'service password-encryption' to encrypt passwords in config.",
                    line_reference="no service password-encryption",
                )
            )
        elif not re.search(r"^service password-encryption", config, re.MULTILINE):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="security",
                    description="'service password-encryption' is not configured. Passwords may be stored in plaintext.",
                    recommendation="Add 'service password-encryption' in global config.",
                )
            )
        return issues

    @staticmethod
    def _check_enable_password_vs_secret(config: str) -> list[ValidationIssue]:
        """enable password (type 0/7) em vez de enable secret (type 5/8/9)."""
        issues: list[ValidationIssue] = []
        if re.search(r"^enable password\s+", config, re.MULTILINE):
            issues.append(
                ValidationIssue(
                    severity="critical",
                    category="security",
                    description="'enable password' uses weak reversible encryption (type 7). Use 'enable secret' instead.",
                    recommendation="Replace 'enable password' with 'enable secret' for MD5/scrypt hashing.",
                    line_reference="enable password",
                )
            )
        return issues

    @staticmethod
    def _check_snmp_version(config: str) -> list[ValidationIssue]:
        """SNMPv1/v2 sem v3."""
        issues: list[ValidationIssue] = []
        has_snmpv2 = bool(
            re.search(r"snmp-server community\s+", config, re.MULTILINE)
        )
        has_snmpv3 = bool(
            re.search(r"snmp-server group\s+.*v3", config, re.MULTILINE)
        )

        if has_snmpv2 and not has_snmpv3:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="security",
                    description="SNMP v1/v2c community strings are configured without SNMPv3. Community strings are sent in plaintext.",
                    recommendation="Migrate to SNMPv3 with authentication and encryption (authPriv).",
                    line_reference="snmp-server community",
                )
            )

        # Check for default community strings
        if re.search(
            r"snmp-server community\s+(public|private)\s+",
            config,
            re.MULTILINE | re.IGNORECASE,
        ):
            issues.append(
                ValidationIssue(
                    severity="critical",
                    category="security",
                    description="Default SNMP community string (public/private) detected.",
                    recommendation="Change community strings to non-default, complex values.",
                    line_reference="snmp-server community public/private",
                )
            )

        return issues

    @staticmethod
    def _check_ssh_version(config: str) -> list[ValidationIssue]:
        """SSH version 1 ou sem version 2 explicito."""
        issues: list[ValidationIssue] = []
        if re.search(r"^ip ssh version\s+1\b", config, re.MULTILINE):
            issues.append(
                ValidationIssue(
                    severity="critical",
                    category="security",
                    description="SSH version 1 is configured. SSHv1 has known vulnerabilities.",
                    recommendation="Use 'ip ssh version 2' for secure SSH connections.",
                    line_reference="ip ssh version 1",
                )
            )
        elif re.search(r"transport input.*ssh", config) and not re.search(
            r"^ip ssh version\s+2", config, re.MULTILINE
        ):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="security",
                    description="SSH is enabled but version 2 is not explicitly enforced.",
                    recommendation="Add 'ip ssh version 2' to enforce SSHv2 only.",
                )
            )
        return issues

    @staticmethod
    def _check_console_password(config: str) -> list[ValidationIssue]:
        """Console sem autenticacao."""
        issues: list[ValidationIssue] = []
        console_match = re.search(
            r"^line con 0\s*\n((?:\s+.*\n)*)", config, re.MULTILINE
        )
        if console_match:
            console_config = console_match.group(1)
            if "login" not in console_config and "password" not in console_config:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="security",
                        description="Console line (con 0) has no authentication configured.",
                        recommendation="Configure 'login local' and 'password' on line con 0.",
                        line_reference="line con 0",
                    )
                )
        return issues

    @staticmethod
    def _check_vty_acl(config: str) -> list[ValidationIssue]:
        """VTY lines sem ACL."""
        issues: list[ValidationIssue] = []
        vty_match = re.search(
            r"^line vty\s+\d+\s+\d+\s*\n((?:\s+.*\n)*)", config, re.MULTILINE
        )
        if vty_match:
            vty_config = vty_match.group(1)
            if "access-class" not in vty_config:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="security",
                        description="VTY lines have no access-class (ACL) restricting management access.",
                        recommendation="Apply an ACL with 'access-class <ACL_NAME> in' on VTY lines.",
                        line_reference="line vty",
                    )
                )
        return issues

    # ─────────────────────────────────────────────────────────
    #  Reliability Rules
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _check_ospf_authentication(config: str) -> list[ValidationIssue]:
        """OSPF sem autenticacao."""
        issues: list[ValidationIssue] = []
        if re.search(r"^router ospf\s+", config, re.MULTILINE):
            has_area_auth = bool(
                re.search(r"area\s+\S+\s+authentication", config, re.MULTILINE)
            )
            has_intf_auth = bool(
                re.search(r"ip ospf authentication", config, re.MULTILINE)
            )
            if not has_area_auth and not has_intf_auth:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="reliability",
                        description="OSPF is configured without authentication. Rogue routers could inject routes.",
                        recommendation="Enable OSPF authentication (MD5 or SHA) per area or interface.",
                        line_reference="router ospf",
                    )
                )
        return issues

    @staticmethod
    def _check_bgp_authentication(config: str) -> list[ValidationIssue]:
        """BGP neighbors sem password."""
        issues: list[ValidationIssue] = []
        bgp_neighbors = re.findall(
            r"neighbor\s+(\S+)\s+remote-as\s+\d+", config
        )
        for neighbor in bgp_neighbors:
            # Procura password para este neighbor
            pattern = rf"neighbor\s+{re.escape(neighbor)}\s+password\s+"
            if not re.search(pattern, config):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="reliability",
                        description=f"BGP neighbor {neighbor} has no MD5 authentication configured.",
                        recommendation=f"Add 'neighbor {neighbor} password <key>' for BGP session security.",
                        line_reference=f"neighbor {neighbor} remote-as",
                    )
                )
        return issues

    @staticmethod
    def _check_spanning_tree_mode(config: str) -> list[ValidationIssue]:
        """Spanning-tree mode nao rapid-pvst."""
        issues: list[ValidationIssue] = []
        stp_match = re.search(r"^spanning-tree mode\s+(\S+)", config, re.MULTILINE)
        if stp_match:
            mode = stp_match.group(1).lower()
            if mode not in ("rapid-pvst", "mst"):
                issues.append(
                    ValidationIssue(
                        severity="info",
                        category="reliability",
                        description=f"Spanning-tree mode is '{mode}'. Rapid-PVST+ provides faster convergence.",
                        recommendation="Consider 'spanning-tree mode rapid-pvst' for faster failover.",
                        line_reference=f"spanning-tree mode {mode}",
                    )
                )
        return issues

    @staticmethod
    def _check_interface_descriptions(config: str) -> list[ValidationIssue]:
        """Interfaces com IP sem description."""
        issues: list[ValidationIssue] = []
        # Encontra interfaces com IP mas sem description
        intf_blocks = re.findall(
            r"^(interface\s+\S+)\s*\n((?:\s+.*\n)*)",
            config,
            re.MULTILINE,
        )
        no_desc_count = 0
        for intf_header, body in intf_blocks:
            has_ip = bool(re.search(r"ip address\s+\d+", body))
            has_desc = bool(re.search(r"description\s+", body))
            if has_ip and not has_desc:
                no_desc_count += 1

        if no_desc_count > 0:
            issues.append(
                ValidationIssue(
                    severity="info",
                    category="reliability",
                    description=f"{no_desc_count} interface(s) with IP addresses lack descriptions.",
                    recommendation="Add 'description' to interfaces for easier troubleshooting and documentation.",
                )
            )
        return issues

    @staticmethod
    def _check_logging_buffered(config: str) -> list[ValidationIssue]:
        """Sem logging buffered."""
        issues: list[ValidationIssue] = []
        if not re.search(r"^logging buffered\s+", config, re.MULTILINE):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="reliability",
                    description="'logging buffered' is not configured. Log messages may be lost.",
                    recommendation="Add 'logging buffered <size> informational' to retain logs locally.",
                )
            )
        return issues

    @staticmethod
    def _check_ntp_configured(config: str) -> list[ValidationIssue]:
        """Sem NTP configurado."""
        issues: list[ValidationIssue] = []
        if not re.search(r"^ntp server\s+", config, re.MULTILINE):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="reliability",
                    description="No NTP server configured. Accurate time is critical for logging and certificates.",
                    recommendation="Configure at least two NTP servers with 'ntp server <IP>'.",
                )
            )
        return issues

    @staticmethod
    def _check_syslog_server(config: str) -> list[ValidationIssue]:
        """Sem syslog server externo."""
        issues: list[ValidationIssue] = []
        if not re.search(r"^logging\s+\d+\.\d+\.\d+\.\d+", config, re.MULTILINE) and \
           not re.search(r"^logging host\s+", config, re.MULTILINE):
            issues.append(
                ValidationIssue(
                    severity="info",
                    category="reliability",
                    description="No external syslog server configured.",
                    recommendation="Add 'logging host <IP>' to send logs to a central syslog server.",
                )
            )
        return issues

    # ─────────────────────────────────────────────────────────
    #  Performance Rules
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _check_mtu_consistency(config: str) -> list[ValidationIssue]:
        """MTU nao padrao em interfaces."""
        issues: list[ValidationIssue] = []
        mtu_values = re.findall(r"^\s+ip mtu\s+(\d+)", config, re.MULTILINE)
        mtu_values += re.findall(r"^\s+mtu\s+(\d+)", config, re.MULTILINE)

        unique_mtus = set(mtu_values)
        if len(unique_mtus) > 1:
            issues.append(
                ValidationIssue(
                    severity="info",
                    category="performance",
                    description=f"Multiple MTU values found ({', '.join(sorted(unique_mtus))}). "
                    "Inconsistent MTU can cause fragmentation.",
                    recommendation="Verify MTU consistency across the path. Use 'ip mtu' or 'mtu' consistently.",
                )
            )
        return issues

    @staticmethod
    def _check_ip_route_cache(config: str) -> list[ValidationIssue]:
        """no ip route-cache em interface."""
        issues: list[ValidationIssue] = []
        count = len(re.findall(r"^\s+no ip route-cache", config, re.MULTILINE))
        if count > 0:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="performance",
                    description=f"'no ip route-cache' found on {count} interface(s). This disables fast switching.",
                    recommendation="Remove 'no ip route-cache' unless specifically needed for policy routing.",
                    line_reference="no ip route-cache",
                )
            )
        return issues
