# 🤖 NetGuru - Agentic AI for Network Operations

**BYO-LLM Platform | Multi-Vendor | Compliance-Ready**

NetGuru é uma plataforma de IA agentic especializada em operações de rede, permitindo que engenheiros de rede usem suas próprias API keys de LLM (OpenAI, Anthropic, Azure, ou modelos locais) para diagnóstico inteligente, análise de PCAPs, validação de configurações e geração automática de topologias.

---

## ✨ Features

- 🤖 **Agentic AI**: Agent autônomo que decide quais ferramentas usar para resolver problemas
- 💬 **Chat Conversacional**: Interface natural para perguntas sobre Cisco, Juniper, Arista, Mikrotik
- 📦 **PCAP Analysis**: Análise inteligente de capturas de pacotes com diagnóstico automatizado
- 🗺️ **Topology Generation**: Geração automática de diagramas de rede a partir de configs
- ✅ **Config Validation**: Validação contra golden configs e políticas de compliance
- 🧠 **Dual RAG**: 
  - **RAG Global**: Documentação curada de vendors (Cisco, Juniper, Arista)
  - **RAG Local**: Conhecimento específico do cliente (configs, topologias, tickets)
- 🔐 **BYO-LLM**: Cliente usa sua própria API key (privacidade total, compliance-ready)

---

## 🎯 Diferencial

### Por que NetGuru vs ChatGPT?

| Feature | ChatGPT | NetGuru |
|---------|---------|---------|
| **Contexto de Rede** | Conhecimento geral | RAG especializado (Cisco/Juniper/Arista docs) |
| **Alucinações** | Comuns em configs | Reduzidas por RAG + validação |
| **PCAP Analysis** | ❌ | ✅ Integrado (scapy + pyshark) |
| **Topology Viz** | ❌ | ✅ React Flow automático |
| **Compliance** | Dados saem para OpenAI | BYO-LLM (dados ficam na infra) |
| **Custo** | $20/mês/usuário | 85-90% margem (cliente paga API) |

### Por que NetGuru vs Cisco ThousandEyes Copilot?

- ✅ **Multi-vendor** (não apenas Cisco)
- ✅ **Sem vendor lock-in**
- ✅ **10x mais barato** (BYO-LLM)
- ✅ **On-prem ou cloud** (flexível)

---

## 🚀 Quick Start

### Pré-requisitos

```bash
# Instalados na máquina
- Docker 24+
- Docker Compose 2.20+
- Git

# Para desenvolvimento local
- Python 3.11+
- Node.js 20+
- OpenAI/Anthropic API Key (para testes)
```

### Instalação

```bash
# 1. Clone do repositório
git clone https://github.com/your-org/netguru.git
cd netguru

# 2. Configure variáveis de ambiente
cp backend/.env.example backend/.env
# Edite backend/.env e adicione sua OPENAI_API_KEY para testes

# 3. Suba a infraestrutura com Docker Compose
docker-compose up -d

# Aguarde ~30s para inicialização
docker-compose logs -f
```

### Acessos

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **Flower (Celery)**: http://localhost:5555

### Primeiros Passos

1. **Registre uma conta**: http://localhost:5173/register
2. **Configure sua API key**: Settings → API Keys → Add OpenAI Key
3. **Faça uma pergunta**: Chat → "Como configurar OSPF no Cisco IOS?"
4. **Veja o agent trabalhar**: Observe as tools sendo chamadas (RAG Global, parser, etc)

---

## 🏗️ Arquitetura

```
┌─────────────────┐
│   React + TS    │
│  (Frontend)     │ ← WebSocket streaming
└────────┬────────┘
         │
    ┌────▼────┐
    │  Nginx  │
    └────┬────┘
         │
┌────────▼───────────────────┐
│    FastAPI Backend         │
│                            │
│  NetworkEngineerAgent      │ ← LangGraph (ReAct)
│  ├─ RAG Tools              │
│  ├─ PCAP Analyzer (Celery) │
│  ├─ Config Validator       │
│  └─ Topology Builder       │
└────────┬───────────────────┘
         │
    ┌────▼────────┐
    │ PostgreSQL  │
    │ + pgvector  │
    └─────────────┘
         │
    ┌────▼────┐
    │  Redis  │
    └─────────┘
```

### Stack Técnica

- **Backend**: FastAPI + Python 3.11
- **Frontend**: React 18 + TypeScript + Vite
- **Database**: PostgreSQL 15 + pgvector
- **Cache/Queue**: Redis 7
- **Workers**: Celery + Flower
- **AI**: LangGraph + LangChain + sentence-transformers
- **Infra**: Docker + Docker Compose

---

## 📚 Documentação

| Documento | Descrição |
|-----------|-----------|
| [📖 CLAUDE.md](CLAUDE.md) | Guia completo para desenvolvimento (AI assistants) |
| [📋 docs/00-overview.md](docs/00-overview.md) | Visão geral técnica e glossário |
| [🏗️ docs/01-architecture.md](docs/01-architecture.md) | Arquitetura detalhada |
| [🗄️ docs/02-database-design.md](docs/02-database-design.md) | Schema PostgreSQL + Redis |
| [🔌 docs/03-api-specification.md](docs/03-api-specification.md) | Endpoints REST + WebSocket |
| [🔐 docs/04-security-model.md](docs/04-security-model.md) | Segurança e autenticação |
| [🧠 docs/05-rag-implementation.md](docs/05-rag-implementation.md) | Implementação de RAG |
| [🤖 docs/11-agent-architecture.md](docs/11-agent-architecture.md) | Arquitetura agentic (LangGraph) |

**Para desenvolvedores:** Comece pelo [CLAUDE.md](CLAUDE.md) - guia completo de desenvolvimento.

---

## 🛠️ Desenvolvimento

### Setup Local (sem Docker)

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configurar database
createdb netguru
alembic upgrade head

# Popular RAG Global (docs Cisco sample)
python -m app.scripts.seed_rag_global

# Rodar
uvicorn app.main:app --reload

# Celery worker (outro terminal)
celery -A app.workers.celery_app worker --loglevel=info
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

### Testes

```bash
# Backend
cd backend
pytest                                    # Todos os testes
pytest tests/agents/ -v                   # Apenas agents
pytest --cov=app --cov-report=html        # Coverage

# Frontend
cd frontend
npm test                                  # Vitest
npm run test:e2e                          # Playwright E2E
```

### Estrutura do Projeto

```
netguru/
├── backend/           # FastAPI + Agent system
├── frontend/          # React + Vite
├── docs/              # Documentação técnica (10 arquivos MD)
├── docker-compose.yml # Orquestração local
└── CLAUDE.md          # Guia para AI assistants
```

---

## 🎓 Casos de Uso

### 1. Troubleshooting Multi-Step

**User:** "Minha rede está lenta desde ontem às 14h"

**Agent faz:**
1. 🔍 Busca mudanças recentes no RAG Local
2. 📦 Analisa PCAP do período (se disponível)
3. 📊 Parse de `show commands` (STP, interfaces)
4. 💡 Sintetiza diagnóstico: "Broadcast storm causado por novo switch sem priority configurada"
5. ✅ Sugere correção com comandos prontos

### 2. Config Review Automatizado

**User:** Upload de `router-config.txt`

**Agent faz:**
1. 📋 Parse da config (ciscoconfparse)
2. ✅ Valida contra golden config
3. 🔍 Busca best practices no RAG Global
4. 📝 Gera report: "3 issues críticos, 5 warnings, 12 ok"

### 3. Documentação Instantânea

**User:** "Como configurar OSPF authentication MD5?"

**Agent faz:**
1. 🔍 Busca RAG Global (docs Cisco oficiais)
2. 💬 Sintetiza resposta com exemplos
3. 📚 Inclui links para docs completos

---

## 🚧 Roadmap

### ✅ Phase 1-2: Foundation (Sprint 1-2) - **Em Progresso**
- [x] Setup FastAPI + PostgreSQL + Redis
- [x] Auth system (JWT)
- [x] Agent básico (LangGraph setup)
- [x] Docker Compose development

### 🔜 Phase 3-4: Core Features (Sprint 3-4)
- [ ] RAG Global/Local implementation
- [ ] Agent com RAG tools
- [ ] Chat interface com WebSocket
- [ ] Tool call visualization

### 📅 Phase 5-6: Advanced Tools (Sprint 5-6)
- [ ] PCAP Analyzer (Celery + scapy)
- [ ] Config Validator
- [ ] Topology Builder (React Flow)
- [ ] Show commands parser

### 🔮 Future
- [ ] ServiceNow/Jira integration
- [ ] Multi-agent collaboration
- [ ] Network automation (safe commands)
- [ ] Custom RAG training por cliente

---

## 🤝 Contribuindo

### Para Desenvolvedores

1. Leia [CLAUDE.md](CLAUDE.md) para entender arquitetura e convenções
2. Crie uma branch: `feature/minha-feature`
3. Desenvolva seguindo padrões:
   - Python: `snake_case`, type hints obrigatórios
   - TypeScript: `camelCase`, interfaces com `I` prefix
   - Commits: Conventional Commits em português
4. Teste: `pytest` (backend) e `npm test` (frontend)
5. PR com descrição clara

### Para AI Assistants (Claude, ChatGPT, Copilot)

Sempre inicie conversas com:
```
"Leia o CLAUDE.md (ou AGENTS.md) antes de responder"
```

O arquivo contém:
- Arquitetura completa
- Convenções de código
- Padrões de desenvolvimento
- Stack técnica
- Workflows

---

## 📄 Licença

MIT License - veja [LICENSE](LICENSE) para detalhes.

---

## 🌟 Público-Alvo

### Primary
- 👤 **Solo Network Engineers**: CCNAs/CCNPs que querem automação barata
- 🏢 **MSPs**: Provedores de serviços gerenciados (multi-cliente)

### Secondary
- 🏦 **Enterprises**: Times de NOC/SOC que precisam compliance
- 🎓 **Estudantes**: Preparação para certificações (CCNA, CCNP, CCIE)

---

## 💰 Modelo de Negócio (BYO-LLM)

**Cliente fornece:**
- API Key própria (OpenAI, Anthropic, Azure, ou local Ollama)

**NetGuru fornece:**
- Agent orchestration (LangGraph)
- Tools especializadas (PCAP, Config Validator, Topology)
- RAG Global curado (docs Cisco/Juniper/Arista)
- Interface + Backend

**Resultado:**
- ✅ Margens de 85-90% (custo de IA é do cliente)
- ✅ Total privacidade (compliance LGPD, GDPR, SOC2)
- ✅ Flexibilidade (cliente escolhe modelo)
- ✅ On-prem possível (dados não saem da infra)

---

## 📞 Suporte

- **Issues**: [GitHub Issues](https://github.com/your-org/netguru/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/netguru/discussions)
- **Email**: support@netguru.io
- **Docs**: [docs/](docs/)

---

## 🏆 Equipe

Desenvolvido com ❤️ para Network Engineers que querem trabalhar smarter, not harder.

**Status do Projeto:** 🚧 MVP em desenvolvimento (Q1 2026)

---

## 🔗 Links Úteis

- [Business Plan](business_plan.md) - Visão de negócio completa
- [LangGraph Docs](https://langchain-ai.github.io/langgraph/) - Framework do agent
- [FastAPI Docs](https://fastapi.tiangolo.com/) - Backend framework
- [React Flow](https://reactflow.dev/) - Topology visualization

---

**⚡ Built with Agentic AI | 🔐 BYO-LLM | 🌍 Multi-Vendor**

*"O futuro das Network Operations é agentic."*
