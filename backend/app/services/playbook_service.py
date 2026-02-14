"""
PlaybookService — guided troubleshooting playbooks with per-conversation state.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.core.config import settings
from app.core.redis import get_redis_client


@dataclass(frozen=True)
class PlaybookStep:
    """One guided step in a troubleshooting playbook."""

    stage: str
    objective: str
    show_commands: tuple[str, ...]
    success_criteria: tuple[str, ...]


@dataclass(frozen=True)
class PlaybookDefinition:
    """Static playbook definition."""

    playbook_id: str
    title: str
    keywords: tuple[str, ...]
    probable_causes: tuple[str, ...]
    validation_checklist: tuple[str, ...]
    steps: tuple[PlaybookStep, ...]


@dataclass
class PlaybookState:
    """Runtime state persisted in Redis per conversation."""

    playbook_id: str
    current_step: int
    status: str
    started_at: str
    updated_at: str


@dataclass(frozen=True)
class PlaybookResponse:
    """Rendered playbook response for ChatService."""

    content: str
    metadata: dict


PLAYBOOKS: dict[str, PlaybookDefinition] = {
    "ospf": PlaybookDefinition(
        playbook_id="ospf",
        title="OSPF Adjacency Troubleshooting",
        keywords=("ospf", "adjacency", "adjacencia", "vizinhan"),
        probable_causes=(
            "Area mismatch entre vizinhos",
            "Autenticação OSPF inconsistente",
            "Hello/Dead timers diferentes",
            "MTU mismatch na interface",
        ),
        validation_checklist=(
            "Todos os neighbors em FULL",
            "Rotas OSPF esperadas na RIB",
            "Sem logs recorrentes de flapping",
        ),
        steps=(
            PlaybookStep(
                stage="coletar",
                objective="Confirmar estado atual de vizinhança e interfaces OSPF.",
                show_commands=(
                    "show ip ospf neighbor",
                    "show ip ospf interface brief",
                    "show ip route ospf",
                ),
                success_criteria=(
                    "Neighbors esperados aparecem no output",
                    "Estado de vizinhos estável (idealmente FULL)",
                ),
            ),
            PlaybookStep(
                stage="analisar",
                objective="Verificar parâmetros que bloqueiam formação de adjacência.",
                show_commands=(
                    "show run | section router ospf",
                    "show ip ospf interface <interface>",
                ),
                success_criteria=(
                    "Area, timers e network type consistentes entre peers",
                    "Config de autenticação alinhada nos dois lados",
                ),
            ),
            PlaybookStep(
                stage="recomendar",
                objective="Aplicar correção mínima para estabilizar adjacência.",
                show_commands=(
                    "show logging | include OSPF",
                    "show ip ospf database",
                ),
                success_criteria=(
                    "Hipótese de causa raiz definida",
                    "Plano de correção e rollback definidos",
                ),
            ),
            PlaybookStep(
                stage="validar",
                objective="Validar convergência e ausência de regressão.",
                show_commands=(
                    "show ip ospf neighbor",
                    "show ip route ospf",
                    "ping <prefixo-remoto>",
                ),
                success_criteria=(
                    "Neighbors permanecem FULL",
                    "Conectividade restaurada e estável",
                ),
            ),
        ),
    ),
    "bgp": PlaybookDefinition(
        playbook_id="bgp",
        title="BGP Flapping Troubleshooting",
        keywords=("bgp", "flap", "flapping", "peer", "neighbor"),
        probable_causes=(
            "Instabilidade de link subjacente",
            "Keepalive/Hold timers agressivos",
            "Ausência de autenticação ou política inconsistente",
            "Reinicializações por CPU/memória ou process reset",
        ),
        validation_checklist=(
            "Sessões BGP Established de forma contínua",
            "Contadores de flap estabilizados",
            "Prefixos esperados anunciados/recebidos",
        ),
        steps=(
            PlaybookStep(
                stage="coletar",
                objective="Mapear peers afetados e frequência do flap.",
                show_commands=(
                    "show ip bgp summary",
                    "show logging | include BGP",
                    "show interfaces | include line protocol|input errors|CRC",
                ),
                success_criteria=(
                    "Peers em flap identificados",
                    "Janela temporal e padrão do flap observados",
                ),
            ),
            PlaybookStep(
                stage="analisar",
                objective="Checar políticas, timers e autenticação por neighbor.",
                show_commands=(
                    "show run | section router bgp",
                    "show ip bgp neighbors <neighbor-ip>",
                ),
                success_criteria=(
                    "Timers e políticas coerentes com o peer remoto",
                    "Erro de FSM ou reset reason identificado",
                ),
            ),
            PlaybookStep(
                stage="recomendar",
                objective="Definir mitigação de curto prazo e correção definitiva.",
                show_commands=(
                    "show processes cpu | include BGP",
                    "show memory statistics",
                ),
                success_criteria=(
                    "Plano de ação com risco baixo definido",
                    "Critério de rollback registrado",
                ),
            ),
            PlaybookStep(
                stage="validar",
                objective="Confirmar estabilidade pós-ação.",
                show_commands=(
                    "show ip bgp summary",
                    "show ip bgp neighbors <neighbor-ip> | include Last reset|Established",
                ),
                success_criteria=(
                    "Peer(s) em Established sem resets recorrentes",
                    "Rotas e tráfego normalizados",
                ),
            ),
        ),
    ),
    "stp_vlan": PlaybookDefinition(
        playbook_id="stp_vlan",
        title="STP/VLAN Loop & Reachability Troubleshooting",
        keywords=("stp", "spanning-tree", "vlan", "loop", "broadcast storm"),
        probable_causes=(
            "Root bridge inesperada para VLAN crítica",
            "Porta trunk com VLANs faltando/excedentes",
            "Portfast/BPDU guard mal aplicado",
            "Loop físico sem proteção STP efetiva",
        ),
        validation_checklist=(
            "Root bridge correta por VLAN",
            "Portas em estado esperado (forwarding/blocking)",
            "Sem crescimento anômalo de broadcast/multicast",
        ),
        steps=(
            PlaybookStep(
                stage="coletar",
                objective="Capturar topologia STP e estado das VLANs afetadas.",
                show_commands=(
                    "show spanning-tree summary",
                    "show spanning-tree vlan <vlan-id>",
                    "show vlan brief",
                ),
                success_criteria=(
                    "VLAN(s) afetadas identificadas",
                    "Portas com transição frequente identificadas",
                ),
            ),
            PlaybookStep(
                stage="analisar",
                objective="Correlacionar STP, trunks e inconsistências de VLAN.",
                show_commands=(
                    "show interfaces trunk",
                    "show run interface <interface>",
                    "show logging | include STP|SPANTREE",
                ),
                success_criteria=(
                    "Root e custos STP coerentes",
                    "Allowed VLANs e mode de trunk corretos",
                ),
            ),
            PlaybookStep(
                stage="recomendar",
                objective="Definir ajuste de STP/VLAN com menor impacto.",
                show_commands=(
                    "show mac address-table dynamic vlan <vlan-id>",
                    "show interfaces counters errors",
                ),
                success_criteria=(
                    "Mudança proposta minimiza risco de loop",
                    "Plano de rollback pronto",
                ),
            ),
            PlaybookStep(
                stage="validar",
                objective="Validar convergência e estabilidade de camada 2.",
                show_commands=(
                    "show spanning-tree vlan <vlan-id>",
                    "show interfaces trunk",
                    "ping <gateway-vlan>",
                ),
                success_criteria=(
                    "Sem eventos de topology change inesperados",
                    "Conectividade L2/L3 restaurada",
                ),
            ),
        ),
    ),
    "wan_loss": PlaybookDefinition(
        playbook_id="wan_loss",
        title="WAN Packet-Loss/Latency Troubleshooting",
        keywords=("wan", "latency", "latencia", "packet loss", "perda de pacotes", "jitter"),
        probable_causes=(
            "Congestionamento no enlace WAN",
            "Erros físicos (CRC/drops) na interface",
            "QoS/policing excessivo",
            "Rota subótima ou assimétrica",
        ),
        validation_checklist=(
            "Perda de pacotes abaixo do limiar alvo",
            "Latência e jitter dentro do esperado",
            "Erros de interface estabilizados",
        ),
        steps=(
            PlaybookStep(
                stage="coletar",
                objective="Medir perda/latência e estado físico da WAN.",
                show_commands=(
                    "ping <destino> repeat 50",
                    "traceroute <destino>",
                    "show interfaces <wan-interface>",
                ),
                success_criteria=(
                    "Baseline de perda e latência registrado",
                    "Erros físicos (input/CRC/drops) identificados",
                ),
            ),
            PlaybookStep(
                stage="analisar",
                objective="Avaliar impacto de fila/QoS e saturação.",
                show_commands=(
                    "show policy-map interface <wan-interface>",
                    "show interfaces <wan-interface> | include rate",
                ),
                success_criteria=(
                    "Ponto de saturação identificado",
                    "Hipótese principal de causa definida",
                ),
            ),
            PlaybookStep(
                stage="recomendar",
                objective="Definir ajuste de QoS/roteamento ou escalonamento com ISP.",
                show_commands=(
                    "show ip route <destino>",
                    "show logging | include LINEPROTO|DUAL|BFD|SLA",
                ),
                success_criteria=(
                    "Plano de mitigação acordado",
                    "Critério de sucesso mensurável definido",
                ),
            ),
            PlaybookStep(
                stage="validar",
                objective="Confirmar melhoria sustentada após mitigação.",
                show_commands=(
                    "ping <destino> repeat 50",
                    "show interfaces <wan-interface>",
                    "show policy-map interface <wan-interface>",
                ),
                success_criteria=(
                    "KPIs de WAN melhoraram e se mantiveram estáveis",
                    "Sem regressão em tráfego crítico",
                ),
            ),
        ),
    ),
    "dns": PlaybookDefinition(
        playbook_id="dns",
        title="DNS Resolution Troubleshooting",
        keywords=("dns", "resolver", "resolucao", "resolution", "nxdomain", "name server"),
        probable_causes=(
            "Servidor DNS indisponível ou não alcançável",
            "Timeout por ACL/firewall",
            "Registros incorretos/ausentes",
            "Alto volume de NXDOMAIN por consulta inválida",
        ),
        validation_checklist=(
            "Consultas A/AAAA respondendo com latência aceitável",
            "Sem crescimento anômalo de NXDOMAIN",
            "Aplicações críticas resolvendo nomes esperados",
        ),
        steps=(
            PlaybookStep(
                stage="coletar",
                objective="Coletar sintomas de falha de resolução e alcance ao DNS.",
                show_commands=(
                    "show hosts",
                    "ping <dns-server-ip>",
                    "show ip dns view",
                ),
                success_criteria=(
                    "Servidor(es) DNS alvo identificados",
                    "Conectividade ao DNS confirmada ou descartada",
                ),
            ),
            PlaybookStep(
                stage="analisar",
                objective="Verificar configuração e comportamento de consultas.",
                show_commands=(
                    "show run | include ip name-server|ip domain",
                    "show logging | include DNS|NXDOMAIN",
                ),
                success_criteria=(
                    "Config DNS válida confirmada",
                    "Erro dominante de resolução identificado",
                ),
            ),
            PlaybookStep(
                stage="recomendar",
                objective="Definir correção de configuração, rede ou registro.",
                show_commands=(
                    "show access-lists",
                    "show ip route <dns-server-ip>",
                ),
                success_criteria=(
                    "Ação corretiva priorizada com rollback definido",
                    "Plano de reteste documentado",
                ),
            ),
            PlaybookStep(
                stage="validar",
                objective="Validar resolução de nomes e estabilidade pós-correção.",
                show_commands=(
                    "ping <hostname>",
                    "show hosts",
                    "show logging | include DNS|NXDOMAIN",
                ),
                success_criteria=(
                    "Resolução normalizada para nomes críticos",
                    "Sem novos erros relevantes em logs",
                ),
            ),
        ),
    ),
}


class PlaybookService:
    """Stateful playbook engine with Redis-backed per-conversation context."""

    def __init__(self, redis_client=None) -> None:  # noqa: ANN001
        self._redis = redis_client

    async def handle_message(
        self,
        conversation_id: UUID,
        content: str,
    ) -> PlaybookResponse | None:
        """
        Try to handle the message as a playbook action.

        Returns:
            PlaybookResponse when message is handled by playbook engine, else None.
        """
        normalized = " ".join(content.lower().split())

        # Start (natural language) has highest priority.
        detected = self._detect_playbook_to_start(normalized)
        if detected:
            return await self._start_playbook(conversation_id, detected)

        # Avoid Redis access for regular chat messages that are not playbook actions.
        is_control_command = any(
            (
                self._is_stop_command(normalized),
                self._is_status_command(normalized),
                self._is_pause_command(normalized),
                self._is_resume_command(normalized),
                self._is_next_command(normalized),
            ),
        )
        if not is_control_command:
            return None

        # Control commands only if there is active/paused state.
        state = await self._get_state(conversation_id)
        if state is None:
            return None

        if self._is_stop_command(normalized):
            await self._delete_state(conversation_id)
            pb = PLAYBOOKS[state.playbook_id]
            return PlaybookResponse(
                content=(
                    f"## Playbook interrompido: {pb.title}\n\n"
                    "Fluxo encerrado nesta conversa. Para reiniciar, diga algo como "
                    "`me guia no troubleshooting de OSPF`."
                ),
                metadata={"playbook_id": state.playbook_id, "action": "stopped"},
            )

        if self._is_status_command(normalized):
            return self._build_status_response(state)

        if self._is_pause_command(normalized):
            if state.status == "paused":
                return PlaybookResponse(
                    content="Playbook já está pausado. Use `retomar playbook` para continuar.",
                    metadata={"playbook_id": state.playbook_id, "action": "already_paused"},
                )
            state.status = "paused"
            state.updated_at = datetime.now(UTC).isoformat()
            await self._save_state(conversation_id, state)
            return PlaybookResponse(
                content=(
                    "Playbook pausado com sucesso.\n\n"
                    "Quando quiser continuar, use `retomar playbook`."
                ),
                metadata={"playbook_id": state.playbook_id, "action": "paused"},
            )

        if self._is_resume_command(normalized):
            if state.status != "paused":
                return PlaybookResponse(
                    content="Playbook já está ativo. Use `proximo` para avançar de etapa.",
                    metadata={"playbook_id": state.playbook_id, "action": "already_active"},
                )
            state.status = "active"
            state.updated_at = datetime.now(UTC).isoformat()
            await self._save_state(conversation_id, state)
            return PlaybookResponse(
                content=self._render_step(PLAYBOOKS[state.playbook_id], state.current_step),
                metadata={
                    "playbook_id": state.playbook_id,
                    "action": "resumed",
                    "current_step": state.current_step,
                },
            )

        if self._is_next_command(normalized):
            if state.status == "paused":
                return PlaybookResponse(
                    content=(
                        "Playbook está pausado. Use `retomar playbook` antes de avançar."
                    ),
                    metadata={"playbook_id": state.playbook_id, "action": "next_while_paused"},
                )
            return await self._advance_playbook(conversation_id, state)

        return None

    async def _start_playbook(
        self,
        conversation_id: UUID,
        playbook_id: str,
    ) -> PlaybookResponse:
        now = datetime.now(UTC).isoformat()
        state = PlaybookState(
            playbook_id=playbook_id,
            current_step=0,
            status="active",
            started_at=now,
            updated_at=now,
        )
        await self._save_state(conversation_id, state)

        pb = PLAYBOOKS[playbook_id]
        intro = (
            f"## Playbook iniciado: {pb.title}\n\n"
            "Fluxo guiado por etapas: `coletar -> analisar -> recomendar -> validar`.\n"
            "Envie os outputs dos comandos e use `proximo` para avançar.\n\n"
        )
        return PlaybookResponse(
            content=intro + self._render_step(pb, 0),
            metadata={"playbook_id": playbook_id, "action": "started", "current_step": 0},
        )

    async def _advance_playbook(
        self,
        conversation_id: UUID,
        state: PlaybookState,
    ) -> PlaybookResponse:
        pb = PLAYBOOKS[state.playbook_id]
        next_step = state.current_step + 1
        if next_step >= len(pb.steps):
            await self._delete_state(conversation_id)
            return PlaybookResponse(
                content=self._render_completion(pb),
                metadata={"playbook_id": state.playbook_id, "action": "completed"},
            )

        state.current_step = next_step
        state.updated_at = datetime.now(UTC).isoformat()
        await self._save_state(conversation_id, state)
        return PlaybookResponse(
            content=self._render_step(pb, next_step),
            metadata={
                "playbook_id": state.playbook_id,
                "action": "advanced",
                "current_step": next_step,
            },
        )

    async def _get_state(self, conversation_id: UUID) -> PlaybookState | None:
        raw = await self._redis_client().get(self._state_key(conversation_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return PlaybookState(
                playbook_id=str(data["playbook_id"]),
                current_step=int(data["current_step"]),
                status=str(data["status"]),
                started_at=str(data["started_at"]),
                updated_at=str(data["updated_at"]),
            )
        except Exception:
            await self._delete_state(conversation_id)
            return None

    async def _save_state(self, conversation_id: UUID, state: PlaybookState) -> None:
        await self._redis_client().setex(
            self._state_key(conversation_id),
            settings.PLAYBOOK_STATE_TTL_SECONDS,
            json.dumps(asdict(state)),
        )

    async def _delete_state(self, conversation_id: UUID) -> None:
        await self._redis_client().delete(self._state_key(conversation_id))

    def _state_key(self, conversation_id: UUID) -> str:
        return f"chat:playbook:{conversation_id}"

    def _redis_client(self):  # noqa: ANN202
        return self._redis or get_redis_client()

    @staticmethod
    def _is_status_command(text: str) -> bool:
        return "status playbook" in text or text.strip() == "playbook status"

    @staticmethod
    def _is_pause_command(text: str) -> bool:
        return any(k in text for k in ("pausar playbook", "pause playbook", "pause"))

    @staticmethod
    def _is_resume_command(text: str) -> bool:
        return any(
            k in text
            for k in ("retomar playbook", "resume playbook", "resume", "retomar")
        )

    @staticmethod
    def _is_stop_command(text: str) -> bool:
        return any(
            k in text
            for k in ("encerrar playbook", "cancelar playbook", "stop playbook", "stop")
        )

    @staticmethod
    def _is_next_command(text: str) -> bool:
        return text.strip() in {
            "proximo",
            "próximo",
            "next",
            "avancar",
            "avançar",
            "seguir",
            "continuar",
        }

    def _detect_playbook_to_start(self, text: str) -> str | None:
        has_intent = any(
            keyword in text
            for keyword in (
                "playbook",
                "troubleshoot",
                "troubleshooting",
                "diagnost",
                "debug",
                "me guia",
                "guia",
                "investigar",
                "resolver",
            )
        )
        if not has_intent:
            return None

        for pb in PLAYBOOKS.values():
            if any(keyword in text for keyword in pb.keywords):
                return pb.playbook_id
        return None

    def _build_status_response(self, state: PlaybookState) -> PlaybookResponse:
        pb = PLAYBOOKS[state.playbook_id]
        step_idx = max(0, min(state.current_step, len(pb.steps) - 1))
        step = pb.steps[step_idx]
        return PlaybookResponse(
            content=(
                f"## Status do Playbook: {pb.title}\n\n"
                f"- Status: **{state.status}**\n"
                f"- Etapa atual: **{step_idx + 1}/{len(pb.steps)} ({step.stage})**\n"
                f"- Iniciado em: `{state.started_at}`\n"
                f"- Última atualização: `{state.updated_at}`\n\n"
                "Use `proximo`, `pausar playbook` ou `encerrar playbook`."
            ),
            metadata={
                "playbook_id": state.playbook_id,
                "action": "status",
                "current_step": step_idx,
                "status": state.status,
            },
        )

    @staticmethod
    def _render_step(playbook: PlaybookDefinition, step_index: int) -> str:
        step = playbook.steps[step_index]
        parts: list[str] = [
            f"### Etapa {step_index + 1}/{len(playbook.steps)} — {step.stage.upper()}",
            "",
            f"**Objetivo:** {step.objective}",
            "",
            "**Comandos sugeridos:**",
        ]
        for cmd in step.show_commands:
            parts.append(f"- `{cmd}`")
        parts.append("")
        parts.append("**Critério de sucesso:**")
        for criterion in step.success_criteria:
            parts.append(f"- {criterion}")
        parts.append("")
        parts.append("Quando concluir a etapa, envie os outputs e digite `proximo`.")
        return "\n".join(parts)

    @staticmethod
    def _render_completion(playbook: PlaybookDefinition) -> str:
        parts: list[str] = [
            f"## Playbook concluído: {playbook.title}",
            "",
            "**Causa provável (hipóteses):**",
        ]
        for cause in playbook.probable_causes:
            parts.append(f"- {cause}")

        parts.append("")
        parts.append("**Checklist de validação final:**")
        for item in playbook.validation_checklist:
            parts.append(f"- {item}")

        parts.append("")
        parts.append("Se quiser, posso iniciar outro playbook nesta conversa.")
        return "\n".join(parts)
