"""
ConfigDiffService — diff semantico de configuracoes com analise de risco.

Compara running x golden e produz:
- mudancas detectadas por bloco (interfaces, routing, ACL, VLAN, services)
- score de risco por categoria (security, availability, performance)
- recomendacoes de mitigacao e rollback
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.services.config_parser_service import (
    ConfigParserService,
    ParsedACL,
    ParsedConfig,
    ParsedInterface,
    ParsedRoutingProtocol,
)


@dataclass(frozen=True)
class DiffChange:
    """Representa uma mudanca semantica entre duas configuracoes."""

    section: str
    item: str
    change_type: str  # "added" | "removed" | "modified"
    details: str
    risk_category: str  # "security" | "availability" | "performance"
    risk_points: int
    critical: bool = False


@dataclass
class ConfigDiffReport:
    """Resultado final da comparacao de configuracoes."""

    running_vendor: str
    golden_vendor: str
    changes: list[DiffChange] = field(default_factory=list)
    critical_findings: list[str] = field(default_factory=list)
    risk_scores: dict[str, int] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    rollback_steps: list[str] = field(default_factory=list)


class ConfigDiffService:
    """Serviço para comparar configs e estimar risco operacional."""

    def __init__(self) -> None:
        self._parser = ConfigParserService()

    def compare_configs(
        self,
        running_config: str,
        golden_config: str,
    ) -> ConfigDiffReport:
        """
        Compara running x golden e retorna relatorio estruturado.

        Args:
            running_config: Config atual do dispositivo.
            golden_config: Config baseline/golden de referencia.

        Returns:
            ConfigDiffReport com mudancas, riscos e recomendacoes.
        """
        running = self._parser.parse(running_config)
        golden = self._parser.parse(golden_config)

        report = ConfigDiffReport(
            running_vendor=running.vendor,
            golden_vendor=golden.vendor,
        )

        self._diff_interfaces(running, golden, report)
        self._diff_routing(running, golden, report)
        self._diff_acls(running, golden, report)
        self._diff_vlans(running, golden, report)
        self._diff_services(running, golden, report)
        self._detect_critical_patterns(running, golden, running_config, golden_config, report)

        report.risk_scores = self._calculate_risk_scores(report)
        report.recommendations = self._build_recommendations(report)
        report.rollback_steps = self._build_rollback_steps(report)
        return report

    def format_report(
        self,
        report: ConfigDiffReport,
        running_label: str = "running",
        golden_label: str = "golden",
    ) -> str:
        """
        Formata relatorio em markdown.

        Args:
            report: Relatorio bruto de comparacao.
            running_label: Nome amigavel da config atual.
            golden_label: Nome amigavel da baseline.

        Returns:
            Relatorio em markdown com secoes para uso direto no chat/export.
        """
        lines: list[str] = [
            "# Relatorio de Diff de Configuracao",
            "",
            f"- Comparacao: **{running_label}** x **{golden_label}**",
            f"- Vendor detectado: running=`{report.running_vendor}`, golden=`{report.golden_vendor}`",
            "",
            "## Mudanças detectadas",
        ]

        if not report.changes:
            lines.append("- Nenhuma mudança semântica detectada entre running e golden.")
        else:
            grouped: dict[str, list[DiffChange]] = defaultdict(list)
            for change in report.changes:
                grouped[change.section].append(change)

            for section in ("interfaces", "routing", "acl", "vlan", "services"):
                section_changes = grouped.get(section, [])
                if not section_changes:
                    continue

                lines.append("")
                lines.append(f"### {section.upper()} ({len(section_changes)})")
                for change in section_changes:
                    critical_tag = " [CRITICO]" if change.critical else ""
                    lines.append(
                        f"- [{change.change_type.upper()}]{critical_tag} `{change.item}`: "
                        f"{change.details}"
                    )

        scores = report.risk_scores
        lines.extend(
            [
                "",
                "## Riscos",
                f"- Segurança: **{scores.get('security', 0)}/100** ({self._risk_level(scores.get('security', 0))})",
                f"- Disponibilidade: **{scores.get('availability', 0)}/100** ({self._risk_level(scores.get('availability', 0))})",
                f"- Performance: **{scores.get('performance', 0)}/100** ({self._risk_level(scores.get('performance', 0))})",
                f"- Risco geral: **{scores.get('overall', 0)}/100** ({self._risk_level(scores.get('overall', 0))})",
            ]
        )

        lines.append("")
        lines.append("### Mudanças críticas")
        if report.critical_findings:
            for finding in report.critical_findings:
                lines.append(f"- {finding}")
        else:
            lines.append("- Nenhuma mudança crítica detectada.")

        lines.append("")
        lines.append("## Ações recomendadas")
        for rec in report.recommendations:
            lines.append(f"- {rec}")

        lines.append("")
        lines.append("### Rollback sugerido")
        for step in report.rollback_steps:
            lines.append(f"- {step}")

        return "\n".join(lines)

    def _diff_interfaces(
        self,
        running: ParsedConfig,
        golden: ParsedConfig,
        report: ConfigDiffReport,
    ) -> None:
        running_map = {intf.name: intf for intf in running.interfaces}
        golden_map = {intf.name: intf for intf in golden.interfaces}

        for name in sorted(running_map.keys() - golden_map.keys()):
            self._add_change(
                report,
                section="interfaces",
                item=name,
                change_type="added",
                details="Interface adicionada na configuração atual.",
                risk_category="availability",
                risk_points=8,
            )

        for name in sorted(golden_map.keys() - running_map.keys()):
            self._add_change(
                report,
                section="interfaces",
                item=name,
                change_type="removed",
                details="Interface presente no golden mas ausente no running.",
                risk_category="availability",
                risk_points=14,
            )

        for name in sorted(running_map.keys() & golden_map.keys()):
            self._diff_interface_fields(running_map[name], golden_map[name], report)

    def _diff_interface_fields(
        self,
        running: ParsedInterface,
        golden: ParsedInterface,
        report: ConfigDiffReport,
    ) -> None:
        if running.shutdown != golden.shutdown:
            became_shutdown = running.shutdown and not golden.shutdown
            self._add_change(
                report,
                section="interfaces",
                item=running.name,
                change_type="modified",
                details=(
                    "Estado administrativo alterado para shutdown."
                    if became_shutdown
                    else "Estado administrativo alterado para no shutdown."
                ),
                risk_category="availability",
                risk_points=20 if became_shutdown else 8,
                critical=became_shutdown,
            )

        running_ip = self._ip_with_mask(running.ip_address, running.subnet_mask)
        golden_ip = self._ip_with_mask(golden.ip_address, golden.subnet_mask)
        if running_ip != golden_ip:
            self._add_change(
                report,
                section="interfaces",
                item=running.name,
                change_type="modified",
                details=f"Endereço IP alterado: `{golden_ip}` -> `{running_ip}`.",
                risk_category="availability",
                risk_points=12,
            )

        if running.vlan != golden.vlan:
            self._add_change(
                report,
                section="interfaces",
                item=running.name,
                change_type="modified",
                details=f"VLAN de acesso alterada: `{golden.vlan}` -> `{running.vlan}`.",
                risk_category="availability",
                risk_points=10,
            )

        if running.acl_in != golden.acl_in:
            self._add_change(
                report,
                section="interfaces",
                item=running.name,
                change_type="modified",
                details=f"ACL IN alterada: `{golden.acl_in}` -> `{running.acl_in}`.",
                risk_category="security",
                risk_points=12,
            )

        if running.acl_out != golden.acl_out:
            self._add_change(
                report,
                section="interfaces",
                item=running.name,
                change_type="modified",
                details=f"ACL OUT alterada: `{golden.acl_out}` -> `{running.acl_out}`.",
                risk_category="security",
                risk_points=12,
            )

    def _diff_routing(
        self,
        running: ParsedConfig,
        golden: ParsedConfig,
        report: ConfigDiffReport,
    ) -> None:
        running_map = {self._routing_key(p): p for p in running.routing_protocols}
        golden_map = {self._routing_key(p): p for p in golden.routing_protocols}

        for key in sorted(running_map.keys() - golden_map.keys()):
            proto = running_map[key]
            self._add_change(
                report,
                section="routing",
                item=key,
                change_type="added",
                details=f"Processo de roteamento adicionado ({proto.protocol}).",
                risk_category="availability",
                risk_points=14,
            )

        for key in sorted(golden_map.keys() - running_map.keys()):
            proto = golden_map[key]
            self._add_change(
                report,
                section="routing",
                item=key,
                change_type="removed",
                details=f"Processo de roteamento removido ({proto.protocol}).",
                risk_category="availability",
                risk_points=18,
            )

        for key in sorted(running_map.keys() & golden_map.keys()):
            self._diff_routing_fields(running_map[key], golden_map[key], key, report)

    def _diff_routing_fields(
        self,
        running: ParsedRoutingProtocol,
        golden: ParsedRoutingProtocol,
        key: str,
        report: ConfigDiffReport,
    ) -> None:
        if running.router_id != golden.router_id:
            self._add_change(
                report,
                section="routing",
                item=key,
                change_type="modified",
                details=f"Router-ID alterado: `{golden.router_id}` -> `{running.router_id}`.",
                risk_category="availability",
                risk_points=10,
            )

        running_networks = set(running.networks)
        golden_networks = set(golden.networks)
        if running_networks != golden_networks:
            self._add_change(
                report,
                section="routing",
                item=key,
                change_type="modified",
                details="Anúncios de network alterados.",
                risk_category="availability",
                risk_points=12,
            )

        running_neighbors = set(running.neighbors)
        golden_neighbors = set(golden.neighbors)
        if running_neighbors != golden_neighbors:
            self._add_change(
                report,
                section="routing",
                item=key,
                change_type="modified",
                details="Lista de neighbors alterada.",
                risk_category="availability",
                risk_points=14,
            )

    def _diff_acls(
        self,
        running: ParsedConfig,
        golden: ParsedConfig,
        report: ConfigDiffReport,
    ) -> None:
        running_map = {acl.name: acl for acl in running.acls}
        golden_map = {acl.name: acl for acl in golden.acls}

        for name in sorted(running_map.keys() - golden_map.keys()):
            self._add_change(
                report,
                section="acl",
                item=name,
                change_type="added",
                details="ACL adicionada na configuração atual.",
                risk_category="security",
                risk_points=10,
            )

        for name in sorted(golden_map.keys() - running_map.keys()):
            self._add_change(
                report,
                section="acl",
                item=name,
                change_type="removed",
                details="ACL removida da configuração atual.",
                risk_category="security",
                risk_points=16,
            )

        for name in sorted(running_map.keys() & golden_map.keys()):
            self._diff_acl_entries(running_map[name], golden_map[name], report)

    def _diff_acl_entries(
        self,
        running_acl: ParsedACL,
        golden_acl: ParsedACL,
        report: ConfigDiffReport,
    ) -> None:
        running_entries = set(running_acl.entries)
        golden_entries = set(golden_acl.entries)

        for entry in sorted(running_entries - golden_entries):
            is_permissive = self._is_acl_too_permissive(entry)
            self._add_change(
                report,
                section="acl",
                item=running_acl.name,
                change_type="modified",
                details=f"Regra adicionada: `{entry}`.",
                risk_category="security",
                risk_points=35 if is_permissive else 10,
                critical=is_permissive,
            )
            if is_permissive:
                self._add_critical(
                    report,
                    "ACL permissiva detectada: regra `permit any any`/`permit ip any any` adicionada.",
                )

        for entry in sorted(golden_entries - running_entries):
            self._add_change(
                report,
                section="acl",
                item=running_acl.name,
                change_type="modified",
                details=f"Regra removida: `{entry}`.",
                risk_category="security",
                risk_points=8,
            )

    def _diff_vlans(
        self,
        running: ParsedConfig,
        golden: ParsedConfig,
        report: ConfigDiffReport,
    ) -> None:
        running_map = {int(v["id"]): str(v.get("name", "")) for v in running.vlans if "id" in v}
        golden_map = {int(v["id"]): str(v.get("name", "")) for v in golden.vlans if "id" in v}

        for vlan_id in sorted(running_map.keys() - golden_map.keys()):
            self._add_change(
                report,
                section="vlan",
                item=f"VLAN {vlan_id}",
                change_type="added",
                details="VLAN adicionada na configuração atual.",
                risk_category="availability",
                risk_points=8,
            )

        for vlan_id in sorted(golden_map.keys() - running_map.keys()):
            self._add_change(
                report,
                section="vlan",
                item=f"VLAN {vlan_id}",
                change_type="removed",
                details="VLAN removida da configuração atual.",
                risk_category="availability",
                risk_points=12,
            )

        for vlan_id in sorted(running_map.keys() & golden_map.keys()):
            if running_map[vlan_id] != golden_map[vlan_id]:
                self._add_change(
                    report,
                    section="vlan",
                    item=f"VLAN {vlan_id}",
                    change_type="modified",
                    details=f"Nome alterado: `{golden_map[vlan_id]}` -> `{running_map[vlan_id]}`.",
                    risk_category="performance",
                    risk_points=4,
                )

    def _diff_services(
        self,
        running: ParsedConfig,
        golden: ParsedConfig,
        report: ConfigDiffReport,
    ) -> None:
        running_services = self._flatten_general_services(running.general)
        golden_services = self._flatten_general_services(golden.general)

        for line in sorted(running_services - golden_services):
            self._add_change(
                report,
                section="services",
                item="global",
                change_type="added",
                details=f"Linha adicionada: `{line}`.",
                risk_category="security" if "ssh" in line or "snmp" in line else "performance",
                risk_points=5,
            )

        for line in sorted(golden_services - running_services):
            critical = "service password-encryption" in line or "ip ssh version 2" in line
            self._add_change(
                report,
                section="services",
                item="global",
                change_type="removed",
                details=f"Linha removida: `{line}`.",
                risk_category="security",
                risk_points=20 if critical else 6,
                critical=critical,
            )
            if critical:
                self._add_critical(
                    report,
                    f"Controle de segurança removido em services: `{line}`.",
                )

    def _detect_critical_patterns(
        self,
        running: ParsedConfig,
        golden: ParsedConfig,
        running_text: str,
        golden_text: str,
        report: ConfigDiffReport,
    ) -> None:
        removed_lines = self._removed_normalized_lines(golden_text, running_text)

        if any(
            re.search(pattern, line)
            for line in removed_lines
            for pattern in (
                r"\bip ospf authentication\b",
                r"\bip ospf message-digest-key\b",
                r"\barea\s+\S+\s+authentication\b",
                r"\bneighbor\s+\S+\s+password\b",
            )
        ):
            self._add_critical(
                report,
                "Remoção de autenticação detectada (OSPF/BGP).",
            )

        running_bgp_asn = {
            str(proto.process_id)
            for proto in running.routing_protocols
            if proto.protocol.upper() == "BGP" and proto.process_id
        }
        golden_bgp_asn = {
            str(proto.process_id)
            for proto in golden.routing_protocols
            if proto.protocol.upper() == "BGP" and proto.process_id
        }
        if running_bgp_asn and golden_bgp_asn and running_bgp_asn != golden_bgp_asn:
            self._add_critical(
                report,
                f"Alteração de ASN BGP detectada: golden={sorted(golden_bgp_asn)} "
                f"running={sorted(running_bgp_asn)}.",
            )

    def _calculate_risk_scores(self, report: ConfigDiffReport) -> dict[str, int]:
        scores: dict[str, int] = {
            "security": 0,
            "availability": 0,
            "performance": 0,
        }

        for change in report.changes:
            category = change.risk_category
            if category in scores:
                scores[category] += max(0, change.risk_points)

        for finding in report.critical_findings:
            text = finding.lower()
            if "autenticação" in text or "acl permissiva" in text or "segurança" in text:
                scores["security"] += 25
            if "asn" in text or "ospf" in text or "bgp" in text:
                scores["availability"] += 25

        for category in ("security", "availability", "performance"):
            scores[category] = min(100, scores[category])

        scores["overall"] = max(scores["security"], scores["availability"], scores["performance"])
        return scores

    def _build_recommendations(self, report: ConfigDiffReport) -> list[str]:
        recs: list[str] = []
        overall = report.risk_scores.get("overall", 0)

        if not report.changes:
            return ["Sem drift relevante. Manter apenas monitoramento contínuo."]

        if overall >= 75:
            recs.append("Executar mudança apenas em janela controlada com plano de rollback testado.")
        elif overall >= 40:
            recs.append("Executar validação em laboratório/staging antes da produção.")
        else:
            recs.append("Risco baixo/moderado. Ainda assim, validar pré e pós-change.")

        if any("autenticação" in finding.lower() for finding in report.critical_findings):
            recs.append("Restaurar autenticação OSPF/BGP antes do deploy para evitar exposição e instabilidade.")

        if any("asn" in finding.lower() for finding in report.critical_findings):
            recs.append("Confirmar ASN com o peer e equipe de backbone antes de aplicar em produção.")

        if any("acl permissiva" in finding.lower() for finding in report.critical_findings):
            recs.append("Substituir regras permissivas por ACL explícita com menor privilégio.")

        recs.append("Coletar evidências antes/depois: `show run`, `show ip route`, `show logging`.")
        recs.append("Monitorar KPIs por 30-60 minutos após mudança (erros, flap, latência, perda).")
        return recs

    @staticmethod
    def _build_rollback_steps(_report: ConfigDiffReport) -> list[str]:
        return [
            "Salvar snapshot pré-change (`show run` completo e outputs críticos).",
            "Manter bloco de configuração anterior pronto para reaplicação imediata.",
            "Em caso de impacto, reverter blocos alterados em ordem: routing -> ACL -> interfaces.",
            "Revalidar serviços críticos com testes de conectividade e logs após rollback.",
        ]

    @staticmethod
    def _routing_key(proto: ParsedRoutingProtocol) -> str:
        return f"{proto.protocol}:{proto.process_id or '-'}"

    @staticmethod
    def _flatten_general_services(general: dict) -> set[str]:
        keys = ("services", "ssh", "ntp", "logging", "snmp", "spanning_tree")
        flattened: set[str] = set()
        for key in keys:
            for value in general.get(key, []):
                normalized = " ".join(str(value).strip().split())
                if normalized:
                    flattened.add(normalized)
        return flattened

    @staticmethod
    def _removed_normalized_lines(source_text: str, target_text: str) -> set[str]:
        def _normalize_lines(text: str) -> set[str]:
            lines: set[str] = set()
            for raw in text.splitlines():
                line = " ".join(raw.strip().split()).lower()
                if not line or line == "!":
                    continue
                lines.add(line)
            return lines

        return _normalize_lines(source_text) - _normalize_lines(target_text)

    @staticmethod
    def _is_acl_too_permissive(entry: str) -> bool:
        text = " ".join(entry.lower().split())
        return bool(
            re.search(r"\bpermit\s+ip\s+any\s+any\b", text)
            or re.search(r"\bpermit\s+any\s+any\b", text)
        )

    @staticmethod
    def _ip_with_mask(ip_address: str | None, subnet_mask: str | None) -> str:
        if ip_address and subnet_mask:
            return f"{ip_address} {subnet_mask}"
        if ip_address:
            return ip_address
        return "none"

    @staticmethod
    def _risk_level(score: int) -> str:
        if score >= 75:
            return "CRITICAL"
        if score >= 50:
            return "HIGH"
        if score >= 25:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _add_critical(report: ConfigDiffReport, message: str) -> None:
        if message not in report.critical_findings:
            report.critical_findings.append(message)

    @staticmethod
    def _add_change(
        report: ConfigDiffReport,
        section: str,
        item: str,
        change_type: str,
        details: str,
        risk_category: str,
        risk_points: int,
        critical: bool = False,
    ) -> None:
        report.changes.append(
            DiffChange(
                section=section,
                item=item,
                change_type=change_type,
                details=details,
                risk_category=risk_category,
                risk_points=risk_points,
                critical=critical,
            )
        )
