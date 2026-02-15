
# 🤖 Claude AI Assistant - NetGuru Project Guide

**Versão:** 1.0  
**Última Atualização:** 15 Fevereiro 2026
**Propósito:** Guia completo para assistência AI no desenvolvimento do NetGuru

> **⚠️ Manutenção**: Se qualquer procedimento documentado aqui estiver desatualizado, sugira correções e atualize este arquivo.

> **📝 CHECKPOINT TEMPORÁRIO (REMOVER NA PRÓXIMA SESSÃO):**
> Sprint 13 — Brainwork Crawler para RAG Global:
> - **BrainworkCrawlerService**: crawlea sitemap XML do brainwork.com.br, filtra posts, dedup via `document_metadata.source_url`
> - **Reutiliza UrlIngestionService**: SSRF check, download, BS4 extraction, Document creation
> - **Metadata enriquecida**: `source=brainwork`, `category=community`, `ingestion_method=crawler`
> - **Task Celery**: `crawl_brainwork_blog` com beat schedule (24h), autoretry
> - **Endpoint admin**: `POST /admin/rag/crawl-brainwork` com audit log
> - **Frontend**: botao "Executar Crawler" na aba RAG Global do AdminRagPage
> - **Config**: `BRAINWORK_CRAWL_HOURS=24`, `BRAINWORK_CRAWL_MAX_PAGES=50`, `BRAINWORK_CRAWL_DELAY_SECONDS=1.0`

---

## ⚙️ Configurações Globais

### Ambiente Python
- **venv**: Sempre ativar ambiente virtual antes de qualquer comando Python
  ```bash
  source venv/bin/activate  # Linux/Mac
  venv\Scripts\activate     # Windows
  ```

### Commits e Git
- **NÃO incluir** assinaturas automáticas do Claude:
  - ❌ "Generated with Claude Code"
  - ❌ "Co-Authored-By: Claude"
- **Mensagens descritivas em português**
- **SEMPRE perguntar antes de commitar**
- Formato: `tipo(escopo): descrição`
  - Exemplo: `feat(agent): adicionar tool de análise PCAP`

### Convenções de Código
- **Python**: `snake_case` para funções/variáveis, `PascalCase` para classes
- **JavaScript/TypeScript**: `camelCase` para funções/variáveis, `PascalCase` para componentes
- **Type hints sempre** (Python e TypeScript)
- **Docstrings obrigatórias** para funções públicas

### Modelagem de Dados (Regra de Ouro)
- **NUNCA usar IDs previsíveis/sequenciais** (ex.: auto incremento) em tabelas de domínio
- **SEMPRE usar UUID** para chaves primárias e estrangeiras relacionadas
- Novas migrations e novos modelos devem seguir esse padrão por padrão (secure-by-default)

### Pattern Discovery (CRÍTICO)
- **SEMPRE buscar padrões existentes** no código antes de implementar algo novo
- **Reutilizar helpers** de `app/services/`, `app/core/`, `frontend/src/services/`
- **NUNCA reinventar a roda**
- Exemplos:
  ```bash
  # Antes de criar novo validator
  grep -r "def validate_" backend/app/
  
  # Antes de criar novo hook
  grep -r "use[A-Z]" frontend/src/
  ```

---

## 📋 Índice

1. [Sobre Este Documento](#sobre-este-documento)
2. [Visão Geral do Projeto](#visão-geral-do-projeto)
3. [Arquitetura e Stack](#arquitetura-e-stack)
4. [Estrutura do Projeto](#estrutura-do-projeto)
5. [Convenções e Padrões](#convenções-e-padrões)
6. [Workflows de Desenvolvimento](#workflows-de-desenvolvimento)
7. [Como Ajudar em Tarefas Específicas](#como-ajudar-em-tarefas-específicas)
8. [Contextos de Conversa](#contextos-de-conversa)
9. [Referências Rápidas](#referências-rápidas)

---

## 📖 Sobre Este Documento

### Propósito
Este documento serve como **memória persistente** e **contexto inicial** para sessões de assistência AI (Claude/ChatGPT/Copilot) no desenvolvimento do NetGuru. 

### Como Usar
**Desenvolvedores:** Sempre comece novas conversas com:
```
"Leia o CLAUDE.md na raiz do projeto antes de responder"
```

**AI Assistants:** Ao receber este arquivo:
1. ✅ Absorva a arquitetura e decisões técnicas
2. ✅ Respeite as convenções estabelecidas
3. ✅ Use os padrões de código documentados
4. ✅ Consulte a documentação em `/docs` para detalhes
5. ✅ Sempre sugira código alinhado com a stack escolhida

### Princípios de Assistência
- 🎯 **Contexto primeiro**: Entenda o objetivo antes de codificar
- 🔍 **Pergunte quando incerto**: Melhor clarificar que assumir
- 📚 **Referencie documentação**: Aponte para arquivos MD relevantes
- ✅ **Código testável**: Sempre considere testing
- 🚀 **MVP-focused**: Priorize simplicidade e entrega rápida
- 🔁 **Reutilize padrões**: Busque código similar antes de criar novo

---

## 🎯 Visão Geral do Projeto

### O Que É o NetGuru?

**NetGuru** é uma plataforma **AI-powered Agentic** para Network Operations baseada no modelo **BYO-LLM** (Bring Your Own LLM).

**Analogia:** Pense no NetGuru como um "GitHub Copilot para Engenheiros de Rede", mas com superpoderes:
- 💬 Chat conversacional sobre Cisco/Juniper/Arista
- 🤖 Agent autônomo que decide quais ferramentas usar
- 📦 Análise de PCAPs com diagnóstico inteligente
- 🗺️ Geração automática de topologias de rede
- ✅ Validação de configs contra golden templates
- 🧠 RAG Dual (Global + Local) para contexto preciso

### Diferencial Estratégico

**BYO-LLM + Arquitetura Agentic:**
1. Cliente usa **sua própria API key** (OpenAI/Anthropic/Azure/Local)
2. NetGuru fornece:
   - 🤖 Agent orchestration (LangGraph)
   - 🧰 Tools especializadas em network engineering
   - 📚 RAG Global curado (docs de vendors)
   - 📂 RAG Local (conhecimento do cliente)

**Por que isso importa?**
- ✅ Custo de IA transferido ao cliente (margens ~85-90%)
- ✅ Total privacidade (dados não saem da infra)
- ✅ Compliance-ready (bancos, governos)
- ✅ Flexibilidade de modelo (não lock-in com OpenAI)

### Público-Alvo

**Primary:**
- 👤 Solo Network Engineers (CCNA/CCNP)
- 🏢 MSPs (Managed Service Providers)

**Secondary:**
- 🏦 Enterprises com times de NOC
- 🎓 Estudantes de certificações

### Competidores

| Competidor | Forte em | Fraco em | NetGuru vs |
|------------|----------|----------|------------|
| **Cisco ThousandEyes Copilot** | Monitoring integrado | Vendor lock-in, caro | ✅ Multi-vendor, BYO-LLM |
| **Selector AI** | Multi-agent avançado | Complexo, precisa GPU | ✅ Simples, cloud ou on-prem |
| **ChatGPT (genérico)** | Geral | Sem contexto de rede, alucina | ✅ RAG especializado |

---

## 🏗️ Arquitetura e Stack

### Decisão Arquitetural: AGENTIC desde o início

**⚠️ IMPORTANTE:** O projeto usa **arquitetura agentic** desde o MVP (não é híbrido com migração futura).

**Por quê?**
1. ✅ Business plan prometeu agents ("Agentic AI Engineering")
2. ✅ Evita refatoração custosa (3+ semanas) depois
3. ✅ Competidores são agentic (Selector AI, Cisco Copilot)
4. ✅ LangGraph torna agentic tão simples quanto pipeline fixo
5. ✅ Clientes esperam "AI Agent" em 2026

### Stack Técnica

```yaml
Backend:
  framework: FastAPI 0.104+
  language: Python 3.11+
  database: PostgreSQL 15 + pgvector
  cache: Redis 7+
  workers: Celery + Flower
  
  # AI Stack
  ai_orchestration: LangGraph 0.0.40+
  ai_framework: LangChain 0.1.0+
  embeddings: sentence-transformers/all-MiniLM-L6-v2
  vector_store: pgvector (MVP) → Qdrant (scale)
  
  # Network Engineering
  pcap_analysis: scapy, pyshark
  config_parsing: ciscoconfparse, ttp
  
Frontend:
  framework: React 18 + TypeScript
  build: Vite 5
  styling: Tailwind CSS
  state: Zustand
  routing: React Router v6
  api: Axios + TanStack Query
  visualization: React Flow, Recharts
  
Infrastructure:
  containers: Docker + Docker Compose
  webserver: Nginx
  cicd: GitHub Actions
  monitoring: Prometheus + Grafana
  logging: structlog + Loki
```

### Arquitetura Agentic - Componente Central

```
User Message
    ↓
FastAPI Endpoint (/api/v1/chat/message)
    ↓
┌──────────────────────────────────────────────────┐
│         NetworkEngineerAgent (LangGraph)         │
│                                                  │
│  Loop de Decisão (ReAct Pattern):               │
│  ┌────────────────────────────────────────┐     │
│  │ 1. Reason: Analisa o que precisa fazer │     │
│  │ 2. Act: Escolhe e executa tool         │     │
│  │ 3. Observe: Processa resultado da tool │     │
│  │ 4. Loop até ter resposta completa      │     │
│  └────────────────────────────────────────┘     │
│                                                  │
│  Tools Disponíveis (Phase-wise):                │
│                                                  │
│  Phase 1-2 (Foundation):                         │
│  └─ (setup infra, ainda sem tools)               │
│                                                  │
│  Phase 3-4 (Core):                               │
│  ├─ 🔍 search_rag_global_tool                    │
│  ├─ 📂 search_rag_local_tool                     │
│  └─ 📋 parse_config_tool                         │
│                                                  │
│  Phase 5-6 (Advanced):                           │
│  ├─ 📦 analyze_pcap_tool (Celery async)          │
│  ├─ ✅ validate_config_tool                      │
│  ├─ 🗺️ generate_topology_tool (Celery async)    │
│  └─ 📊 parse_show_commands_tool                  │
└──────────────────────────────────────────────────┘
    ↓
Response JSON:
{
  "response": "Resposta sintetizada pelo agent",
  "tool_calls": [
    {
      "tool": "search_rag_global",
      "input": "OSPF authentication configuration",
      "output": "OSPF supports MD5...",
      "duration_ms": 234
    }
  ],
  "reasoning_steps": [
    "User asked about OSPF authentication",
    "Searching vendor documentation",
    "Found relevant examples",
    "Synthesizing answer"
  ],
  "tokens_used": 1250
}
```

---

## 📁 Estrutura do Projeto

```
/home/leandroo/GitHub/netguru/
├── CLAUDE.md                        # 🤖 Este arquivo
├── README.md
├── business_plan.md                 # 💼 Contexto de negócio
├── docker-compose.yml
├── .gitignore
│
├── backend/                         # FastAPI
│   ├── app/
│   │   ├── agents/                  # 🤖 Agent system
│   │   │   ├── __init__.py
│   │   │   ├── network_engineer_agent.py
│   │   │   ├── state.py
│   │   │   └── tools/
│   │   │       ├── __init__.py
│   │   │       ├── rag_tools.py
│   │   │       ├── config_tools.py          # parse_config, validate_config
│   │   │       ├── show_command_tools.py     # parse_show_commands
│   │   │       ├── pcap_tools.py            # analyze_pcap
│   │   │       └── topology_tools.py
│   │   │
│   │   ├── api/v1/endpoints/
│   │   │   ├── auth.py
│   │   │   ├── chat.py              # Agent invocation
│   │   │   ├── files.py
│   │   │   └── users.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── dependencies.py
│   │   │
│   │   ├── models/                  # SQLAlchemy
│   │   ├── schemas/                 # Pydantic
│   │   ├── services/                # Business logic
│   │   ├── workers/                 # Celery
│   │   └── main.py
│   │
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                        # React + Vite
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   │   ├── ChatWindow.tsx
│   │   │   │   ├── ToolCallDisplay.tsx
│   │   │   │   └── ReasoningSteps.tsx
│   │   │   └── topology/
│   │   │
│   │   ├── pages/
│   │   ├── services/
│   │   ├── stores/                  # Zustand
│   │   └── types/
│   │
│   ├── package.json
│   └── Dockerfile
│
└── docs/                            # 📚 Documentação técnica
    ├── 00-overview.md               # ⭐ Start here
    ├── 01-architecture.md
    ├── 02-database-design.md
    ├── 03-api-specification.md
    ├── 04-security-model.md
    ├── 05-rag-implementation.md
    ├── 06-phase1-foundation.md      # Sprint 1-2
    ├── 07-phase2-core-features.md   # Sprint 3-4
    ├── 08-phase3-agents.md          # Sprint 5-6
    ├── 09-deployment.md
    ├── 10-testing-strategy.md
    └── 11-agent-architecture.md     # ⭐ Agent details
```

---

## 🎨 Convenções e Padrões

### Python (Backend)

#### Naming
```python
# Classes: PascalCase
class NetworkEngineerAgent:
    pass

# Functions/Variables: snake_case
def get_current_user():
    pass

# Constants: UPPER_SNAKE_CASE
MAX_FILE_SIZE_MB = 100

# Tools: snake_case + _tool suffix
async def search_rag_global_tool(query: str) -> str:
    pass
```

#### Type Hints (Obrigatórios)
```python
from typing import Optional, List, Dict

def create_user(
    email: str, 
    password: str,
    plan_tier: str = "solo"
) -> User:
    ...
```

#### Docstrings (Google Style)
```python
def search_rag_global(query: str, top_k: int = 5) -> List[Document]:
    """
    Search the Global RAG for vendor documentation.
    
    Args:
        query: User's technical question
        top_k: Number of documents to retrieve
        
    Returns:
        List of relevant documents with scores
        
    Example:
        >>> docs = search_rag_global("How to configure OSPF?")
    """
    ...
```

#### Imports Order
```python
# 1. Standard library
import os
from typing import Optional

# 2. Third-party
from fastapi import FastAPI
from langgraph.prebuilt import create_react_agent

# 3. Local
from app.core.config import settings
```

### TypeScript (Frontend)

```typescript
// Components: PascalCase
const ChatWindow: React.FC = () => { ... }

// Functions: camelCase
const handleSubmit = () => { ... }

// Constants: UPPER_SNAKE_CASE
const API_BASE_URL = import.meta.env.VITE_API_URL;

// Interfaces: PascalCase + I prefix
interface IUser {
  id: string;
  email: string;
}

interface IAgentResponse {
  response: string;
  toolCalls: IToolCall[];
}
```

### Git Workflow

**⚠️ Fase Inicial (até MVP rodando):**
- Trabalhar **direto na `main`** (sem branches)
- Commits frequentes e descritivos
- Quando tivermos primeira versão funcional → criar `develop` branch

**Pós-MVP (quando tiver versão rodando):**
```bash
# Branch naming
feature/add-pcap-analyzer-tool
fix/agent-infinite-loop
docs/update-agent-architecture
```

**Commits (Conventional - em português):**
```bash
feat(agent): adicionar tool de análise PCAP
fix(agent): corrigir loop infinito no reasoning
docs: atualizar diagrama de arquitetura
test(agent): adicionar testes de tool calling
```

---

## 🔄 Workflows de Desenvolvimento

### 1. Adicionando Nova Tool ao Agent

```python
# filepath: backend/app/agents/tools/config_tools.py

async def validate_bgp_config_tool(config_text: str) -> str:
    """
    Validates BGP configuration for common issues.
    
    Useful when user asks about BGP or wants config review.
    
    Args:
        config_text: Cisco IOS BGP config
        
    Returns:
        Validation report with issues/warnings
    """
    try:
        parser = ConfigParser()
        result = await parser.validate_bgp(config_text)
        return result.format_report()
    except Exception as e:
        return f"Error validating BGP: {str(e)}"

# Register as LangChain Tool
bgp_validator_tool = Tool(
    name="validate_bgp_config",
    description="""
    Validates BGP configuration.
    Input: Cisco IOS BGP config text.
    Use when user mentions BGP problems or wants review.
    """,
    func=validate_bgp_config_tool
)
```

**Registrar:**
```python
# filepath: backend/app/agents/tools/__init__.py

def get_all_tools(user_id: int):
    return [
        search_rag_global_tool,
        search_rag_local_tool,
        bgp_validator_tool,  # NEW
    ]
```

**Testar:**
```python
# filepath: backend/tests/agents/tools/test_config_tools.py

@pytest.mark.asyncio
async def test_bgp_validator_detects_missing_router_id():
    config = """
    router bgp 65001
     neighbor 10.0.0.1 remote-as 65002
    """
    
    result = await validate_bgp_config_tool(config)
    assert "router-id" in result.lower()
```

### 2. Buscando Padrões Existentes

**Antes de implementar, SEMPRE pesquise:**

```bash
# Procurar validadores existentes
grep -r "def validate_" backend/app/

# Procurar parsers existentes
grep -r "class.*Parser" backend/app/

# Procurar hooks React
grep -r "use[A-Z]" frontend/src/

# Procurar serviços similares
find backend/app/services -name "*.py" | xargs grep "class.*Service"
```

---

## 💡 Como Ajudar em Tarefas Específicas

### "Implementar feature X"

**Processo:**
1. ✅ **Clarificar escopo**: "Para qual fase? MVP ou futuro?"
2. ✅ **Buscar padrões**: `grep -r "similar_feature" backend/`
3. ✅ **Consultar docs**: Verificar `docs/0X-phaseY.md`
4. ✅ **Propor arquitetura**: "Service + Tool + Endpoint + Frontend"
5. ✅ **Gerar código**: Com filepath comments
6. ✅ **Sugerir testes**: Happy path + edge cases

### "Debugar erro X"

**Processo:**
1. ✅ **Reproduzir contexto**: Arquivo? Linha? Stack trace?
2. ✅ **Analisar causa**: Explicar *por que* acontece
3. ✅ **Propor fix**: Código específico
4. ✅ **Prevenir recorrência**: Test case

### "Escrever testes"

**Sempre incluir:**
```python
# Unit test (mock externos)
@pytest.mark.asyncio
async def test_agent_uses_rag_for_protocol_questions():
    with patch('app.agents.tools.search_rag_global') as mock:
        mock.return_value = "OSPF uses..."
        agent = NetworkEngineerAgent(user_id=1, api_key="test")
        result = await agent.run("What is OSPF?")
        assert mock.called
        assert "OSPF" in result["response"]
```

---

## 📖 Referências Rápidas

### Commands

```bash
# Backend
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
celery -A app.workers.celery_app worker --loglevel=info
pytest

# Frontend
cd frontend
npm run dev
npm test

# Docker
docker-compose up -d
docker-compose logs -f backend

# Pattern discovery
grep -r "def validate_" backend/
grep -r "use[A-Z]" frontend/src/
```

### Endpoints Principais

```
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/chat/message         # 🤖 Agent
WS   /ws/chat/{conversation_id}   # Streaming
POST /api/v1/files/upload
GET  /api/v1/agent/tools
POST /api/v1/billing/seats        # 💺 Pre-compra de assentos
GET  /api/v1/billing/subscription # 📊 Plano + uso + seat_info
DELETE /api/v1/users/me/api-keys  # 🔑 Remover API key (inicia grace BYO-LLM)
POST /api/v1/auth/ws-ticket       # 🎫 Ticket efemero para WS (30s, one-time)
GET  /api/v1/admin/llm-models     # 📋 Catalogo de modelos LLM
POST /api/v1/admin/llm-models     # ➕ Criar modelo no catalogo
PATCH /api/v1/admin/llm-models/:id # ✏️ Editar modelo
DELETE /api/v1/admin/llm-models/:id # 🗑️ Remover modelo
POST /api/v1/admin/rag/crawl-brainwork # 🕷️ Crawler Brainwork (trigger manual)
```

### Troubleshooting Comum

1. **Agent não usa tool criada**
   - ✅ Verifique `description` (LLM decide baseado nisso)
   - ✅ Tool está em `get_all_tools()`?

2. **RAG irrelevante**
   - ✅ Embeddings corretos?
   - ✅ Chunk size 500-1000 chars?

3. **Agent em loop**
   - ✅ Adicione `max_iterations`
   - ✅ Early stopping se tool falha 3x

4. **venv não ativado**
   ```bash
   # Sempre verificar antes de pip install
   which python  # Deve mostrar path do venv
   ```

5. **Resposta do assistente vazia (0 text chunks)**
   - ✅ Verificar `backend/logs/netguru.log` — procurar `EMPTY_RESPONSE` ou `ZERO text chunks`
   - ✅ Anthropic retorna `chunk.content` como lista quando tools estao bound — fix em `network_engineer_agent.py`
   - ✅ API key vazia/invalida pode causar falha silenciosa

6. **Mapper failed to initialize (Topology, etc)**
   - ✅ Todo modelo SQLAlchemy DEVE ser importado em `models/__init__.py`
   - ✅ Celery worker tem `import app.models` no `celery_app.py`
   - ✅ Reiniciar backend E Celery worker apos adicionar novo modelo

7. **Logs do backend**
   - Em dev: `backend/logs/netguru.log` (RotatingFileHandler, 10MB x 3)
   - Console: sempre ativo (stdout)
   - SQL queries: controlado por `LOG_LEVEL` no `.env`

---

## ✅ Checklist de Desenvolvimento

**Antes de começar:**
- [ ] Li CLAUDE.md
- [ ] Verifiquei fase atual (Sprint 1-2, 3-4, 5-6)
- [ ] Busquei padrões existentes (`grep -r`)
- [ ] Revisei `docs/0X-phaseY.md`

**Durante:**
- [ ] venv ativado (Python)
- [ ] Código segue convenções
- [ ] Filepath comments
- [ ] Error handling
- [ ] Reutilizei helpers existentes

**Antes de commit:**
- [ ] Linter passou
- [ ] Testes passam
- [ ] Defaults críticos em docs conferem com `backend/app/core/config.py` (ex.: `PCAP_*`, `CHAT_*`)
- [ ] Commit em português
- [ ] SEM assinaturas do Claude
- [ ] Perguntei antes de commitar

---

## 🎯 Objetivos Atuais

### Sprint 1-2 (Foundation) - ✅ Completo
- [x] Setup backend (FastAPI + PostgreSQL + Redis)
- [x] Setup frontend (React + Vite)
- [x] Auth system (JWT)
- [x] Basic agent setup
- [x] Docker Compose

### Sprint 3-4 (Core) - ✅ Completo
- [x] RAG Global/Local
- [x] Agent com RAG tools
- [x] Chat interface
- [x] WebSocket streaming

### Sprint 5-6 (Advanced Tools) - ✅ Completo
- [x] ConfigParserService (Cisco/Juniper)
- [x] ConfigValidatorService (15 regras best practices)
- [x] ShowCommandParserService (textfsm inline)
- [x] PcapAnalyzerService (scapy + asyncio.to_thread)
- [x] Tools registradas no agent (parse_config, validate_config, parse_show_commands, analyze_pcap)
- [x] System prompt e frontend labels atualizados
- [ ] Testes end-to-end via WebSocket

### Sprint 7 (Layout & UX) - ✅ Completo
- [x] Layout universal aside + main para todas as paginas autenticadas
- [x] Sidebar contextual por rota (ChatSidebar, FilesSidebar, MemoriesSidebar, ProfileSidebar)
- [x] Nav dropdown compartilhado no aside (todas as paginas)
- [x] Mobile drawer responsivo (960px breakpoint)
- [x] ChatPage simplificado (sem aside/nav duplicado)

### Sprint 8 (Billing per-seat) - ✅ Completo
- [x] Plan.max_members e price_per_extra_seat_cents (team=3/R$33, enterprise=10/R$25)
- [x] Subscription.seat_quantity para rastrear quantity no Stripe
- [x] SeatService (check_seat_limit, sync_stripe_quantity, get_seat_info)
- [x] Checkout com quantity dinamica: max(plan.max_members, member_count)
- [x] Webhook sync de seat_quantity (checkout.completed, subscription.updated)
- [x] POST /billing/seats para pre-compra de assentos com proration
- [x] Invite retorna 402 quando seats esgotados, sync apos invite/remove
- [x] PlanLimitService.check_seat_limit delegando ao SeatService
- [x] Task Celery reconcile_seat_quantities a cada 6h
- [x] Frontend: secao de assentos no MePage, seats na tabela do PricingPage
- [ ] Testes unitarios e integracao para SeatService

### Sprint 9 (BYO-LLM discount + grace period) - ✅ Completo
- [x] Plan.byollm_discount_cents e stripe_byollm_coupon_id (solo=R$15, team=R$45)
- [x] Subscription.byollm_discount_applied e byollm_grace_notified_at
- [x] Checkout aplica Stripe coupon quando owner tem API key configurada
- [x] Webhook sincroniza byollm_discount_applied (checkout.completed, subscription.updated)
- [x] Task periodica check_byollm_discount_eligibility (a cada 6h):
  - Grace period 7 dias com email warning ao owner
  - Revogacao automatica via stripe.Subscription.delete_discount
  - Restauracao automatica se owner reconfigura API key
- [x] EmailService.send_byollm_discount_warning + task Celery com autoretry
- [x] Email template seed (byollm_discount_warning) na migration
- [x] DELETE /users/me/api-keys para remocao da API key
- [x] Frontend: botao "Remover API Key" no MePage com aviso de grace period
- [x] Frontend: exibicao do desconto BYO-LLM em HomePage, PricingPage e MePage
- [ ] Testes unitarios para check_byollm_discount_eligibility
- [ ] Testes de integracao para DELETE /users/me/api-keys

### Sprint 10 (Catalogo LLM + modelo default por plano) - ✅ Completo
- [x] Modelo `LlmModel` (provider, model_id, display_name, is_active, sort_order) com UUID PK
- [x] Plan.default_llm_model_id FK para llm_models (SET NULL on delete)
- [x] Migration seed com 27 modelos atualizados (7 providers):
  - OpenAI: GPT-5 family (5.2, 5.1, 5, mini, nano), GPT-4.1 family, o3, o3-pro, o4-mini
  - Anthropic: Opus 4.6, Sonnet 4.5, Haiku 4.5, Opus 4.5
  - Google: Gemini 2.5 Pro/Flash/Flash-Lite, Gemini 3 Pro/Flash (Preview)
  - Groq: Llama 3.3 70B, Llama 3.1 8B Instant
  - DeepSeek: V3 Chat, R1 Reasoner
  - OpenRouter: Claude Sonnet 4.5, Gemini 2.5 Flash, DeepSeek V3
- [x] Schemas admin: LlmModelCreate, LlmModelUpdate, LlmModelResponse
- [x] CRUD endpoints GET/POST/PATCH/DELETE `/admin/llm-models` com audit log
- [x] API keys por provider: 7 chaves Fernet em ENCRYPTED_KEYS (`free_llm_api_key_{provider}`)
- [x] `LLMModelResolverService.resolve_plan_model()` — resolucao por plano
- [x] ChatService: resolucao de modelo por plano (free fallback + BYO-LLM)
  - Cadeia: conversation.model_used → plan default → system setting → code default
  - Flag `_used_plan_provider` para diferenciar plan-specific vs global fallback
- [x] Frontend: catalogo CRUD inline em AdminSettingsPage (tabela + form inline)
- [x] Frontend: campos API key por provider em AdminSettingsPage
- [x] Frontend: dropdown "Modelo LLM padrao" agrupado por provider em AdminPlansPage
- [x] Config defaults atualizados: gpt-4.1, claude-sonnet-4-5, gemini-2.5-flash
- [ ] Testes unitarios para resolve_plan_model e CRUD llm-models
- [ ] Testes de integracao para resolucao de modelo no chat

### Sprint 11 (Bugfixes + Observabilidade) - ✅ Completo
- [x] Fix resposta vazia do streaming: tratar `chunk.content` como lista de content blocks
  (Anthropic retorna lista quando tools estao bound, nao string)
- [x] Logging para arquivo em dev: `backend/app/core/logging_config.py`
  - RotatingFileHandler → `backend/logs/netguru.log` (10MB, 3 backups)
  - DEBUG=True: console + arquivo; prod: apenas console
  - Loggers barulhentos silenciados (httpcore, httpx, asyncio)
- [x] Logging de diagnostico no streaming:
  - chat_service.py: log de tentativas LLM (providers, models, source)
  - chat_service.py: warning EMPTY_RESPONSE quando accumulated vazio
  - network_engineer_agent.py: event_count, text_chunks_emitted, warning se zero
- [x] Fix Topology mapper: registrar modelo em `models/__init__.py`
- [x] Fix Celery mapper: `import app.models` no `celery_app.py` (previne mapper failures)
- [x] Fix UUID serialization no audit_log: `_json_safe()` recursivo
- [x] Fix SAWarning DELETE conversations: `passive_deletes=True` em relationships
- [x] Features como checkboxes no AdminPlansPage (substituiu textarea JSON)
- [x] Terminologia: "modelo incluso no plano" em vez de "modelo gratuito"
- [x] Ocultar provider/modelo no chat quando usa LLM do sistema (free fallback)
- [ ] Testes para streaming com content blocks como lista

### Sprint 12 (Security Hardening) - ✅ Completo
- [x] **P0 #39**: RBAC `workspace:billing_manage` em checkout/portal/seats (403 para member/viewer)
- [x] **P0 #40**: Webhook Stripe fail-fast se `webhook_secret` vazio (`StripeNotConfiguredError`)
- [x] **P0 #41**: IDOR PCAP: `analyze_pcap` escopado por `workspace_id`, fallbacks sem escopo removidos
- [x] **P0 #42**: SSRF URL ingestion: `_validate_url_target()` com DNS resolve + bloqueio IP privado
  - Revalidacao apos cada redirect (max 5), hostnames bloqueados (localhost, metadata, .local)
- [x] **P1 #43**: `model_used` validado contra catalogo `llm_models` ativo (criacao 400 + runtime fallback)
- [x] **P1 #44**: WS ticket efemero `POST /auth/ws-ticket` (30s, one-time use Redis)
  - Frontend obtem ticket antes de conectar, fallback para JWT se ticket falhar
- [x] **P1 #45**: Rate limiting Redis-backed: login 10/min, refresh 20/min, forgot-password 5/min
  - `backend/app/core/rate_limit.py` — sliding window, fail-open se Redis falhar
  - Config: `AUTH_RATE_LIMIT_PER_MINUTE` no settings
- [x] **P1 #46**: DELETE /users/me/api-keys exige `API_KEYS_UPDATE_SELF` (era READ)
- [x] **P2 #47**: Erros sanitizados ao cliente (mensagem generica + log interno com detalhes)
- [x] **P2 #48**: CORS R2 usa `cors_origins_list` do settings, warning se wildcard
- [ ] Testes unitarios para rate limiter e RBAC billing
- [ ] Testes de integracao para WS ticket efemero

### Sprint 13 (Brainwork Crawler) - ✅ Completo
- [x] BrainworkCrawlerService: sitemap XML parsing + filtro de posts (`YYYY/MM/DD/slug`)
- [x] Dedup via query `document_metadata.source_url LIKE '%brainwork.com.br%'`
- [x] Reuso de UrlIngestionService (SSRF check, download, BS4 extraction)
- [x] Metadata enriquecida: `source=brainwork`, `category=community`, `ingestion_method=crawler`
- [x] Disparo automatico de `process_document.delay()` para chunking + embedding
- [x] Rate limiting entre requests (`asyncio.sleep` configuravel)
- [x] Task Celery `crawl_brainwork_blog` com beat schedule (a cada 24h)
- [x] Config: `BRAINWORK_CRAWL_HOURS`, `BRAINWORK_CRAWL_MAX_PAGES`, `BRAINWORK_CRAWL_DELAY_SECONDS`
- [x] Endpoint `POST /admin/rag/crawl-brainwork` com `ADMIN_RAG_MANAGE` + audit log
- [x] Schemas: `BrainworkCrawlRequest`, `BrainworkCrawlResponse`
- [x] Frontend: botao "Executar Crawler" na aba RAG Global do AdminRagPage
- [x] Frontend: exibicao de resultado (URLs, novas, ingeridas, falhas, erros)
- [ ] Testes unitarios para BrainworkCrawlerService
- [ ] Teste de dedup (rodar crawler 2x sem duplicar)

---

## 📚 Documentação Relacionada

| Documento | Quando Consultar |
|-----------|------------------|
| `business_plan.md` | Objetivos de negócio |
| `docs/00-overview.md` | Visão geral técnica |
| `docs/11-agent-architecture.md` | Detalhes de agents |
| `docs/06-phase1-foundation.md` | Implementação Sprint 1-2 |

---

## 🚀 Para AI Assistants

Você tem contexto completo do NetGuru. Use para:
- ⚡ Respostas alinhadas com arquitetura
- 🎯 Código seguindo convenções
- 🔍 Buscar padrões antes de criar novo
- 📚 Referenciar docs apropriadas
- 💬 Commits em português, SEM assinaturas

**Lembre-se:**
- ✅ SEMPRE ativar venv antes de comandos Python
- ✅ SEMPRE buscar padrões existentes (`grep -r`)
- ✅ SEMPRE perguntar antes de commitar
- ✅ NUNCA incluir "Generated with Claude" em commits

---

**Versão:** 1.0
**Última atualização:** 15 de Fevereiro de 2026

**Boa construção! 🚀🤖**
