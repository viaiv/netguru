"""
PreChangeReviewService — validacao preventiva antes de executar change de rede.

Entrega:
- matriz de impacto por dominio (routing, security, convergence, observability)
- pre-check e post-check operacionais
- decisao assistida (go / no-go / go with mitigation)
- playbook pos-change automatico
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.config_diff_service import ConfigDiffService


@dataclass(frozen=True)
class DomainAssessment:
    """Avaliacoes de risco por dominio tecnico."""

    domain: str
    score: int
    impact: str
    rationale: tuple[str, ...]


@dataclass
class PreChangeReviewReport:
    """Resultado completo de pre-change review."""

    proposal: str
    domain_assessments: list[DomainAssessment] = field(default_factory=list)
    overall_score: int = 0
    decision: str = "go"
    explicit_alert: str | None = None
    recommendations: list[str] = field(default_factory=list)
    pre_checks: list[str] = field(default_factory=list)
    post_checks: list[str] = field(default_factory=list)
    post_change_playbook: dict[str, list[str]] = field(default_factory=dict)


class PreChangeReviewService:
    """Servico heuristico para avaliar impacto de changes de rede."""

    _PATTERN_RULES: dict[str, list[tuple[re.Pattern[str], int, str]]] = {
        "routing": [
            (re.compile(r"\brouter\s+bgp\b", re.IGNORECASE), 24, "Alteracao de processo BGP."),
            (re.compile(r"\bremote-as\b", re.IGNORECASE), 20, "Mudanca de vizinhanca/AS no BGP."),
            (re.compile(r"\brouter\s+ospf\b", re.IGNORECASE), 18, "Alteracao no dominio OSPF."),
            (re.compile(r"\bip\s+route\s+0\.0\.0\.0\b", re.IGNORECASE), 16, "Mudanca em default route."),
            (re.compile(r"\bmaximum-paths\b", re.IGNORECASE), 12, "Alteracao de ECMP/forwarding."),
        ],
        "security": [
            (re.compile(r"\bpermit\s+ip\s+any\s+any\b", re.IGNORECASE), 45, "ACL altamente permissiva."),
            (re.compile(r"\bpermit\s+any\s+any\b", re.IGNORECASE), 40, "ACL altamente permissiva."),
            (re.compile(r"\bno\s+ip\s+ssh\b", re.IGNORECASE), 26, "Possivel desativacao de acesso seguro."),
            (
                re.compile(r"\b(no\s+)?ip\s+ospf\s+authentication\b", re.IGNORECASE),
                22,
                "Mudanca em autenticacao OSPF.",
            ),
            (
                re.compile(r"\bneighbor\s+\S+\s+password\b", re.IGNORECASE),
                18,
                "Mudanca de autenticacao de peer BGP.",
            ),
            (re.compile(r"\bsnmp-server\s+community\s+public\b", re.IGNORECASE), 20, "SNMP community fraca."),
        ],
        "convergence": [
            (re.compile(r"\bshutdown\b", re.IGNORECASE), 20, "Possivel indisponibilidade por shutdown."),
            (
                re.compile(r"\bspanning-tree\s+mode\b", re.IGNORECASE),
                16,
                "Alteracao de modo STP impacta convergencia L2.",
            ),
            (re.compile(r"\bbfd\b", re.IGNORECASE), 12, "Alteracao em mecanismos de deteccao rapida."),
            (re.compile(r"\bmtu\b", re.IGNORECASE), 14, "Mudanca de MTU pode causar blackhole/intermitencia."),
            (re.compile(r"\bhello-interval\b|\bdead-interval\b", re.IGNORECASE), 14, "Mudanca de timers."),
        ],
        "observability": [
            (re.compile(r"\bno\s+logging\b", re.IGNORECASE), 20, "Reducao de observabilidade de logs."),
            (
                re.compile(r"\bno\s+snmp-server\b", re.IGNORECASE),
                18,
                "Reducao de visibilidade de monitoramento SNMP.",
            ),
            (re.compile(r"\bno\s+ntp\b", re.IGNORECASE), 14, "Perda de sincronismo temporal para troubleshooting."),
            (re.compile(r"\bip\s+sla\b", re.IGNORECASE), 10, "Mudanca em probes de monitoramento ativo."),
        ],
    }

    def review_change(
        self,
        change_proposal: str,
        running_config: str | None = None,
        golden_config: str | None = None,
    ) -> PreChangeReviewReport:
        """
        Avalia proposta de change e retorna relatorio de impacto.

        Args:
            change_proposal: Texto livre com proposta/trecho de config/comando.
            running_config: Config atual (opcional) para enriquecer avaliacao.
            golden_config: Config baseline (opcional) para enriquecer avaliacao.
        """
        text = change_proposal or ""
        domain_scores: dict[str, int] = {
            "routing": 8,
            "security": 8,
            "convergence": 8,
            "observability": 8,
        }
        rationales: dict[str, list[str]] = {k: [] for k in domain_scores}

        for domain, rules in self._PATTERN_RULES.items():
            for pattern, points, rationale in rules:
                if pattern.search(text):
                    domain_scores[domain] += points
                    rationales[domain].append(rationale)

        explicit_alert: str | None = None
        if running_config and golden_config:
            diff_svc = ConfigDiffService()
            diff_report = diff_svc.compare_configs(
                running_config=running_config,
                golden_config=golden_config,
            )
            domain_scores["security"] += int(diff_report.risk_scores.get("security", 0) * 0.45)
            availability_score = int(diff_report.risk_scores.get("availability", 0) * 0.45)
            domain_scores["routing"] += availability_score
            domain_scores["convergence"] += int(availability_score * 0.6)
            domain_scores["observability"] += int(
                diff_report.risk_scores.get("performance", 0) * 0.25
            )

            if diff_report.critical_findings:
                explicit_alert = (
                    "ALERTA DE ALTO RISCO: diff de configuracao reportou mudancas criticas "
                    "com potencial de impacto operacional imediato."
                )
                for finding in diff_report.critical_findings[:3]:
                    rationales["security"].append(f"Critico no diff: {finding}")

        # Clamp scores and build assessments
        assessments: list[DomainAssessment] = []
        for domain, score in domain_scores.items():
            safe_score = min(100, max(0, score))
            domain_scores[domain] = safe_score
            assessments.append(
                DomainAssessment(
                    domain=domain,
                    score=safe_score,
                    impact=self._impact_level(safe_score),
                    rationale=tuple(rationales[domain] or ("Nenhum sinal critico identificado.",)),
                )
            )

        overall = max(domain_scores.values()) if domain_scores else 0
        high_risk_domains = [d for d, s in domain_scores.items() if s >= 70]

        if high_risk_domains:
            decision = "no-go"
            if explicit_alert is None:
                explicit_alert = (
                    "ALERTA DE ALTO RISCO: dominios com impacto elevado detectados "
                    f"({', '.join(high_risk_domains)})."
                )
        elif overall >= 40:
            decision = "go with mitigation"
        else:
            decision = "go"

        report = PreChangeReviewReport(
            proposal=change_proposal.strip(),
            domain_assessments=sorted(assessments, key=lambda a: a.score, reverse=True),
            overall_score=overall,
            decision=decision,
            explicit_alert=explicit_alert,
        )
        report.pre_checks = self._build_pre_checks(report.domain_assessments)
        report.post_checks = self._build_post_checks(report.domain_assessments)
        report.recommendations = self._build_recommendations(report)
        report.post_change_playbook = self._build_post_change_playbook(report.domain_assessments)
        return report

    def format_report(self, report: PreChangeReviewReport) -> str:
        """
        Formata relatorio em markdown para uso no chat/export.
        """
        lines: list[str] = [
            "# Pre-Change Review",
            "",
            "## Proposta de change",
            f"```",
            report.proposal or "(vazio)",
            "```",
            "",
            "## Matriz de impacto",
            "| Dominio | Impacto | Score |",
            "| --- | --- | --- |",
        ]
        for item in report.domain_assessments:
            lines.append(
                f"| {item.domain} | {item.impact} | {item.score}/100 |"
            )

        lines.extend(
            [
                "",
                "## Decisao assistida",
                f"- Decisao: **{report.decision.upper()}**",
                f"- Score geral: **{report.overall_score}/100**",
            ]
        )
        if report.explicit_alert:
            lines.append(f"- {report.explicit_alert}")

        lines.append("")
        lines.append("## Racional de impacto")
        for item in report.domain_assessments:
            lines.append(f"### {item.domain.upper()}")
            for rationale in item.rationale:
                lines.append(f"- {rationale}")

        lines.append("")
        lines.append("## Pre-check operacional")
        for step in report.pre_checks:
            lines.append(f"- {step}")

        lines.append("")
        lines.append("## Pos-check operacional")
        for step in report.post_checks:
            lines.append(f"- {step}")

        lines.append("")
        lines.append("## Recomendacoes objetivas")
        for rec in report.recommendations:
            lines.append(f"- {rec}")

        lines.append("")
        lines.append("## Playbook pos-change")
        for phase, checks in report.post_change_playbook.items():
            lines.append(f"### {phase}")
            for check in checks:
                lines.append(f"- {check}")

        return "\n".join(lines)

    @staticmethod
    def _impact_level(score: int) -> str:
        if score >= 70:
            return "high"
        if score >= 40:
            return "medium"
        return "low"

    @staticmethod
    def _build_pre_checks(assessments: list[DomainAssessment]) -> list[str]:
        checks = [
            "Confirmar janela de manutencao aprovada e plano de rollback validado.",
            "Coletar baseline pre-change: show run, show logging, show interface status.",
        ]
        domains = {item.domain for item in assessments if item.score >= 40}
        if "routing" in domains:
            checks.append("Validar tabela de rotas e estado de neighbors antes da mudanca.")
        if "security" in domains:
            checks.append("Revisar ACL/politicas para evitar bloqueio ou exposicao indevida.")
        if "convergence" in domains:
            checks.append("Confirmar estabilidade de STP/OSPF/BGP para evitar flap durante change.")
        if "observability" in domains:
            checks.append("Garantir syslog/SNMP/NTP operacionais para observacao imediata.")
        return checks

    @staticmethod
    def _build_post_checks(assessments: list[DomainAssessment]) -> list[str]:
        checks = [
            "Executar smoke tests de conectividade (ping/traceroute) para servicos criticos.",
            "Verificar erros e alarms novos em logs apos a aplicacao.",
        ]
        domains = {item.domain for item in assessments if item.score >= 40}
        if "routing" in domains:
            checks.append("Checar convergencia de rotas e estabilidade de neighbors (OSPF/BGP).")
        if "security" in domains:
            checks.append("Validar trafego autorizado e bloqueios esperados nas ACLs.")
        if "convergence" in domains:
            checks.append("Monitorar flapping de interface/STP e perda de pacotes.")
        if "observability" in domains:
            checks.append("Confirmar ingestao de telemetry/logs no observability stack.")
        return checks

    @staticmethod
    def _build_recommendations(report: PreChangeReviewReport) -> list[str]:
        recs: list[str] = []
        if report.decision == "no-go":
            recs.append("Nao executar em producao sem mitigacoes e validacao em laboratorio.")
        elif report.decision == "go with mitigation":
            recs.append("Executar apenas com mitigacoes ativas e criterio claro de rollback.")
        else:
            recs.append("Risco controlado: executar com monitoramento padrao e checkpoints.")

        high_domains = [d.domain for d in report.domain_assessments if d.score >= 70]
        if high_domains:
            recs.append(
                "Priorizar mitigacoes nos dominios de alto risco: "
                + ", ".join(high_domains)
                + "."
            )

        recs.append("Documentar evidencias pre e pos-change para auditoria e aprendizado.")
        recs.append("Definir owner e tempo maximo para rollback (RTO operacional).")
        return recs

    @staticmethod
    def _build_post_change_playbook(
        assessments: list[DomainAssessment],
    ) -> dict[str, list[str]]:
        domains = {item.domain for item in assessments if item.score >= 40}
        playbook: dict[str, list[str]] = {
            "T0-T5 (imediato)": [
                "Aplicar change com captura de logs em tempo real.",
                "Validar disponibilidade dos servicos criticos em ate 5 minutos.",
            ],
            "T5-T30 (estabilizacao)": [
                "Comparar KPIs de latencia/perda com baseline pre-change.",
                "Confirmar ausencia de alarmes novos recorrentes.",
            ],
            "T30-T60 (confirmacao)": [
                "Executar checklist final de saude e registrar resultados.",
                "Encerrar janela apenas com aceite operacional do owner.",
            ],
        }
        if "routing" in domains:
            playbook["T5-T30 (estabilizacao)"].append(
                "Validar estabilidade de adjacencias e tabela de rotas completa."
            )
        if "security" in domains:
            playbook["T5-T30 (estabilizacao)"].append(
                "Executar testes de allow/deny em fluxos sensiveis."
            )
        if "observability" in domains:
            playbook["T30-T60 (confirmacao)"].append(
                "Confirmar continuidade de logs e metricas no SIEM/NMS."
            )
        return playbook
