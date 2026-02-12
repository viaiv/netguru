# API Specification - NetGuru Platform

**Versão:** 1.0  
**Data:** Fevereiro 2026  
**Base URL:** `http://localhost:8000/api/v1` (development)

---

## 🌐 Visão Geral

A API NetGuru segue princípios RESTful com:
- **Versionamento:** Prefixo `/api/v1/`
- **Autenticação:** JWT Bearer tokens
- **Formato:** JSON para request/response
- **Erros:** Códigos HTTP padronizados + mensagens descritivas
- **Rate Limiting:** Headers informativos
- **WebSocket:** Para chat em tempo real

---

## 🔐 Autenticação

### Fluxo de Autenticação

```
1. POST /auth/register → {user_id}
2. POST /auth/login → {access_token, refresh_token}
3. Requests subsequentes → Header: Authorization: Bearer {access_token}
4. Token expira → POST /auth/refresh → {new_access_token}
```

### Headers Padrão

```http
Content-Type: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## 📋 Endpoints

### Authentication (`/auth`)

#### POST `/auth/register`

Registra novo usuário.

**Request:**
```json
{
  "email": "engineer@example.com",
  "password": "SecureP@ss123",
  "full_name": "João Silva"
}
```

**Response:** `201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "engineer@example.com",
  "full_name": "João Silva",
  "plan_tier": "solo",
  "created_at": "2026-02-12T10:30:00Z"
}
```

**Erros:**
- `400`: Email inválido ou senha fraca (<8 chars)
- `409`: Email já cadastrado

---

#### POST `/auth/login`

Autentica usuário e retorna tokens.

**Request:**
```json
{
  "email": "engineer@example.com",
  "password": "SecureP@ss123"
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "refresh_abc123def456",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Erros:**
- `401`: Credenciais inválidas
- `403`: Conta desativada

---

#### POST `/auth/refresh`

Renova access token usando refresh token.

**Request:**
```json
{
  "refresh_token": "refresh_abc123def456"
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Comportamento:**
- Refresh token é invalidado (one-time use)
- Novo refresh token **não** é emitido (usar login se refresh expirou)

**Erros:**
- `401`: Refresh token inválido ou expirado

---

### Users (`/users`)

#### GET `/users/me`

Retorna perfil do usuário autenticado.

**Headers:** `Authorization: Bearer {token}` (obrigatório)

**Response:** `200 OK`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "engineer@example.com",
  "full_name": "João Silva",
  "plan_tier": "solo",
  "is_active": true,
  "created_at": "2026-02-12T10:30:00Z"
}
```

---

#### PATCH `/users/me`

Atualiza perfil do usuário.

**Request:**
```json
{
  "full_name": "João Pedro Silva"
}
```

**Response:** `200 OK`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "engineer@example.com",
  "full_name": "João Pedro Silva",
  "plan_tier": "solo",
  "updated_at": "2026-02-12T11:00:00Z"
}
```

---

#### GET `/users/me/api-keys`

Lista API keys de LLM providers do usuário.

**Response:** `200 OK`
```json
{
  "api_keys": [
    {
      "id": "key-uuid-1",
      "provider": "openai",
      "key_name": "Minha Chave OpenAI",
      "is_active": true,
      "last_used_at": "2026-02-12T09:00:00Z",
      "created_at": "2026-02-10T14:00:00Z"
    },
    {
      "id": "key-uuid-2",
      "provider": "anthropic",
      "key_name": "Claude Key",
      "is_active": true,
      "last_used_at": null,
      "created_at": "2026-02-11T16:30:00Z"
    }
  ]
}
```

**Nota:** Chaves **nunca** são retornadas plaintext.

---

#### POST `/users/me/api-keys`

Adiciona nova API key.

**Request:**
```json
{
  "provider": "openai",
  "api_key": "sk-proj-abc123...",
  "key_name": "Produção OpenAI"
}
```

**Response:** `201 Created`
```json
{
  "id": "key-uuid-3",
  "provider": "openai",
  "key_name": "Produção OpenAI",
  "is_active": true,
  "created_at": "2026-02-12T11:15:00Z"
}
```

**Validação Backend:**
- Faz teste de conexão com provider antes de salvar
- Encrypta key com Fernet

**Erros:**
- `400`: API key inválida (testada no provider)
- `409`: Key com mesmo nome já existe

---

#### DELETE `/users/me/api-keys/{key_id}`

Remove API key.

**Response:** `204 No Content`

---

### Chat (`/chat`)

#### POST `/chat/conversations`

Cria nova conversa.

**Request:**
```json
{
  "title": "Troubleshooting OSPF" 
}
```

**Response:** `201 Created`
```json
{
  "id": "conv-uuid-123",
  "title": "Troubleshooting OSPF",
  "user_id": "user-uuid",
  "created_at": "2026-02-12T11:20:00Z"
}
```

**Título Auto-gerado:**
- Se `title` omitido, primeira mensagem é enviada ao LLM para gerar título

---

#### GET `/chat/conversations`

Lista conversas do usuário (paginado).

**Query Params:**
- `page` (default: 1)
- `limit` (default: 20, max: 100)

**Response:** `200 OK`
```json
{
  "conversations": [
    {
      "id": "conv-uuid-123",
      "title": "OSPF Configuration",
      "message_count": 12,
      "last_message_at": "2026-02-12T10:45:00Z",
      "created_at": "2026-02-11T09:00:00Z"
    },
    {
      "id": "conv-uuid-456",
      "title": "PCAP Analysis - Latency Issues",
      "message_count": 5,
      "last_message_at": "2026-02-10T14:30:00Z",
      "created_at": "2026-02-10T14:00:00Z"
    }
  ],
  "pagination": {
    "total": 47,
    "page": 1,
    "pages": 3,
    "limit": 20
  }
}
```

---

#### GET `/chat/conversations/{conversation_id}`

Retorna detalhes da conversa + mensagens.

**Response:** `200 OK`
```json
{
  "id": "conv-uuid-123",
  "title": "OSPF Configuration",
  "user_id": "user-uuid",
  "created_at": "2026-02-11T09:00:00Z",
  "messages": [
    {
      "id": "msg-uuid-1",
      "role": "user",
      "content": "Como configurar OSPF em um router Cisco?",
      "created_at": "2026-02-11T09:05:00Z"
    },
    {
      "id": "msg-uuid-2",
      "role": "assistant",
      "content": "Para configurar OSPF em um router Cisco...",
      "tokens_used": 245,
      "metadata": {
        "retrieved_docs": ["cisco_ospf_guide.pdf:chunk_12"],
        "latency_ms": 1234
      },
      "created_at": "2026-02-11T09:05:03Z"
    }
  ]
}
```

---

#### POST `/chat/conversations/{conversation_id}/messages`

Envia mensagem (alternativa ao WebSocket para clients sem WS).

**Request:**
```json
{
  "content": "Qual a diferença entre OSPF e EIGRP?",
  "stream": false
}
```

**Response (stream=false):** `201 Created`
```json
{
  "id": "msg-uuid-3",
  "role": "assistant",
  "content": "OSPF é um protocolo de roteamento link-state...",
  "tokens_used": 312,
  "created_at": "2026-02-12T11:25:05Z"
}
```

**Response (stream=true):** `200 OK` (Server-Sent Events)
```
data: {"type": "token", "content": "OSPF"}

data: {"type": "token", "content": " é"}

data: {"type": "token", "content": " um"}

data: {"type": "done", "message_id": "msg-uuid-3", "tokens_used": 312}
```

**Erros:**
- `404`: Conversation não encontrada
- `403`: User não é dono da conversation
- `429`: Rate limit excedido

---

#### DELETE `/chat/conversations/{conversation_id}`

Deleta conversa e todas as mensagens.

**Response:** `204 No Content`

---

### WebSocket (`/ws`)

#### WS `/ws/chat/{conversation_id}`

Conexão WebSocket para chat em tempo real.

**Autenticação:** Query param `?token={access_token}`

**Client → Server Messages:**
```json
{
  "type": "message",
  "content": "Como analisar um PCAP no Wireshark?"
}
```

```json
{
  "type": "cancel",
  "message_id": "msg-uuid-4"
}
```

**Server → Client Messages:**
```json
{
  "type": "message_start",
  "message_id": "msg-uuid-4",
  "timestamp": "2026-02-12T11:30:00Z"
}
```

```json
{
  "type": "token",
  "content": "Para",
  "message_id": "msg-uuid-4"
}
```

```json
{
  "type": "message_end",
  "message_id": "msg-uuid-4",
  "tokens_used": 421,
  "timestamp": "2026-02-12T11:30:04Z"
}
```

```json
{
  "type": "error",
  "error": "LLM API key inválida ou expirada",
  "code": "LLM_AUTH_ERROR"
}
```

**Comportamento:**
- Conexão permanece aberta (keep-alive ping/pong a cada 30s)
- Múltiplas mensagens podem ser enviadas sequencialmente
- Servidor fecha conexão se token expirar (client deve reconectar)

---

### Files (`/files`)

#### POST `/files/upload`

Upload de arquivos (configs, logs, PCAP).

**Request:** `multipart/form-data`
```
POST /api/v1/files/upload
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="router_config.txt"
Content-Type: text/plain

router ospf 1
 network 10.0.0.0 0.255.255.255 area 0
!
------WebKitFormBoundary
Content-Disposition: form-data; name="file_type"

config
------WebKitFormBoundary--
```

**Response:** `201 Created`
```json
{
  "id": "file-uuid-789",
  "filename": "router_config.txt",
  "file_type": "config",
  "file_size_bytes": 2048,
  "status": "uploaded",
  "created_at": "2026-02-12T11:35:00Z"
}
```

**Validações:**
- Extensão permitida (`.txt`, `.conf`, `.log`, `.pcap`, `.cap`)
- Tamanho máximo: 100MB (configurável por plan_tier)
- Magic bytes verification (não apenas extensão)

**Triggers:**
- `file_type='pcap'` → Dispara Celery task `analyze_pcap`
- `file_type='config'` → Ingere no RAG Local (embeddings)

---

#### GET `/files`

Lista arquivos do usuário.

**Query Params:**
- `file_type` (opcional): Filtra por tipo
- `page`, `limit`

**Response:** `200 OK`
```json
{
  "files": [
    {
      "id": "file-uuid-789",
      "filename": "router_config.txt",
      "file_type": "config",
      "file_size_bytes": 2048,
      "status": "completed",
      "created_at": "2026-02-12T11:35:00Z",
      "processed_at": "2026-02-12T11:35:15Z"
    }
  ],
  "pagination": {
    "total": 23,
    "page": 1,
    "pages": 2,
    "limit": 20
  }
}
```

---

#### GET `/files/{file_id}`

Retorna metadata + download URL.

**Response:** `200 OK`
```json
{
  "id": "file-uuid-789",
  "filename": "router_config.txt",
  "original_filename": "router_config.txt",
  "file_type": "config",
  "file_size_bytes": 2048,
  "status": "completed",
  "download_url": "/api/v1/files/file-uuid-789/download",
  "metadata": {
    "vendor": "cisco",
    "chunks_created": 3
  },
  "created_at": "2026-02-12T11:35:00Z",
  "processed_at": "2026-02-12T11:35:15Z"
}
```

---

#### GET `/files/{file_id}/download`

Download do arquivo original.

**Response:** `200 OK`
```
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="router_config.txt"

[conteúdo do arquivo]
```

---

#### DELETE `/files/{file_id}`

Deleta arquivo + embeddings associados.

**Response:** `204 No Content`

---

### Analysis (`/analysis`)

#### POST `/analysis/pcap`

Inicia análise de PCAP (Celery task assíncrona).

**Request:**
```json
{
  "file_id": "file-uuid-pcap-1",
  "analysis_type": "latency" 
}
```

**Tipos de análise:**
- `latency`: Análise de delays TCP
- `retransmissions`: Conta retransmissões
- `full`: Análise completa

**Response:** `202 Accepted`
```json
{
  "task_id": "task-uuid-123",
  "status": "pending",
  "estimated_duration_seconds": 120,
  "created_at": "2026-02-12T11:40:00Z"
}
```

---

#### GET `/analysis/tasks/{task_id}`

Polling de status da análise.

**Response (running):** `200 OK`
```json
{
  "task_id": "task-uuid-123",
  "status": "running",
  "progress": 45,
  "started_at": "2026-02-12T11:40:05Z"
}
```

**Response (completed):** `200 OK`
```json
{
  "task_id": "task-uuid-123",
  "status": "completed",
  "result": {
    "total_packets": 15234,
    "retransmissions": 42,
    "avg_latency_ms": 23.4,
    "top_talkers": [
      {"ip": "10.0.0.1", "packets": 5432},
      {"ip": "10.0.0.2", "packets": 3210}
    ]
  },
  "completed_at": "2026-02-12T11:42:15Z"
}
```

**Response (failed):** `200 OK`
```json
{
  "task_id": "task-uuid-123",
  "status": "failed",
  "error_message": "Invalid PCAP format",
  "completed_at": "2026-02-12T11:40:30Z"
}
```

---

#### POST `/analysis/config-validation`

Valida configuração contra Golden Config.

**Request:**
```json
{
  "file_id": "file-uuid-config-1",
  "golden_config_id": "golden-uuid-1" 
}
```

**Response:** `200 OK`
```json
{
  "is_valid": false,
  "violations": [
    {
      "severity": "error",
      "line": 15,
      "message": "SNMP community string usando 'public' (inseguro)",
      "recommendation": "Use string complexa ou SNMPv3"
    },
    {
      "severity": "warning",
      "line": 23,
      "message": "Interface Gi0/1 sem descrição",
      "recommendation": "Adicione: description 'Link para Switch Core'"
    }
  ]
}
```

---

### Topology (`/topology`)

#### POST `/topology/generate`

Gera topologia a partir de configs.

**Request:**
```json
{
  "file_ids": ["file-uuid-1", "file-uuid-2", "file-uuid-3"],
  "layout": "hierarchical"
}
```

**Layouts:** `hierarchical`, `force-directed`, `circular`

**Response:** `201 Created`
```json
{
  "id": "topology-uuid-456",
  "title": "Topologia - 2026-02-12",
  "graph_data": {
    "nodes": [
      {
        "id": "r1",
        "type": "router",
        "data": {
          "label": "Router-Core-1",
          "ip": "10.0.0.1",
          "model": "Cisco ISR 4451"
        },
        "position": {"x": 250, "y": 0}
      },
      {
        "id": "s1",
        "type": "switch",
        "data": {
          "label": "Switch-Access-1",
          "ip": "10.0.1.10",
          "model": "Cisco 2960X"
        },
        "position": {"x": 100, "y": 200}
      }
    ],
    "edges": [
      {
        "id": "e1",
        "source": "r1",
        "target": "s1",
        "label": "Gi0/0/1 → Port1",
        "data": {"speed": "1Gbps"}
      }
    ]
  },
  "metadata": {
    "total_devices": 2,
    "vendors": ["cisco"],
    "device_types": {"router": 1, "switch": 1}
  },
  "created_at": "2026-02-12T11:50:00Z"
}
```

---

#### GET `/topology/{topology_id}`

Retorna topologia salva.

**Response:** `200 OK` (mesmo formato do POST acima)

---

#### GET `/topology`

Lista topologias do usuário.

**Response:** `200 OK`
```json
{
  "topologies": [
    {
      "id": "topology-uuid-456",
      "title": "Topologia - 2026-02-12",
      "device_count": 2,
      "created_at": "2026-02-12T11:50:00Z"
    }
  ],
  "pagination": {...}
}
```

---

## ⚠️ Códigos de Erro

### HTTP Status Codes

| Código | Significado | Uso |
|--------|-------------|-----|
| `200` | OK | Request sucesso |
| `201` | Created | Recurso criado (POST) |
| `204` | No Content | Deleção sucesso |
| `400` | Bad Request | Validação falhou |
| `401` | Unauthorized | Token ausente/inválido |
| `403` | Forbidden | Sem permissão |
| `404` | Not Found | Recurso não existe |
| `409` | Conflict | Duplicata (email, etc) |
| `422` | Unprocessable Entity | Schema inválido |
| `429` | Too Many Requests | Rate limit |
| `500` | Internal Server Error | Erro do servidor |
| `503` | Service Unavailable | Manutenção |

### Formato de Erro

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "O campo 'email' é obrigatório",
    "details": {
      "field": "email",
      "constraint": "required"
    }
  }
}
```

**Códigos de Erro Customizados:**
- `VALIDATION_ERROR`: Input inválido
- `AUTH_ERROR`: Autenticação falhou
- `LLM_AUTH_ERROR`: API key de LLM inválida
- `RATE_LIMIT_EXCEEDED`: Muitas requests
- `FILE_TOO_LARGE`: Upload excede limite
- `INSUFFICIENT_QUOTA`: Plano não permite feature

---

## 📊 Rate Limiting

### Headers de Response

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1709827260
```

### Limites por Plano

| Endpoint | Solo | Team | Enterprise |
|----------|------|------|------------|
| `POST /chat/messages` | 100/min | 500/min | 2000/min |
| `POST /files/upload` | 10/hour | 50/hour | 200/hour |
| `POST /analysis/*` | 5/hour | 20/hour | 100/hour |

**Response ao exceder:**
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Limite de 100 requests/min excedido",
    "retry_after": 45
  }
}
```

---

## 🔍 Paginação

### Query Params Padrão

- `page`: Número da página (começa em 1)
- `limit`: Itens por página (default: 20, max: 100)

### Response Padrão

```json
{
  "items": [...],
  "pagination": {
    "total": 234,
    "page": 2,
    "pages": 12,
    "limit": 20,
    "has_next": true,
    "has_prev": true
  }
}
```

---

## 🧪 Testando a API

### cURL Examples

**Login:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "pass123"}'
```

**Criar Conversa:**
```bash
curl -X POST http://localhost:8000/api/v1/chat/conversations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Conversation"}'
```

**Upload de Arquivo:**
```bash
curl -X POST http://localhost:8000/api/v1/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@router_config.txt" \
  -F "file_type=config"
```

---

### Postman Collection

**Disponível em:** `/docs/postman/netguru-api.json`

Importe no Postman para ter todos os endpoints configurados.

---

## 📖 Documentação Interativa

### Swagger UI

Acesse: `http://localhost:8000/docs`

Documentação auto-gerada com FastAPI, permite testar endpoints diretamente no navegador.

### ReDoc

Acesse: `http://localhost:8000/redoc`

Versão alternativa mais limpa da documentação.

---

## 🔄 Versionamento

### Estratégia

- **v1** (atual): `/api/v1/*` - MVP e features core
- **v2** (futuro): `/api/v2/*` - Breaking changes

### Breaking Changes

Mudanças que quebram compatibilidade (requerem nova versão):
- Remoção de campos em responses
- Mudança de tipos (string → int)
- Mudança de URLs

### Non-Breaking Changes

Podem ser feitas na mesma versão:
- Adição de campos opcionais
- Novos endpoints
- Novos query params opcionais

---

## 🗺️ Próximos Passos

1. Revise [04-security-model.md](04-security-model.md) para implementação de autenticação
2. Consulte [05-rag-implementation.md](05-rag-implementation.md) para detalhes de chat
3. Implemente com [06-phase1-foundation.md](06-phase1-foundation.md)

---

**Ver também:** [02-database-design.md](02-database-design.md) para schemas de dados.
