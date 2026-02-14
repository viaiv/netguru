"""
Tests for pre-change review service.
"""
from __future__ import annotations

from app.services.pre_change_review_service import PreChangeReviewService


def test_pre_change_review_low_risk_returns_go() -> None:
    """
    Low-impact proposal should produce GO with low/medium matrix.
    """
    svc = PreChangeReviewService()
    report = svc.review_change(
        change_proposal=(
            "Adicionar descricao na interface Gi0/1 e ajustar logging buffered para 16384."
        ),
    )
    rendered = svc.format_report(report)

    assert report.decision == "go"
    assert report.overall_score < 40
    assert report.explicit_alert is None
    assert "## Matriz de impacto" in rendered
    assert "## Decisao assistida" in rendered
    assert "## Playbook pos-change" in rendered


def test_pre_change_review_high_risk_returns_no_go_with_alert() -> None:
    """
    High-risk proposal must raise explicit alert and NO-GO decision.
    """
    svc = PreChangeReviewService()
    report = svc.review_change(
        change_proposal="""
router bgp 65100
 neighbor 10.0.0.2 remote-as 65002
 no ip ospf authentication
 ip access-list extended EDGE-IN
  permit ip any any
""",
    )
    rendered = svc.format_report(report)

    assert report.decision == "no-go"
    assert report.explicit_alert is not None
    assert "ALERTA DE ALTO RISCO" in report.explicit_alert
    assert report.overall_score >= 70
    assert "NO-GO" in rendered
    assert "Recomendacoes objetivas" in rendered
