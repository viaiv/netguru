# NetGuru - Roadmap Funcional (2 Sprints)

**Versao:** 1.0  
**Atualizado em:** 14 de fevereiro de 2026  
**Escopo:** Consolidacao das issues funcionais do roadmap com priorizacao por impacto x esforco e dependencias explicitas.

---

## Objetivo

Consolidar um plano de entrega em 2 sprints para:
- estabilizar o fluxo critico de chat agentic (WebSocket + tools),
- acelerar funcionalidades de maior valor para NOC/Network Engineers,
- reduzir risco operacional com governanca e observabilidade.

---

## Priorizacao (Impacto x Esforco)

| Grupo | Impacto | Esforco | Itens |
|------|------|------|------|
| Fundacao de confiabilidade | Alto | Medio | #5, #6, #7, #8 |
| Valor imediato de operacao | Alto | Medio | #11, #12, #13, #14, #17, #20 |
| Inteligencia e escala | Medio-Alto | Medio | #15, #16, #18, #19 |
| Alinhamento tecnico | Medio | Baixo-Medio | #9, #10 |

---

## Dependencias Principais

| Dependencia | Itens dependentes | Motivo |
|------|------|------|
| #5, #6 | Todo fluxo de chat/WS | Sem contrato consistente de cancelamento e stream_end, qualquer melhoria funcional fica instavel. |
| #7 | #20, observabilidade de tools | Correlacao por ID e pre-requisito para evidencias confiaveis. |
| #8 | #11, #12, #13, #14, #15, #16, #17, #18, #19, #20 | Cobertura de testes protege evolucao sem regressao. |
| #9 | #14 e operacao de PCAP | Timeout coerente evita comportamento divergente entre doc e runtime. |
| #10 | Persistencia/auditoria/memorias | Timestamps timezone-aware reduzem ambiguidades e erros de ordenacao. |

---

## Sprint 1 (Confiabilidade + Valor Imediato)

### Fundacao obrigatoria
- [x] #5 Corrigir consistencia transacional no cancelamento de chat via WebSocket
- [x] #6 Alinhar contrato WS de `stream_end` no cenario de cancelamento
- [x] #7 Correlacionar `tool_call_start/tool_call_end` por ID unico
- [x] #8 Adicionar cobertura de testes para fluxo chat agentic e tools avancadas

### Funcionalidades priorizadas
- [x] #11 Playbooks guiados de troubleshooting no chat
- [x] #12 Diff de configuracao com analise de risco de mudanca
- [x] #13 Contexto automatico de anexos para tool calling
- [x] #14 Progresso em tempo real para jobs assincronos no chat
- [x] #17 Guardrails por perfil/plano para tools sensiveis
- [x] #20 Respostas com evidencias e nivel de confianca

### Saida esperada
- Chat agentic robusto para uso operacional real.
- Melhor UX de troubleshooting e analise de arquivos.
- Primeira camada de governanca (guardrails + evidencias).

---

## Sprint 2 (Inteligencia Operacional + Escala)

### Funcionalidades
- [x] #15 Modo pre-change review para validacao de impacto
- [x] #16 Memoria persistente por ambiente e dispositivo
- [x] #18 Fallback automatico de provedor/modelo LLM
- [x] #19 Painel de custo e uso BYO-LLM

### Alinhamento tecnico
- [x] #9 Sincronizar documentacao e configuracao de timeout de analise PCAP
- [x] #10 Migrar backend para timestamps timezone-aware e remover uso de `utcnow()`

### Saida esperada
- Agente mais consistente entre sessoes e com menor risco operacional.
- Maior resiliencia de disponibilidade (fallback de provider).
- Visibilidade de custo e desempenho para gestao do produto.

---

## Status Consolidado

Na data de atualizacao deste documento (14/02/2026), todas as issues do roadmap funcional (#5 a #20) estao encerradas no repositorio.  
A issue #21 permanece aberta apenas para formalizar esta consolidacao documental.

---

## Criterios de Sucesso

- Menos regressao no fluxo chat/tool calling.
- Menor tempo medio de troubleshooting assistido.
- Maior confianca do usuario final (evidencias + controle de risco).
- Maior visibilidade operacional de consumo e estabilidade.
