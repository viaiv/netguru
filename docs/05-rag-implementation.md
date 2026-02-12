# RAG Implementation - NetGuru Platform

**Versão:** 1.0  
**Data:** Fevereiro 2026

---

## 🧠 Visão Geral do RAG

**RAG (Retrieval-Augmented Generation)** combina:
1. **Retrieval**: Busca em base de conhecimento
2. **Augmentation**: Enriquece prompt com contexto relevante
3. **Generation**: LLM gera resposta baseada no contexto

**NetGuru implementa Dual RAG:**
- **RAG Global**: Documentação curada de vendors (Cisco, Juniper, Arista)
- **RAG Local**: Documentos específicos do cliente (configs, topologias, tickets)

---

## 🎯 Arquitetura do RAG

```
[User Question: "Como configurar OSPF?"]
         ↓
[1. Embedding Generation]
   sentence-transformers → vector[384]
         ↓
[2. Dual Search]
   ├→ RAG Global (pgvector) → Top 3 chunks Cisco docs
   └→ RAG Local (pgvector) → Top 2 chunks user docs
         ↓
[3. Context Assembly]
   Combine chunks + format
         ↓
[4. LLM Call]
   Prompt template + context + user question
         ↓
[5. Streaming Response]
   Token-by-token via WebSocket
```

---

## 📚 RAG Global: Curadoria de Documentos

### Fontes de Conhecimento

**Vendors Suportados (MVP):**
- Cisco: Configuration Guides, Command References, Design Guides
- Juniper: Day One Books, TechLibrary
- Arista: EOS Manuals

**Formato:**
- PDF originais → Markdown (melhor para chunking)
- Estrutura preservada (headers, code blocks)

---

### Pipeline de Ingestão

**Script: `scripts/ingest_cisco_docs.py`**

```python
import os
from pathlib import Path
from langchain.document_loaders import PyMuPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from app.db.session import AsyncSessionLocal
from app.models.document import Embedding

# 1. Load PDF
loader = PyMuPDFLoader("docs/cisco_ospf_config_guide.pdf")
pages = loader.load()

# 2. Split into chunks
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n", "\n", " ", ""]
)
chunks = splitter.split_documents(pages)

# 3. Generate embeddings
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

async def ingest():
    async with AsyncSessionLocal() as db:
        for i, chunk in enumerate(chunks):
            # Generate vector
            vector = model.encode(chunk.page_content).tolist()
            
            # Save to DB
            embedding = Embedding(
                user_id=None,  # Global RAG
                document_id=None,
                chunk_text=chunk.page_content,
                chunk_index=i,
                embedding=vector,
                metadata={
                    "source": "cisco_ospf_config_guide.pdf",
                    "page": chunk.metadata.get("page"),
                    "vendor": "cisco"
                }
            )
            db.add(embedding)
        
        await db.commit()
        print(f"Ingested {len(chunks)} chunks")

if __name__ == "__main__":
    import asyncio
    asyncio.run(ingest())
```

---

### Estrutura de Metadata

```python
{
    "source": "cisco_ospf_config_guide.pdf",
    "vendor": "cisco",
    "product": "ios-xe",
    "category": "routing",
    "topic": "ospf",
    "page": 42,
    "section": "Area Configuration",
    "ingested_at": "2026-02-12T10:00:00Z"
}
```

**Benefícios:**
- Filtrar por vendor: "Apenas docs Cisco"
- Filtrar por categoria: "Routing protocols"
- Citação precisa: "Fonte: Cisco OSPF Guide, página 42"

---

## 🏠 RAG Local: Documentos do Cliente

### Upload e Processamento

**Fluxo:**
```
1. User uploads config file → POST /files/upload
2. File saved → Celery task triggered
3. Task:
   a. Parse file (detect vendor/device type)
   b. Split into chunks
   c. Generate embeddings
   d. Save to DB (user_id populated)
4. Status updated → "completed"
```

---

### Parsing de Config Files

**Exemplo: Cisco IOS Config**

```python
from typing import List, Dict
import re

class CiscoConfigParser:
    def parse(self, config_text: str) -> List[Dict]:
        """
        Retorna lista de blocos de config com metadata
        """
        sections = []
        current_section = []
        current_context = "global"
        
        for line in config_text.split('\n'):
            line = line.strip()
            
            # Detect interface sections
            if line.startswith('interface '):
                if current_section:
                    sections.append({
                        "context": current_context,
                        "content": '\n'.join(current_section)
                    })
                current_context = line
                current_section = [line]
            
            # Detect router sections
            elif line.startswith('router '):
                if current_section:
                    sections.append({
                        "context": current_context,
                        "content": '\n'.join(current_section)
                    })
                current_context = line
                current_section = [line]
            
            else:
                current_section.append(line)
        
        # Add last section
        if current_section:
            sections.append({
                "context": current_context,
                "content": '\n'.join(current_section)
            })
        
        return sections

# Uso
parser = CiscoConfigParser()
sections = parser.parse(config_content)

for section in sections:
    # Gerar embedding para cada seção
    vector = model.encode(section['content']).tolist()
    
    embedding = Embedding(
        user_id=user.id,  # Local RAG
        document_id=document.id,
        chunk_text=section['content'],
        embedding=vector,
        metadata={
            "context": section['context'],
            "vendor": "cisco",
            "file_type": "config"
        }
    )
```

---

### RAPTOR: Hierarchical Summarization

**RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval)** cria resumos em múltiplos níveis para logs extensos.

```python
from langchain.chains.summarize import load_summarize_chain
from langchain.chat_models import ChatOpenAI

async def generate_raptor_tree(chunks: List[str], llm: ChatOpenAI):
    """
    Cria árvore de resumos:
    Level 0: Chunks originais
    Level 1: Resumos de grupos de chunks
    Level 2: Resumo geral
    """
    embeddings_list = []
    
    # Level 0: Chunks originais
    for chunk in chunks:
        vector = model.encode(chunk).tolist()
        embeddings_list.append({
            "level": 0,
            "text": chunk,
            "vector": vector
        })
    
    # Level 1: Agrupar e resumir
    cluster_size = 5
    for i in range(0, len(chunks), cluster_size):
        group = chunks[i:i+cluster_size]
        
        # LLM summarize
        summary = await llm.summarize(group)
        vector = model.encode(summary).tolist()
        
        embeddings_list.append({
            "level": 1,
            "text": summary,
            "vector": vector,
            "source_chunks": list(range(i, min(i+cluster_size, len(chunks))))
        })
    
    # Level 2: Resumo geral
    all_level1 = [e['text'] for e in embeddings_list if e['level'] == 1]
    final_summary = await llm.summarize(all_level1)
    vector = model.encode(final_summary).tolist()
    
    embeddings_list.append({
        "level": 2,
        "text": final_summary,
        "vector": vector
    })
    
    return embeddings_list
```

**Quando usar:**
- Logs de troubleshooting extensos (>10k linhas)
- Show tech-support outputs
- Histórico de tickets

---

## 🔍 Retrieval: Vector Search

### Embedding Model

**Modelo:** `sentence-transformers/all-MiniLM-L6-v2`
- Dimensão: 384
- Velocidade: Rápido (~200 encode/sec em CPU)
- Qualidade: Boa para documentação técnica
- Multilingual: Sim (Português + Inglês)

**Alternativas:**
- `text-embedding-ada-002` (OpenAI): Melhor qualidade, custo por API
- `e5-large-v2`: Melhor qualidade, mais lento

---

### PostgreSQL pgvector Search

**Query de Similaridade:**
```sql
-- Cosine similarity (1 = idêntico, 0 = oposto)
SELECT 
    chunk_text,
    metadata,
    1 - (embedding <=> $1::vector) AS similarity
FROM embeddings
WHERE user_id IS NULL  -- RAG Global
ORDER BY embedding <=> $1::vector
LIMIT 5;
```

**Operadores pgvector:**
- `<=>` : Cosine distance (recomendado)
- `<->` : L2 distance (Euclidean)
- `<#>` : Inner product

---

### Hybrid Search: Global + Local

```python
async def retrieve_context(
    query: str,
    user_id: str,
    top_k_global: int = 3,
    top_k_local: int = 2
) -> List[Dict]:
    """
    Busca híbrida em RAG Global e Local
    """
    # Generate query embedding
    query_vector = model.encode(query).tolist()
    
    # Search RAG Global
    global_results = await db.execute(
        text("""
            SELECT chunk_text, metadata, 
                   1 - (embedding <=> :vector) AS similarity
            FROM embeddings
            WHERE user_id IS NULL
            ORDER BY embedding <=> :vector
            LIMIT :limit
        """),
        {"vector": query_vector, "limit": top_k_global}
    )
    
    # Search RAG Local
    local_results = await db.execute(
        text("""
            SELECT chunk_text, metadata,
                   1 - (embedding <=> :vector) AS similarity
            FROM embeddings
            WHERE user_id = :user_id
            ORDER BY embedding <=> :vector
            LIMIT :limit
        """),
        {"vector": query_vector, "user_id": user_id, "limit": top_k_local}
    )
    
    # Combine and sort by similarity
    all_results = []
    
    for row in global_results:
        all_results.append({
            "text": row.chunk_text,
            "source": "global",
            "similarity": row.similarity,
            "metadata": row.metadata
        })
    
    for row in local_results:
        all_results.append({
            "text": row.chunk_text,
            "source": "local",
            "similarity": row.similarity,
            "metadata": row.metadata
        })
    
    # Sort by similarity descending
    all_results.sort(key=lambda x: x['similarity'], reverse=True)
    
    return all_results[:5]  # Top 5 overall
```

---

### Reranking (Opcional - Fase 3)

Após retrieval inicial, usar modelo de reranking para melhorar ordem:

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

def rerank_results(query: str, results: List[Dict]) -> List[Dict]:
    """
    Reordena resultados usando cross-encoder
    """
    pairs = [(query, r['text']) for r in results]
    scores = reranker.predict(pairs)
    
    for i, result in enumerate(results):
        result['rerank_score'] = scores[i]
    
    results.sort(key=lambda x: x['rerank_score'], reverse=True)
    return results
```

---

## 🤖 LLM Integration: Provider Abstraction

### Abstract Provider Interface

```python
from abc import ABC, abstractmethod
from typing import AsyncGenerator

class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False
    ) -> str | AsyncGenerator[str, None]:
        pass
    
    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        pass

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str):
        import openai
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4-turbo-preview"
    
    async def generate(self, messages, stream=False):
        if stream:
            return self._stream_generate(messages)
        else:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content
    
    async def _stream_generate(self, messages):
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True
        )
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    async def count_tokens(self, text: str) -> int:
        import tiktoken
        encoding = tiktoken.encoding_for_model(self.model)
        return len(encoding.encode(text))

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = "claude-3-opus-20240229"
    
    async def generate(self, messages, stream=False):
        if stream:
            return self._stream_generate(messages)
        else:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=messages
            )
            return response.content[0].text
    
    async def _stream_generate(self, messages):
        async with self.client.messages.stream(
            model=self.model,
            max_tokens=4096,
            messages=messages
        ) as stream:
            async for text in stream.text_stream:
                yield text
```

---

### Provider Factory

```python
async def get_llm_provider(user_id: str, db: AsyncSession) -> LLMProvider:
    """
    Retorna provider baseado na API key do usuário
    """
    # Buscar API key ativa do usuário
    result = await db.execute(
        select(APIKey).where(
            APIKey.user_id == user_id,
            APIKey.is_active == True
        ).order_by(APIKey.last_used_at.desc())
    )
    api_key_record = result.scalar_one_or_none()
    
    if not api_key_record:
        raise HTTPException(400, "Nenhuma API key configurada")
    
    # Decrypt key
    key_service = APIKeyService()
    plaintext_key = key_service.decrypt_key(api_key_record.encrypted_key)
    
    # Factory pattern
    if api_key_record.provider == "openai":
        return OpenAIProvider(plaintext_key)
    elif api_key_record.provider == "anthropic":
        return AnthropicProvider(plaintext_key)
    else:
        raise ValueError(f"Provider não suportado: {api_key_record.provider}")
```

---

## 📝 Prompt Engineering

### System Prompt Template

```python
SYSTEM_PROMPT = """Você é o NetGuru, um assistente especializado em engenharia de redes.

Seu objetivo é ajudar engenheiros de rede com:
- Configuração de equipamentos (Cisco, Juniper, Arista)
- Troubleshooting de problemas de conectividade
- Análise de logs e PCAPs
- Design de topologias de rede
- Boas práticas de segurança

IMPORTANTE:
1. Base suas respostas APENAS no contexto fornecido abaixo
2. Se o contexto não contém informação suficiente, diga "Não tenho informação suficiente no contexto para responder com precisão"
3. Sempre cite a fonte quando usar documentação (ex: "De acordo com o Cisco OSPF Configuration Guide...")
4. Forneça comandos CLI completos e validados
5. Explique os comandos linha por linha quando relevante
6. Se detectar configuração insegura, alerte o usuário

CONTEXTO:
{context}

Agora responda a pergunta do usuário de forma clara e técnica.
"""
```

---

### Context Formatting

```python
def format_context(retrieved_chunks: List[Dict]) -> str:
    """
    Formata chunks recuperados em contexto legível
    """
    context_parts = []
    
    for i, chunk in enumerate(retrieved_chunks, 1):
        source = chunk['metadata'].get('source', 'Unknown')
        page = chunk['metadata'].get('page')
        
        source_info = f"Fonte {i}: {source}"
        if page:
            source_info += f" (página {page})"
        
        context_parts.append(f"{source_info}\n{chunk['text']}\n")
    
    return "\n---\n".join(context_parts)

# Exemplo de saída:
"""
Fonte 1: cisco_ospf_config_guide.pdf (página 42)
To configure OSPF area 0:
router ospf 1
 network 10.0.0.0 0.255.255.255 area 0
!

---

Fonte 2: user_config_routerA.txt (interface GigabitEthernet0/0)
interface GigabitEthernet0/0
 ip address 10.0.0.1 255.255.255.0
 ip ospf 1 area 0
!
"""
```

---

### Full Prompt Assembly

```python
async def build_chat_prompt(
    conversation_id: str,
    user_message: str,
    user_id: str,
    db: AsyncSession
) -> List[Dict[str, str]]:
    """
    Monta lista de mensagens para LLM
    """
    # 1. Retrieve context via RAG
    context_chunks = await retrieve_context(user_message, user_id)
    context = format_context(context_chunks)
    
    # 2. Get conversation history (últimas 10 mensagens)
    history = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    history_messages = list(reversed(history.scalars().all()))
    
    # 3. Build messages array
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(context=context)}
    ]
    
    # Add history
    for msg in history_messages:
        messages.append({
            "role": msg.role,
            "content": msg.content
        })
    
    # Add current user message
    messages.append({
        "role": "user",
        "content": user_message
    })
    
    return messages
```

---

## 🔄 Complete Chat Flow

```python
from app.services.rag.global_rag import retrieve_context
from app.services.llm.provider import get_llm_provider

async def process_chat_message(
    conversation_id: str,
    user_message: str,
    user_id: str,
    db: AsyncSession,
    websocket: WebSocket
):
    """
    Fluxo completo: RAG → LLM → Stream via WebSocket
    """
    try:
        # 1. Save user message
        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=user_message
        )
        db.add(user_msg)
        await db.commit()
        
        # 2. Build prompt with RAG
        messages = await build_chat_prompt(
            conversation_id,
            user_message,
            user_id,
            db
        )
        
        # 3. Get LLM provider
        llm = await get_llm_provider(user_id, db)
        
        # 4. Stream response
        full_response = ""
        token_count = 0
        
        await websocket.send_json({
            "type": "message_start",
            "message_id": str(uuid.uuid4())
        })
        
        async for token in llm.generate(messages, stream=True):
            full_response += token
            token_count += 1
            
            await websocket.send_json({
                "type": "token",
                "content": token
            })
        
        # 5. Save assistant message
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=full_response,
            tokens_used=token_count
        )
        db.add(assistant_msg)
        await db.commit()
        
        await websocket.send_json({
            "type": "message_end",
            "message_id": str(assistant_msg.id),
            "tokens_used": token_count
        })
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await websocket.send_json({
            "type": "error",
            "error": str(e)
        })
```

---

## 📊 Monitoring e Otimização

### Métricas Chave

```python
# Latency tracking
with tracer.start_as_current_span("rag_retrieval"):
    context = await retrieve_context(query, user_id)

with tracer.start_as_current_span("llm_generation"):
    response = await llm.generate(messages)

# Prometheus metrics
from prometheus_client import Histogram, Counter

rag_latency = Histogram('rag_retrieval_seconds', 'RAG retrieval latency')
llm_latency = Histogram('llm_generation_seconds', 'LLM generation latency')
tokens_generated = Counter('tokens_generated_total', 'Total tokens generated')
```

### Cache de Embeddings

```python
# Cache query embeddings em Redis (TTL 1h)
cache_key = f"embedding:{hash(query)}"
cached_vector = await redis.get(cache_key)

if cached_vector:
    query_vector = json.loads(cached_vector)
else:
    query_vector = model.encode(query).tolist()
    await redis.setex(cache_key, 3600, json.dumps(query_vector))
```

---

## 🗺️ Próximos Passos

1. Revise [06-phase1-foundation.md](06-phase1-foundation.md) para implementação inicial
2. Estude [07-phase2-core-features.md](07-phase2-core-features.md) para integração completa
3. Configure monitoring em [09-deployment.md](09-deployment.md)

---

**Ver também:** [01-architecture.md](01-architecture.md#rag-subsystem) para contexto arquitetural.
