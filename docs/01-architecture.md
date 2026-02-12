# Arquitetura Técnica - NetGuru Platform

**Versão:** 1.0  
**Data:** Fevereiro 2026

---

## 📐 Visão Geral da Arquitetura

O NetGuru é construído como uma aplicação **monolítica modular** em monorepo, com clara separação de responsabilidades entre camadas. A arquitetura suporta desde deploy local (Docker Compose) até produção escalável (Kubernetes).

### Princípios Arquiteturais

1. **Separation of Concerns**: API, Business Logic, Data Access em camadas distintas
2. **Dependency Injection**: FastAPI deps para testabilidade
3. **Domain-Driven Design**: Services organizados por domínio (RAG, Chat, Analysis)
4. **API-First**: Contratos definidos com Pydantic antes da implementação
5. **Async by Default**: Operações I/O assíncronas quando possível
6. **Fail-Safe**: Graceful degradation se serviços externos falharem

---

## 🗂️ Estrutura de Diretórios Completa

```
netguru/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app + startup/shutdown
│   │   │
│   │   ├── api/                       # 🌐 API Layer
│   │   │   ├── __init__.py
│   │   │   ├── deps.py                # Dependências compartilhadas
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── router.py          # Agregador de routers
│   │   │       └── endpoints/
│   │   │           ├── __init__.py
│   │   │           ├── auth.py        # POST /auth/login, /register
│   │   │           ├── users.py       # GET /users/me, PATCH /users/me
│   │   │           ├── chat.py        # POST /chat/conversations, /messages
│   │   │           ├── files.py       # POST /files/upload, GET /files/{id}
│   │   │           ├── analysis.py    # POST /analysis/pcap, /config
│   │   │           ├── topology.py    # GET /topology/{id}
│   │   │           └── websocket.py   # WS /ws/chat/{conversation_id}
│   │   │
│   │   ├── core/                      # ⚙️ Core Configuration
│   │   │   ├── __init__.py
│   │   │   ├── config.py              # Pydantic Settings
│   │   │   ├── security.py            # JWT, password hashing
│   │   │   └── logging.py             # Structured logging setup
│   │   │
│   │   ├── models/                    # 🗄️ SQLAlchemy ORM Models
│   │   │   ├── __init__.py
│   │   │   ├── base.py                # Base class
│   │   │   ├── user.py                # User, APIKey
│   │   │   ├── conversation.py        # Conversation, Message
│   │   │   ├── document.py            # Document, Embedding
│   │   │   ├── analysis.py            # AnalysisTask, TopologySnapshot
│   │   │   └── mixins.py              # TimestampMixin, SoftDeleteMixin
│   │   │
│   │   ├── schemas/                   # 📋 Pydantic Schemas (DTO)
│   │   │   ├── __init__.py
│   │   │   ├── user.py                # UserCreate, UserResponse, UserUpdate
│   │   │   ├── auth.py                # Token, LoginRequest
│   │   │   ├── chat.py                # ConversationCreate, MessageCreate
│   │   │   ├── file.py                # FileUpload, FileMetadata
│   │   │   ├── analysis.py            # PCAPAnalysisRequest, TaskStatus
│   │   │   └── common.py              # GenericResponse, PaginatedResponse
│   │   │
│   │   ├── services/                  # 🧠 Business Logic
│   │   │   ├── __init__.py
│   │   │   ├── user_service.py        # User CRUD + API key management
│   │   │   ├── auth_service.py        # Login, token generation
│   │   │   ├── chat_service.py        # Conversation orchestration
│   │   │   │
│   │   │   ├── rag/                   # RAG Subsystem
│   │   │   │   ├── __init__.py
│   │   │   │   ├── embeddings.py      # Embedding generation
│   │   │   │   ├── global_rag.py      # Search in curated docs
│   │   │   │   ├── local_rag.py       # Search in user docs
│   │   │   │   └── chunking.py        # Document splitting strategies
│   │   │   │
│   │   │   ├── llm/                   # LLM Integration
│   │   │   │   ├── __init__.py
│   │   │   │   ├── provider.py        # Abstract LLM Provider
│   │   │   │   ├── openai_provider.py
│   │   │   │   ├── anthropic_provider.py
│   │   │   │   └── agent_service.py   # LangChain orchestration
│   │   │   │
│   │   │   ├── file_service.py        # Upload handling, validation
│   │   │   ├── pcap_analyzer.py       # PCAP parsing (scapy)
│   │   │   ├── config_parser.py       # Cisco/Juniper config parsing
│   │   │   └── topology_builder.py    # CDP/LLDP → Graph
│   │   │
│   │   ├── db/                        # 🔌 Database
│   │   │   ├── __init__.py
│   │   │   ├── session.py             # SQLAlchemy session factory
│   │   │   ├── base.py                # Declarative base
│   │   │   └── redis.py               # Redis client + helpers
│   │   │
│   │   ├── middleware/                # 🚦 Middleware
│   │   │   ├── __init__.py
│   │   │   ├── error_handler.py       # Global exception handler
│   │   │   ├── rate_limiter.py        # Redis-based rate limiting
│   │   │   └── request_logger.py      # Request/response logging
│   │   │
│   │   ├── workers/                   # 👷 Celery Workers
│   │   │   ├── __init__.py
│   │   │   ├── celery_app.py          # Celery config
│   │   │   └── tasks/
│   │   │       ├── __init__.py
│   │   │       ├── pcap_tasks.py      # analyze_pcap task
│   │   │       ├── rag_tasks.py       # generate_embeddings task
│   │   │       └── topology_tasks.py  # build_topology task
│   │   │
│   │   └── utils/                     # 🔧 Utilities
│   │       ├── __init__.py
│   │       ├── validators.py          # Custom Pydantic validators
│   │       ├── file_helpers.py        # File I/O helpers
│   │       └── network_utils.py       # IP validation, subnet calc
│   │
│   ├── tests/                         # 🧪 Tests
│   │   ├── __init__.py
│   │   ├── conftest.py                # Pytest fixtures
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   │
│   ├── alembic/                       # 🔄 Database Migrations
│   │   ├── versions/
│   │   ├── env.py
│   │   └── README
│   │
│   ├── scripts/                       # 📜 Utility Scripts
│   │   ├── ingest_cisco_docs.py       # Populate RAG Global
│   │   └── create_superuser.py
│   │
│   ├── .env.example                   # Environment variables template
│   ├── requirements.txt               # Python dependencies
│   ├── requirements-dev.txt           # Dev dependencies
│   ├── Dockerfile
│   ├── alembic.ini
│   └── pyproject.toml                 # Poetry/Ruff config
│
├── frontend/
│   ├── public/
│   │   └── favicon.ico
│   │
│   ├── src/
│   │   ├── main.tsx                   # Entry point
│   │   ├── App.tsx                    # Root component + routing
│   │   │
│   │   ├── components/                # 🧩 Reusable Components
│   │   │   ├── layout/
│   │   │   │   ├── Header.tsx
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   └── Footer.tsx
│   │   │   ├── chat/
│   │   │   │   ├── ChatWindow.tsx
│   │   │   │   ├── MessageBubble.tsx
│   │   │   │   ├── ChatInput.tsx
│   │   │   │   └── ConversationsList.tsx
│   │   │   ├── files/
│   │   │   │   ├── FileUpload.tsx
│   │   │   │   ├── FileList.tsx
│   │   │   │   └── FilePreview.tsx
│   │   │   ├── topology/
│   │   │   │   ├── TopologyGraph.tsx  # React Flow
│   │   │   │   └── NodeDetails.tsx
│   │   │   └── common/
│   │   │       ├── Button.tsx
│   │   │       ├── Input.tsx
│   │   │       ├── Modal.tsx
│   │   │       └── Spinner.tsx
│   │   │
│   │   ├── pages/                     # 📄 Page Components
│   │   │   ├── Login.tsx
│   │   │   ├── Register.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Chat.tsx
│   │   │   ├── Files.tsx
│   │   │   ├── Topology.tsx
│   │   │   └── Settings.tsx
│   │   │
│   │   ├── services/                  # 🔌 API Layer
│   │   │   ├── api.ts                 # Axios instance + interceptors
│   │   │   ├── websocket.ts           # WebSocket client
│   │   │   ├── auth.service.ts
│   │   │   ├── chat.service.ts
│   │   │   ├── file.service.ts
│   │   │   └── topology.service.ts
│   │   │
│   │   ├── hooks/                     # 🎣 Custom React Hooks
│   │   │   ├── useAuth.ts
│   │   │   ├── useChat.ts
│   │   │   ├── useWebSocket.ts
│   │   │   └── useFileUpload.ts
│   │   │
│   │   ├── stores/                    # 🗃️ Zustand State
│   │   │   ├── authStore.ts
│   │   │   ├── chatStore.ts
│   │   │   └── uiStore.ts
│   │   │
│   │   ├── types/                     # 📝 TypeScript Types
│   │   │   ├── api.types.ts
│   │   │   ├── chat.types.ts
│   │   │   └── user.types.ts
│   │   │
│   │   ├── utils/                     # 🔧 Utilities
│   │   │   ├── formatters.ts
│   │   │   ├── validators.ts
│   │   │   └── constants.ts
│   │   │
│   │   └── styles/
│   │       └── globals.css            # Tailwind imports
│   │
│   ├── .env.example
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── Dockerfile
│
├── docs/                              # 📚 Documentation (este diretório)
├── docker-compose.yml                 # Local development stack
├── docker-compose.prod.yml            # Production stack
├── .github/
│   └── workflows/
│       ├── ci.yml                     # CI pipeline
│       └── cd.yml                     # CD pipeline
├── .gitignore
└── README.md
```

---

## 🏗️ Camadas da Aplicação

### 1. API Layer (`app/api/`)

**Responsabilidade:** Receber requisições HTTP/WebSocket, validar input, retornar responses.

**Componentes:**
- **Routers (endpoints/)**: Definem rotas e handlers
- **Dependencies (deps.py)**: Injeção de DB sessions, autenticação, rate limiting

**Exemplo de Endpoint:**
```python
# app/api/v1/endpoints/chat.py
from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_current_user, get_db
from app.schemas.chat import ConversationCreate, MessageCreate
from app.services.chat_service import ChatService

router = APIRouter()

@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    service = ChatService(db)
    return await service.create_conversation(user.id, data.title)
```

**Padrões:**
- Sempre usar `response_model` para documentação automática
- Exceptions são capturadas pelo middleware e convertidas em JSON
- WebSocket connections autenticadas via token no query param

---

### 2. Core Layer (`app/core/`)

**Responsabilidade:** Configurações globais e funcionalidades cross-cutting.

**config.py (Pydantic Settings):**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "NetGuru"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    
    # Database
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 100
    UPLOAD_DIR: str = "/var/uploads"
    
    class Config:
        env_file = ".env"

settings = Settings()
```

**security.py:**
- JWT encoding/decoding usando `python-jose`
- Password hashing com `passlib[bcrypt]`
- Token validation helpers

---

### 3. Models Layer (`app/models/`)

**Responsabilidade:** Definir estrutura das tabelas PostgreSQL (ORM).

**Exemplo (user.py):**
```python
from sqlalchemy import Column, String, Boolean, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
import uuid

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    plan_tier = Column(Enum("solo", "team", "enterprise"), default="solo")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    conversations = relationship("Conversation", back_populates="user")
    api_keys = relationship("APIKey", back_populates="user")
```

**Padrões:**
- UUIDs como PKs (segurança)
- Timestamps em UTC
- Soft deletes com `is_active`
- Índices em campos de busca frequente

---

### 4. Schemas Layer (`app/schemas/`)

**Responsabilidade:** Validação de input/output e serialização.

**Padrões de Nomenclatura:**
```python
# user.py
class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None

class UserCreate(UserBase):
    password: str = Field(min_length=8)

class UserUpdate(BaseModel):
    full_name: str | None = None
    # Sem email/password - requer endpoints separados

class UserInDB(UserBase):
    id: UUID4
    plan_tier: str
    is_active: bool
    created_at: datetime

class UserResponse(UserBase):
    id: UUID4
    plan_tier: str
    # Sem campos sensíveis
```

---

### 5. Services Layer (`app/services/`)

**Responsabilidade:** Business logic reutilizável e independente do framework.

**Princípios:**
- **No FastAPI dependencies dentro de services** (recebem DB session como argumento)
- **Retornam domain objects ou Dict**, não HTTP responses
- **Testáveis isoladamente** (unit tests)

**Exemplo (chat_service.py):**
```python
class ChatService:
    def __init__(self, db: AsyncSession, redis: Redis, llm_provider: LLMProvider):
        self.db = db
        self.redis = redis
        self.llm = llm_provider
    
    async def send_message(
        self, 
        conversation_id: UUID, 
        user_id: UUID, 
        content: str
    ) -> Message:
        # 1. Validate conversation ownership
        conv = await self._get_conversation(conversation_id, user_id)
        
        # 2. Retrieve context (RAG)
        context = await self.rag_service.retrieve(content, user_id)
        
        # 3. Call LLM
        response = await self.llm.generate(
            messages=await self._build_history(conversation_id),
            context=context
        )
        
        # 4. Save messages
        user_msg = await self._save_message(conversation_id, "user", content)
        assistant_msg = await self._save_message(conversation_id, "assistant", response)
        
        return assistant_msg
```

---

### 6. Database Layer (`app/db/`)

**session.py (AsyncSession Factory):**
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(settings.DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

**redis.py:**
```python
import redis.asyncio as aioredis

class RedisClient:
    def __init__(self):
        self.redis = None
    
    async def connect(self):
        self.redis = await aioredis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
        )
    
    async def get_cached(self, key: str) -> str | None:
        return await self.redis.get(key)
    
    async def set_cached(self, key: str, value: str, ttl: int = 3600):
        await self.redis.setex(key, ttl, value)
```

---

### 7. Workers Layer (`app/workers/`)

**Responsabilidade:** Processar tarefas assíncronas longas (>10s).

**celery_app.py:**
```python
from celery import Celery

celery_app = Celery(
    "netguru_workers",
    broker=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
    backend=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1"
)

celery_app.conf.task_routes = {
    "app.workers.tasks.pcap_tasks.*": {"queue": "pcap"},
    "app.workers.tasks.rag_tasks.*": {"queue": "rag"},
}
```

**tasks/pcap_tasks.py:**
```python
from app.workers.celery_app import celery_app
from app.services.pcap_analyzer import PCAPAnalyzer

@celery_app.task(bind=True, max_retries=3)
def analyze_pcap(self, file_path: str, user_id: str):
    try:
        analyzer = PCAPAnalyzer()
        result = analyzer.analyze(file_path)
        return {"status": "completed", "result": result}
    except Exception as exc:
        self.retry(exc=exc, countdown=60)
```

---

## 🔄 Fluxo de Dados: Chat com RAG

```
[Usuario]
   │ 1. WS: "Como configurar OSPF?"
   ↓
[Frontend - ChatWindow.tsx]
   │ 2. ws.send(JSON.stringify({content: "..."}))
   ↓
[Backend - websocket.py]
   │ 3. Valida JWT, extrai user_id
   ↓
[ChatService.send_message()]
   │ 4. Busca contexto no RAG
   ↓
[RAGService.retrieve()]
   │ 5. Embedding da query
   │ 6. pgvector similarity search
   │ 7. Retorna top-5 chunks relevantes
   ↓
[LLMProvider.generate()]
   │ 8. Monta prompt com contexto
   │ 9. Chama OpenAI API (chave do user)
   │ 10. Stream response tokens
   ↓
[websocket.py]
   │ 11. ws.send_text(token) em loop
   ↓
[Frontend]
   │ 12. Atualiza UI incrementalmente
   └─→ [Usuario vê resposta em tempo real]
```

---

## 🔐 Fluxo de Autenticação

```
1. POST /api/v1/auth/register
   → Cria user com password hash
   → Retorna user_id

2. POST /api/v1/auth/login
   → Valida email/password
   → Gera access_token (JWT, 1h) + refresh_token (7d)
   → Armazena refresh_token no Redis
   → Retorna tokens

3. GET /api/v1/users/me (Header: Authorization: Bearer <access_token>)
   → Middleware extrai token
   → Valida assinatura e expiration
   → Injeta user via Depends(get_current_user)

4. POST /api/v1/auth/refresh (Body: {refresh_token})
   → Valida refresh_token no Redis
   → Gera novo access_token
   → Invalida refresh_token antigo (one-time use)
```

---

## 📊 Decisões Arquiteturais

### ✅ Por que Monorepo?
- **Vantagem**: Sincronização de schemas entre backend/frontend
- **Vantagem**: CI/CD simplificado (um repositório)
- **Desvantagem**: Build times maiores (mitigado com cache Docker)

### ✅ Por que Celery?
- **Alternativas**: RQ, Dramatiq, ARQ
- **Escolha**: Celery - maduro, flower UI, retry policies robustas
- **Uso**: PCAP analysis (1-5 min), embedding generation (batch)

### ✅ Por que pgvector em vez de Pinecone?
- **MVP**: Simplicidade operacional, menos dependências externas
- **Limitação**: Performance em >1M vectors (suficiente para 10k docs)
- **Migração futura**: Qdrant/Weaviate se necessário

### ✅ Por que WebSocket em vez de SSE?
- **Vantagem WS**: Bidirecional (user pode cancelar geração)
- **Vantagem WS**: Suporte nativo no FastAPI
- **Desvantagem**: Mais complexo que polling

### ✅ Por que Zustand em vez de Redux?
- **Vantagem**: Menos boilerplate (~90% menos código)
- **Vantagem**: Performance superior (subscriptions granulares)
- **Suficiente para**: MVP e escala média

---

## 🚀 Próximos Passos

1. Revise [02-database-design.md](02-database-design.md) para schema detalhado
2. Estude [03-api-specification.md](03-api-specification.md) para contratos de API
3. Configure ambiente com [06-phase1-foundation.md](06-phase1-foundation.md)

---

**Configuração Local:** Ver [00-overview.md](00-overview.md#quick-start) para instruções de setup.
