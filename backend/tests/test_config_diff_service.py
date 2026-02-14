"""
Tests for semantic config diff + risk analysis service.
"""
from __future__ import annotations

from app.services.config_diff_service import ConfigDiffService


def test_config_diff_detects_critical_changes_and_sections() -> None:
    """
    Must detect critical security/availability changes and render expected sections.
    """
    golden_config = """
hostname R1
!
interface GigabitEthernet0/0
 description Uplink ISP
 ip address 10.0.0.1 255.255.255.252
 ip ospf authentication message-digest
 ip ospf message-digest-key 1 md5 SECRET
!
router bgp 65001
 neighbor 10.0.0.2 remote-as 65002
 neighbor 10.0.0.2 password 7 123456
!
ip access-list extended EDGE-IN
 permit tcp any any eq 443
 deny ip any any
!
"""

    running_config = """
hostname R1
!
interface GigabitEthernet0/0
 description Uplink ISP
 ip address 10.0.0.1 255.255.255.252
!
router bgp 65100
 neighbor 10.0.0.2 remote-as 65002
!
ip access-list extended EDGE-IN
 permit ip any any
 deny ip any any
!
"""

    svc = ConfigDiffService()
    report = svc.compare_configs(
        running_config=running_config,
        golden_config=golden_config,
    )
    rendered = svc.format_report(report)

    critical_text = " ".join(report.critical_findings).lower()
    assert "autenticação" in critical_text
    assert "asn bgp" in critical_text
    assert "acl permissiva" in critical_text
    assert report.risk_scores["security"] >= 60
    assert report.risk_scores["availability"] >= 40

    assert "## Mudanças detectadas" in rendered
    assert "## Riscos" in rendered
    assert "## Ações recomendadas" in rendered
    assert "### Rollback sugerido" in rendered


def test_config_diff_ignores_cosmetic_only_changes() -> None:
    """
    Description-only changes should not raise critical findings (false positive guard).
    """
    golden_config = """
hostname SW1
!
interface GigabitEthernet0/1
 description Link para core antigo
 switchport access vlan 10
!
"""

    running_config = """
hostname SW1
!
interface GigabitEthernet0/1
 description Link para core novo
 switchport access vlan 10
!
"""

    svc = ConfigDiffService()
    report = svc.compare_configs(
        running_config=running_config,
        golden_config=golden_config,
    )
    rendered = svc.format_report(report)

    assert report.critical_findings == []
    assert report.risk_scores["overall"] < 25
    assert "Nenhuma mudança semântica detectada" in rendered
