# Database Design - NetGuru Platform

**Versão:** 1.0  
**Data:** Fevereiro 2026

---

## 🗄️ Visão Geral

O NetGuru utiliza dois sistemas de armazenamento complementares:

- **PostgreSQL 15+**: Dados persistentes estruturados + embeddings (pgvector)
- **Redis 7+**: Cache, sessions, rate limiting, Celery queue

---

## 📊 Schema PostgreSQL

### Extensões Necessárias

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";
```

---

### Tabela: `users`

Armazena usuários da plataforma.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    plan_tier VARCHAR(20) NOT NULL DEFAULT 'solo' CHECK (plan_tier IN ('solo', 'team', 'enterprise')),
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_plan_tier ON users(plan_tier) WHERE is_active = TRUE;
```

**Colunas:**
- `id`: UUID para segurança (não sequencial)
- `email`: Login único
- `hashed_password`: bcrypt hash (nunca plaintext)
- `plan_tier`: Define features disponíveis e rate limits
- `is_active`: Soft delete (permite histórico)

---

### Tabela: `api_keys`

Armazena API keys de LLM providers dos usuários (encrypted).

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL CHECK (provider IN ('openai', 'anthropic', 'azure', 'local')),
    encrypted_key TEXT NOT NULL,
    key_name VARCHAR(100), -- User-friendly label
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    
    UNIQUE(user_id, provider, key_name)
);

CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_active ON api_keys(user_id, is_active) WHERE is_active = TRUE;
```

**Segurança:**
- `encrypted_key`: Usar Fernet (cryptography lib) ou AWS Secrets Manager
- Suportar rotação (múltiplas keys ativas por user)
- TTL opcional via `expires_at`

---

### Tabela: `conversations`

Representa uma sessão de chat.

```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL DEFAULT 'Nova Conversa',
    model_used VARCHAR(100), -- Ex: "gpt-4-turbo", "claude-3-opus"
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_updated_at ON conversations(updated_at DESC);
```

**Comportamento:**
- Título auto-gerado a partir da primeira mensagem (via LLM)
- `updated_at` atualizado a cada nova mensagem (para ordenação recente)

---

### Tabela: `messages`

Mensagens dentro de conversas.

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    tokens_used INTEGER, -- Para billing tracking
    metadata JSONB, -- Ex: {"retrieved_docs": ["doc1", "doc2"], "latency_ms": 1234}
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);
```

**Otimizações:**
- `metadata`: Armazena contexto RAG usado, latência, etc (analytics)
- Índice por conversation + timestamp para retrieval rápido

---

### Tabela: `documents`

Arquivos uploaded pelos usuários (configs, logs, PCAPs).

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL, -- 'pcap', 'config', 'log', 'pdf'
    file_size_bytes BIGINT NOT NULL,
    storage_path TEXT NOT NULL, -- S3 URL ou filesystem path
    mime_type VARCHAR(100),
    status VARCHAR(20) DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'processing', 'completed', 'failed')),
    metadata JSONB, -- Ex: {"vendor": "cisco", "device_type": "router"}
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_type ON documents(file_type);
CREATE INDEX idx_documents_status ON documents(status) WHERE status != 'completed';
```

**Workflow:**
1. Upload → status='uploaded'
2. Celery task inicia → status='processing'
3. Completa → status='completed', `processed_at` set
4. Erro → status='failed', metadata inclui erro

---

### Tabela: `embeddings`

Vetores para RAG (Global + Local).

```sql
CREATE TABLE embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE, -- NULL para RAG Global
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE, -- NULL para docs curados
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding vector(384), -- Dimensão depende do modelo (all-MiniLM-L6-v2 = 384)
    metadata JSONB, -- Ex: {"page": 5, "section": "OSPF Configuration"}
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_embeddings_user_id ON embeddings(user_id);
CREATE INDEX idx_embeddings_document_id ON embeddings(document_id);

-- Índice de similaridade vetorial (HNSW = rápido)
CREATE INDEX idx_embeddings_vector ON embeddings USING hnsw (embedding vector_cosine_ops);
```

**Estratégia de Busca:**
```sql
-- RAG Global (user_id IS NULL)
SELECT chunk_text, (embedding <=> query_vector) AS distance
FROM embeddings
WHERE user_id IS NULL
ORDER BY distance
LIMIT 5;

-- RAG Local (filtrado por user)
SELECT chunk_text, (embedding <=> query_vector) AS distance
FROM embeddings
WHERE user_id = 'user-uuid-here'
ORDER BY distance
LIMIT 5;
```

---

### Tabela: `analysis_tasks`

Rastrear tarefas assíncronas (Celery).

```sql
CREATE TABLE analysis_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    task_type VARCHAR(50) NOT NULL, -- 'pcap_analysis', 'topology_generation', 'config_validation'
    celery_task_id VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    result JSONB, -- Output do análise
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_analysis_tasks_user_id ON analysis_tasks(user_id);
CREATE INDEX idx_analysis_tasks_celery_id ON analysis_tasks(celery_task_id);
CREATE INDEX idx_analysis_tasks_status ON analysis_tasks(status) WHERE status IN ('pending', 'running');
```

**Polling Pattern:**
Frontend faz polling em `GET /api/v1/analysis/tasks/{id}` até `status='completed'`.

---

### Tabela: `topology_snapshots`

Snapshots de topologia de rede gerados.

```sql
CREATE TABLE topology_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    graph_data JSONB NOT NULL, -- Ex: {"nodes": [...], "edges": [...]}
    metadata JSONB, -- Ex: {"total_devices": 15, "vendors": ["cisco", "juniper"]}
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_topology_user_id ON topology_snapshots(user_id);
```

**Graph Data Format (React Flow compatible):**
```json
{
  "nodes": [
    {"id": "r1", "type": "router", "data": {"label": "Router-1", "ip": "10.0.0.1"}},
    {"id": "s1", "type": "switch", "data": {"label": "Switch-1", "ip": "10.0.0.10"}}
  ],
  "edges": [
    {"id": "e1", "source": "r1", "target": "s1", "label": "Gi0/1 - Port1"}
  ]
}
```

---

## 🔄 Relacionamentos (ER Diagram)

```
users 1────>* api_keys
  │
  ├────────>* conversations 1────>* messages
  │
  ├────────>* documents 1────>* embeddings
  │
  └────────>* analysis_tasks
      │
      └────────>* topology_snapshots
```

---

## ⚡ Redis Data Structures

### 1. Sessions

**Padrão:** `session:{user_id}`  
**Tipo:** Hash  
**TTL:** 24 horas  
**Dados:**
```redis
HSET session:550e8400-e29b-41d4-a716-446655440000
  "access_token" "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  "refresh_token" "refresh_abc123"
  "expires_at" "1709827200"
```

**Uso:**
- Validar tokens sem hit no PostgreSQL
- Invalidar sessões instantaneamente (logout)

---

### 2. Rate Limiting

**Padrão:** `ratelimit:{user_id}:{endpoint}`  
**Tipo:** String (counter)  
**TTL:** 60 segundos  

**Implementação (Fixed Window):**
```python
async def check_rate_limit(redis: Redis, user_id: str, endpoint: str, limit: int):
    key = f"ratelimit:{user_id}:{endpoint}"
    current = await redis.incr(key)
    
    if current == 1:
        await redis.expire(key, 60)  # Reset após 1 minuto
    
    if current > limit:
        raise HTTPException(429, "Rate limit exceeded")
```

**Limites por Plano:**
```python
RATE_LIMITS = {
    "solo": {"chat": 100, "upload": 10},
    "team": {"chat": 500, "upload": 50},
    "enterprise": {"chat": 2000, "upload": 200}
}
```

---

### 3. Cache de Conversas Recentes

**Padrão:** `cache:conversation:{conversation_id}`  
**Tipo:** List (últimas N mensagens)  
**TTL:** 1 hora  

**Uso:**
```python
# Cache hit evita query PostgreSQL
messages = await redis.lrange(f"cache:conversation:{conv_id}", 0, -1)
if not messages:
    messages = await db.query(Message).filter(...).all()
    await redis.lpush(f"cache:conversation:{conv_id}", *[m.json() for m in messages])
    await redis.expire(..., 3600)
```

---

### 4. Celery Task Queue

**Queues:**
- `celery:queue:pcap` - Análise de PCAP (worker dedicado)
- `celery:queue:rag` - Geração de embeddings
- `celery:queue:default` - Tarefas gerais

**Result Backend:**
- `celery:result:{task_id}` - Resultado da task (auto-expira em 24h)

---

### 5. WebSocket Pub/Sub

**Padrão:** `ws:conversation:{conversation_id}`  
**Tipo:** Pub/Sub Channel  

**Uso (Multi-instance Support):**
```python
# Backend instância 1 recebe mensagem do LLM
await redis.publish(
    f"ws:conversation:{conv_id}",
    json.dumps({"type": "message_chunk", "content": "texto..."})
)

# Backend instância 2 (subscribed) repassa para WebSocket
async for message in pubsub.listen():
    await websocket.send_text(message["data"])
```

**Benefício:** Load balancer pode rotear WS para qualquer instância.

---

## 🔧 Migrations (Alembic)

### Estrutura de Versões

```
alembic/versions/
├── 001_initial_schema.py           # Tabelas users, api_keys
├── 002_add_conversations.py        # Tabelas conversations, messages
├── 003_add_documents_embeddings.py # RAG tables + pgvector
├── 004_add_analysis_tasks.py       # Analysis tracking
└── 005_add_topology_snapshots.py   # Topology feature
```

### Exemplo de Migration

```python
# alembic/versions/001_initial_schema.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('plan_tier', sa.String(20), server_default='solo'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_users_email', 'users', ['email'])

def downgrade():
    op.drop_index('idx_users_email')
    op.drop_table('users')
```

### Comandos Úteis

```bash
# Criar nova migration
alembic revision --autogenerate -m "add topology snapshots"

# Aplicar migrations
alembic upgrade head

# Reverter última migration
alembic downgrade -1

# Ver histórico
alembic history
```

---

## 📈 Otimizações de Performance

### Índices Estratégicos

**Índices Parciais (economizam espaço):**
```sql
-- Apenas usuários ativos
CREATE INDEX idx_active_users ON users(id) WHERE is_active = TRUE;

-- Apenas tasks pendentes/running
CREATE INDEX idx_pending_tasks ON analysis_tasks(status) 
WHERE status IN ('pending', 'running');
```

**Índices Compostos (queries complexas):**
```sql
-- Busca de conversas por usuário + data
CREATE INDEX idx_conv_user_updated ON conversations(user_id, updated_at DESC);

-- Mensagens por conversa + ordem
CREATE INDEX idx_msg_conv_created ON messages(conversation_id, created_at);
```

---

### Connection Pooling (SQLAlchemy)

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,          # Conexões permanentes
    max_overflow=10,       # Conexões extras em pico
    pool_pre_ping=True,    # Testa conexão antes de usar
    pool_recycle=3600      # Recicla após 1h (evita stale connections)
)
```

---

### Cache Strategy

**Cache Hierarquico:**
```
1. Redis (1h TTL) → Conversas recentes, user profiles
2. PostgreSQL Query Cache
3. pgvector Index (HNSW)
```

**Invalidação:**
```python
async def create_message(conversation_id: UUID, content: str):
    message = await db_create_message(...)
    
    # Invalidar cache da conversa
    await redis.delete(f"cache:conversation:{conversation_id}")
    
    return message
```

---

## 🔍 Queries Comuns

### 1. Últimas Conversas do Usuário
```sql
SELECT c.id, c.title, c.updated_at, COUNT(m.id) as message_count
FROM conversations c
LEFT JOIN messages m ON m.conversation_id = c.id
WHERE c.user_id = $1
GROUP BY c.id
ORDER BY c.updated_at DESC
LIMIT 20;
```

### 2. Histórico de Mensagens para Context Window
```sql
SELECT role, content, created_at
FROM messages
WHERE conversation_id = $1
ORDER BY created_at ASC
LIMIT 50; -- Últimas 50 mensagens
```

### 3. Busca Semântica RAG (Hybrid: Global + Local)
```sql
WITH global_results AS (
    SELECT chunk_text, (embedding <=> $1) AS distance, 'global' as source
    FROM embeddings
    WHERE user_id IS NULL
    ORDER BY distance
    LIMIT 3
),
local_results AS (
    SELECT chunk_text, (embedding <=> $1) AS distance, 'local' as source
    FROM embeddings
    WHERE user_id = $2
    ORDER BY distance
    LIMIT 2
)
SELECT * FROM global_results
UNION ALL
SELECT * FROM local_results
ORDER BY distance;
```

### 4. Usage Analytics (Token Consumption)
```sql
SELECT 
    DATE(created_at) as date,
    SUM(tokens_used) as total_tokens,
    COUNT(*) as message_count
FROM messages
WHERE conversation_id IN (
    SELECT id FROM conversations WHERE user_id = $1
)
GROUP BY DATE(created_at)
ORDER BY date DESC
LIMIT 30; -- Últimos 30 dias
```

---

## 🚨 Backup Strategy

### PostgreSQL

**Automated Daily Backups:**
```bash
# Cron job (3am daily)
0 3 * * * pg_dump -h localhost -U netguru -F c -b -v -f /backups/netguru_$(date +\%Y\%m\%d).backup netguru_db
```

**Retenção:**
- Diários: 7 dias
- Semanais: 4 semanas
- Mensais: 12 meses

**Restore:**
```bash
pg_restore -h localhost -U netguru -d netguru_db -v /backups/netguru_20260212.backup
```

---

### Redis (RDB + AOF)

**Configuração (redis.conf):**
```conf
# RDB snapshots
save 900 1      # 15 min se >= 1 key mudou
save 300 10     # 5 min se >= 10 keys
save 60 10000   # 1 min se >= 10k keys

# AOF (journal)
appendonly yes
appendfsync everysec
```

---

## 🔒 Segurança

### 1. Row-Level Security (RLS)

```sql
-- Usuários só acessam seus próprios dados
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_conversations_policy ON conversations
FOR ALL
TO authenticated_user
USING (user_id = current_setting('app.current_user_id')::uuid);
```

### 2. Encrypted Fields

**API Keys (Fernet Encryption):**
```python
from cryptography.fernet import Fernet

cipher = Fernet(settings.ENCRYPTION_KEY)

# Encrypt antes de salvar
encrypted = cipher.encrypt(api_key.encode())
await db.execute(
    "INSERT INTO api_keys (encrypted_key) VALUES ($1)",
    encrypted.decode()
)

# Decrypt para uso
decrypted = cipher.decrypt(encrypted_db_value.encode()).decode()
```

### 3. SQL Injection Prevention

**SEMPRE usar parametrized queries:**
```python
# ✅ CORRETO
await db.execute("SELECT * FROM users WHERE email = $1", user_email)

# ❌ ERRADO (SQL injection vulnerability)
await db.execute(f"SELECT * FROM users WHERE email = '{user_email}'")
```

---

## 📊 Monitoramento

### Key Metrics

**PostgreSQL:**
- Connection pool usage
- Slow queries (>100ms)
- Table bloat (vacuum effectiveness)
- Cache hit ratio (>95%)

**Redis:**
- Memory usage
- Evicted keys (should be 0)
- Commands/sec
- Keyspace hits rate

**Dashboard Query (Prometheus + Grafana):**
```sql
-- Slow queries (pg_stat_statements extension)
SELECT 
    query,
    calls,
    mean_exec_time,
    stddev_exec_time
FROM pg_stat_statements
WHERE mean_exec_time > 100
ORDER BY mean_exec_time DESC
LIMIT 10;
```

---

## 🗺️ Próximos Passos

1. Revise [03-api-specification.md](03-api-specification.md) para endpoints que consomem estes dados
2. Consulte [04-security-model.md](04-security-model.md) para implementação de encryption
3. Implemente com [06-phase1-foundation.md](06-phase1-foundation.md) - Sprint inicial

---

**Ver também:** [01-architecture.md](01-architecture.md) para contexto da arquitetura completa.
