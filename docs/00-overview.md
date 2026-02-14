# NetGuru Platform - Visão Geral Técnica

**Versão:** 1.0  
**Data:** Fevereiro 2026  
**Status:** Em Desenvolvimento

---

## 📋 Índice de Navegação

| Documento | Descrição | Quando Consultar |
|-----------|-----------|------------------|
| **[00-overview.md](00-overview.md)** | Este arquivo - Visão geral e glossário | Início do projeto |
| **[01-architecture.md](01-architecture.md)** | Arquitetura técnica completa | Setup inicial e referência |
| **[02-database-design.md](02-database-design.md)** | Schema PostgreSQL + Redis | Criação de migrations |
| **[03-api-specification.md](03-api-specification.md)** | Endpoints REST + WebSocket | Desenvolvimento de APIs |
| **[04-security-model.md](04-security-model.md)** | Autenticação e segurança | Features de auth/upload |
| **[05-rag-implementation.md](05-rag-implementation.md)** | Implementação Dual RAG | Features de IA |
| **[06-phase1-foundation.md](06-phase1-foundation.md)** | Sprint 1-2: Fundação | Primeira implementação |
| **[07-phase2-core-features.md](07-phase2-core-features.md)** | Sprint 3-4: Chat + RAG | MVP core |
| **[08-phase3-agents.md](08-phase3-agents.md)** | Sprint 5-6: Agents | Diferenciadores |
| **[09-deployment.md](09-deployment.md)** | Docker e CI/CD | Deploy e produção |
| **[10-testing-strategy.md](10-testing-strategy.md)** | Testes automatizados | Durante todo desenvolvimento |
| **[11-agent-architecture.md](11-agent-architecture.md)** | Arquitetura detalhada do agent | Evolução do orchestration |
| **[12-roadmap-funcional-2-sprints.md](12-roadmap-funcional-2-sprints.md)** | Roadmap funcional consolidado | Priorização e dependências |

---

## 🎯 Sobre o Projeto

O **NetGuru** é uma plataforma AI-powered para Network Operations baseada no modelo **BYO-LLM** (Bring Your Own LLM). Diferente de ferramentas tradicionais, funciona como um engenheiro de rede sênior virtual capaz de:

- 🤖 Responder dúvidas técnicas sobre configurações Cisco/Juniper/Arista
- 📦 Analisar arquivos PCAP e diagnosticar problemas de rede
- 🗺️ Gerar visualizações de topologia automaticamente
- ✅ Validar configurações contra Golden Configs
- 🧠 Aprender com a documentação específica do cliente (RAG Local)

### Diferencial Estratégico

**Modelo BYO-LLM:** O cliente usa sua própria API key (OpenAI, Anthropic, Azure) ou modelos locais. A NetGuru fornece:
- RAG Global curado (documentação técnica de vendors)
- RAG Local (conhecimento do cliente)
- Camada de orquestração de agentes
- Interface de chat profissional

**Vantagens:**
- ✅ Custo marginal de IA transferido ao cliente (margens ~85-90%)
- ✅ Total privacidade e compliance (dados não saem da infra do cliente)
- ✅ Flexibilidade de escolha de modelo

---

## 🛠️ Stack Tecnológica

### Backend
- **Framework:** FastAPI 0.104+
- **Linguagem:** Python 3.11+
- **Database:** PostgreSQL 15 + pgvector extension
- **Cache/Queue:** Redis 7+
- **Workers:** Celery + Flower
- **AI Stack:** LangChain, sentence-transformers
- **File Processing:** scapy, pyshark, pandas

### Frontend
- **Framework:** React 18 + TypeScript
- **Build Tool:** Vite 5
- **Styling:** Tailwind CSS
- **State:** Zustand
- **Routing:** React Router v6
- **API Client:** Axios + TanStack Query
- **Visualização:** React Flow, Recharts

### Infrastructure
- **Containers:** Docker + Docker Compose
- **Web Server:** Nginx
- **CI/CD:** GitHub Actions
- **Monitoring:** Prometheus + Grafana
- **Logging:** structlog + Loki

---

## 📊 Arquitetura de Alto Nível

```
┌─────────────────┐
│   React + Vite  │
│    Frontend     │
└────────┬────────┘
         │ HTTP/WS
         ↓
┌─────────────────┐
│  Nginx Reverse  │
│      Proxy      │
└────────┬────────┘
         │
         ↓
┌─────────────────┐     ┌──────────────┐
│   FastAPI       │────→│  PostgreSQL  │
│   Backend       │     │  + pgvector  │
└────────┬────────┘     └──────────────┘
         │
         ├──→ Redis (Cache/Sessions/Queue)
         │
         ├──→ Celery Workers (PCAP/Topology)
         │
         └──→ Client's LLM API (OpenAI/Anthropic)
```

---

## 📚 Glossário

### Termos de Negócio

**BYO-LLM (Bring Your Own LLM)**  
Modelo onde o cliente fornece sua própria API key para serviços de IA, mantendo controle sobre custos e privacidade.

**Solo Engineer / Team / Enterprise**  
Tiers de planos de assinatura do NetGuru.

**MSP (Managed Service Provider)**  
Empresas que gerenciam infraestrutura de TI de terceiros - público-alvo chave.

### Termos Técnicos

**RAG (Retrieval-Augmented Generation)**  
Técnica que combina busca em base de conhecimento com geração de texto por LLM, reduzindo alucinações.

**RAG Global**  
Base de conhecimento curada pela NetGuru com documentação oficial de vendors (Cisco, Juniper, Arista).

**RAG Local**  
Base de conhecimento específica do cliente, criada a partir de uploads (configs, topologias, tickets).

**Agentic AI**  
IA baseada em agentes autônomos que podem usar ferramentas e tomar decisões sequenciais.

**PCAP (Packet Capture)**  
Formato de arquivo que contém pacotes de rede capturados (Wireshark, tcpdump).

**pgvector**  
Extensão do PostgreSQL para armazenar e buscar embeddings vetoriais.

**Embedding**  
Representação numérica (vetor) de texto que captura significado semântico.

**CDP/LLDP**  
Protocolos de descoberta de vizinhos em redes (Cisco Discovery Protocol / Link Layer Discovery Protocol).

**Golden Config**  
Configuração padrão aprovada que serve como baseline para validação.

**RAPTOR**  
Técnica de processamento recursivo para criar resumos hierárquicos de documentos longos.

### Termos de Rede

**CCIE**  
Cisco Certified Internetwork Expert - certificação de nível avançado.

**MTTR**  
Mean Time To Resolution - tempo médio para resolver um incidente.

**STP**  
Spanning Tree Protocol - protocolo de prevenção de loops em redes.

**OSPF**  
Open Shortest Path First - protocolo de roteamento dinâmico.

---

## 🚀 Quick Start para Desenvolvedores

### Pré-requisitos
```bash
- Docker 24+ e Docker Compose 2.20+
- Python 3.11+
- Node.js 20+
- Git
```

### Setup Local

```bash
# Clone do repositório
git clone https://github.com/your-org/netguru.git
cd netguru

# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install

# Subir infraestrutura
docker-compose up -d postgres redis

# Migrations
cd ../backend
alembic upgrade head

# Rodar backend
uvicorn app.main:app --reload

# Rodar frontend (outro terminal)
cd ../frontend
npm run dev
```

### Acessos
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Flower (Celery): http://localhost:5555

---

## 📋 Convenções de Código

### Python (Backend)
```python
# Naming
- Classes: PascalCase (UserService, ChatRouter)
- Functions/Variables: snake_case (get_current_user, api_key)
- Constants: UPPER_SNAKE_CASE (MAX_FILE_SIZE_MB)
- Private: _leading_underscore (_validate_token)

# Imports Order
1. Standard library
2. Third-party
3. Local application

# Type Hints obrigatórios
def create_user(email: str, password: str) -> User:
    ...
```

### TypeScript (Frontend)
```typescript
// Naming
- Components: PascalCase (ChatWindow, FileUpload)
- Functions/Variables: camelCase (handleSubmit, userId)
- Constants: UPPER_SNAKE_CASE (API_BASE_URL)
- Interfaces: PascalCase + I prefix (IUser, IMessage)

// Props Typing
interface ChatWindowProps {
  conversationId: string;
  onSendMessage: (msg: string) => void;
}
```

### Git Workflow
```bash
# Branch naming
feature/add-pcap-analysis
fix/websocket-connection
docs/update-api-spec
refactor/rag-service

# Commits (Conventional Commits)
feat: add PCAP upload endpoint
fix: resolve JWT expiration bug
docs: update architecture diagram
test: add RAG service unit tests
```

---

## 🎓 Recursos de Aprendizado

### FastAPI
- [Documentação Oficial](https://fastapi.tiangolo.com/)
- [Full Stack FastAPI Template](https://github.com/tiangolo/full-stack-fastapi-template)

### LangChain
- [LangChain Docs](https://python.langchain.com/)
- [RAG Tutorial](https://python.langchain.com/docs/use_cases/question_answering/)

### React + Vite
- [Vite Guide](https://vitejs.dev/guide/)
- [React Flow Docs](https://reactflow.dev/)

### Network Engineering
- [Cisco Configuration Guides](https://www.cisco.com/c/en/us/support/index.html)
- [Wireshark User Guide](https://www.wireshark.org/docs/)

---

## 📞 Suporte

**Comunicação do Time:**
- Issues: GitHub Issues para bugs e features
- Discussões: GitHub Discussions para arquitetura
- Documentação: Sempre atualizar MDs junto com código

**Dúvidas sobre este documento:**  
Abra uma issue com label `documentation`

---

## 🗺️ Próximos Passos

1. ✅ Leia [01-architecture.md](01-architecture.md) para entender a estrutura completa
2. ✅ Revise [02-database-design.md](02-database-design.md) para o modelo de dados
3. ✅ Estude [03-api-specification.md](03-api-specification.md) para contratos de API
4. 🚀 Comece implementação com [06-phase1-foundation.md](06-phase1-foundation.md)

**Boa construção! 🚀**
