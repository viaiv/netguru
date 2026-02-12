# Phase 2: Core Features - NetGuru Platform

**Sprint:** 3-4 (2 semanas)  
**Objetivo:** Chat funcional com RAG Global + File Upload  
**Data:** Fevereiro-Março 2026

---

## 🎯 Objetivos da Fase 2

Ao final desta fase, teremos:
- ✅ Chat funcional com WebSocket
- ✅ RAG Global implementado (docs Cisco)
- ✅ LLM integration (OpenAI/Anthropic via BYO-Key)
- ✅ Upload de arquivos (configs/logs)
- ✅ RAG Local (documentos do cliente)
- ✅ Frontend completo de chat com streaming

**Entregável:** MVP funcional - usuário pode fazer perguntas técnicas e receber respostas contextualizadas.

---

## 📋 Backend Implementation

### Task 2.1: Database Models (Conversations & Messages)

**app/models/conversation.py:**
```python
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False, default="Nova Conversa")
    model_used = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # user, assistant, system
    content = Column(String, nullable=False)
    tokens_used = Column(Integer)
    metadata = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
```

**Adicionar ao User model:**
```python
# Em app/models/user.py
from sqlalchemy.orm import relationship

class User(Base):
    # ... campos existentes ...
    
    # Relationships
    conversations = relationship("Conversation", back_populates="user")
    api_keys = relationship("APIKey", back_populates="user")
```

**Migration:**
```bash
alembic revision --autogenerate -m "add conversations and messages"
alembic upgrade head
```

---

### Task 2.2: Document & Embedding Models

**app/models/document.py:**
```python
from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid
from app.db.base import Base

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # config, log, pcap, pdf
    file_size_bytes = Column(BigInteger, nullable=False)
    storage_path = Column(String, nullable=False)
    mime_type = Column(String)
    status = Column(String, default="uploaded")  # uploaded, processing, completed, failed
    metadata = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User")
    embeddings = relationship("Embedding", back_populates="document", cascade="all, delete-orphan")

class Embedding(Base):
    __tablename__ = "embeddings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))  # NULL for global RAG
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_text = Column(String, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding = Column(Vector(384))  # Dimensão do all-MiniLM-L6-v2
    metadata = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="embeddings")
```

**Setup pgvector:**
```sql
-- Run in PostgreSQL
CREATE EXTENSION IF NOT EXISTS vector;
```

**requirements.txt (adicionar):**
```txt
pgvector==0.2.4
sentence-transformers==2.2.2
langchain==0.1.0
langchain-community==0.0.10
openai==1.7.2
anthropic==0.8.1
```

---

### Task 2.3: Embedding Service

**app/services/rag/embeddings.py:**
```python
from sentence_transformers import SentenceTransformer
from typing import List
import numpy as np

class EmbeddingService:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.dimension = 384
    
    def encode(self, text: str) -> List[float]:
        """Gera embedding para um texto"""
        vector = self.model.encode(text, convert_to_numpy=True)
        return vector.tolist()
    
    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """Gera embeddings para múltiplos textos"""
        vectors = self.model.encode(texts, convert_to_numpy=True)
        return vectors.tolist()

# Singleton
embedding_service = EmbeddingService()
```

---

### Task 2.4: RAG Global Service

**app/services/rag/global_rag.py:**
```python
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.services.rag.embeddings import embedding_service

class GlobalRAGService:
    async def retrieve(
        self,
        query: str,
        db: AsyncSession,
        top_k: int = 3
    ) -> List[Dict]:
        """
        Busca nos documentos curados (RAG Global)
        """
        # Generate query embedding
        query_vector = embedding_service.encode(query)
        
        # Search
        result = await db.execute(
            text("""
                SELECT 
                    chunk_text,
                    metadata,
                    1 - (embedding <=> CAST(:vector AS vector)) AS similarity
                FROM embeddings
                WHERE user_id IS NULL
                ORDER BY embedding <=> CAST(:vector AS vector)
                LIMIT :limit
            """),
            {"vector": query_vector, "limit": top_k}
        )
        
        results = []
        for row in result:
            results.append({
                "text": row.chunk_text,
                "source": "global",
                "similarity": float(row.similarity),
                "metadata": row.metadata
            })
        
        return results
```

---

### Task 2.5: LLM Provider Integration

**app/services/llm/provider.py:**
```python
from abc import ABC, abstractmethod
from typing import List, Dict, AsyncGenerator

class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False
    ) -> str | AsyncGenerator[str, None]:
        pass

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4-turbo-preview"
    
    async def generate(self, messages, stream=False):
        if stream:
            return self._stream(messages)
        else:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content
    
    async def _stream(self, messages):
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True
        )
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = "claude-3-opus-20240229"
    
    async def generate(self, messages, stream=False):
        if stream:
            return self._stream(messages)
        else:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=messages
            )
            return response.content[0].text
    
    async def _stream(self, messages):
        async with self.client.messages.stream(
            model=self.model,
            max_tokens=4096,
            messages=messages
        ) as stream:
            async for text in stream.text_stream:
                yield text
```

---

### Task 2.6: Chat Service

**app/services/chat_service.py:**
```python
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.rag.global_rag import GlobalRAGService
from app.services.llm.provider import LLMProvider
import uuid

SYSTEM_PROMPT = """Você é o NetGuru, um assistente especializado em engenharia de redes.

Seu objetivo é ajudar engenheiros de rede com configurações Cisco, Juniper e Arista.

CONTEXTO:
{context}

Responda de forma técnica e precisa, citando fontes quando possível."""

class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.rag = GlobalRAGService()
    
    async def create_conversation(self, user_id: uuid.UUID, title: str = "Nova Conversa") -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation
    
    async def get_conversations(self, user_id: uuid.UUID, limit: int = 20) -> List[Conversation]:
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    async def send_message(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        llm_provider: LLMProvider,
        stream: bool = True
    ):
        # 1. Save user message
        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=content
        )
        self.db.add(user_msg)
        await self.db.commit()
        
        # 2. Retrieve context
        context_chunks = await self.rag.retrieve(content, self.db)
        context = self._format_context(context_chunks)
        
        # 3. Build prompt
        messages = await self._build_prompt(conversation_id, content, context)
        
        # 4. Generate response
        if stream:
            async for token in llm_provider.generate(messages, stream=True):
                yield token
        else:
            response = await llm_provider.generate(messages, stream=False)
            yield response
    
    def _format_context(self, chunks: List[Dict]) -> str:
        parts = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk['metadata'].get('source', 'Unknown')
            parts.append(f"Fonte {i}: {source}\n{chunk['text']}")
        return "\n\n---\n\n".join(parts)
    
    async def _build_prompt(
        self,
        conversation_id: uuid.UUID,
        current_message: str,
        context: str
    ) -> List[Dict[str, str]]:
        # Get history
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(10)
        )
        history = list(reversed(result.scalars().all()))
        
        # Build messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(context=context)}
        ]
        
        for msg in history[:-1]:  # Exclude last (current) message
            messages.append({"role": msg.role, "content": msg.content})
        
        messages.append({"role": "user", "content": current_message})
        
        return messages
```

---

### Task 2.7: WebSocket Endpoint

**app/api/v1/endpoints/websocket.py:**
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.chat_service import ChatService
from app.services.llm.provider import get_llm_provider
from app.core.security import decode_token
import json
import uuid

router = APIRouter()

@router.websocket("/ws/chat/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: uuid.UUID,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    await websocket.accept()
    
    # Authenticate
    user_id = decode_token(token)
    if not user_id:
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    try:
        chat_service = ChatService(db)
        llm_provider = await get_llm_provider(uuid.UUID(user_id), db)
        
        while True:
            # Receive message
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "message":
                content = message_data.get("content")
                
                # Stream response
                await websocket.send_json({"type": "message_start"})
                
                full_response = ""
                async for token in chat_service.send_message(
                    conversation_id,
                    uuid.UUID(user_id),
                    content,
                    llm_provider,
                    stream=True
                ):
                    full_response += token
                    await websocket.send_json({
                        "type": "token",
                        "content": token
                    })
                
                # Save assistant message
                assistant_msg = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_response
                )
                db.add(assistant_msg)
                await db.commit()
                
                await websocket.send_json({"type": "message_end"})
    
    except WebSocketDisconnect:
        print(f"Client disconnected")
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "error": str(e)
        })
        await websocket.close()
```

---

## 📋 Frontend Implementation

### Task 2.8: Chat Store

**src/stores/chatStore.ts:**
```typescript
import { create } from 'zustand';
import api from '../services/api';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

interface ChatState {
  conversations: Conversation[];
  currentConversation: Conversation | null;
  messages: Message[];
  isLoading: boolean;
  
  fetchConversations: () => Promise<void>;
  createConversation: (title?: string) => Promise<Conversation>;
  selectConversation: (id: string) => Promise<void>;
  sendMessage: (content: string) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  currentConversation: null,
  messages: [],
  isLoading: false,
  
  fetchConversations: async () => {
    const response = await api.get('/chat/conversations');
    set({ conversations: response.data.conversations });
  },
  
  createConversation: async (title = 'Nova Conversa') => {
    const response = await api.post('/chat/conversations', { title });
    const conversation = response.data;
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      currentConversation: conversation,
      messages: []
    }));
    return conversation;
  },
  
  selectConversation: async (id: string) => {
    set({ isLoading: true });
    const response = await api.get(`/chat/conversations/${id}`);
    set({
      currentConversation: response.data,
      messages: response.data.messages,
      isLoading: false
    });
  },
  
  sendMessage: (content: string) => {
    // Será implementado com WebSocket
  }
}));
```

---

### Task 2.9: WebSocket Hook

**src/hooks/useWebSocket.ts:**
```typescript
import { useEffect, useRef, useState } from 'react';

interface UseWebSocketProps {
  conversationId: string;
  onMessage: (data: any) => void;
}

export function useWebSocket({ conversationId, onMessage }: UseWebSocketProps) {
  const ws = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    const wsUrl = `ws://localhost:8000/api/v1/ws/chat/${conversationId}?token=${token}`;
    
    ws.current = new WebSocket(wsUrl);
    
    ws.current.onopen = () => {
      setIsConnected(true);
      console.log('WebSocket connected');
    };
    
    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      onMessage(data);
    };
    
    ws.current.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    ws.current.onclose = () => {
      setIsConnected(false);
      console.log('WebSocket disconnected');
    };
    
    return () => {
      ws.current?.close();
    };
  }, [conversationId]);
  
  const sendMessage = (content: string) => {
    if (ws.current && isConnected) {
      ws.current.send(JSON.stringify({ type: 'message', content }));
    }
  };
  
  return { sendMessage, isConnected };
}
```

---

### Task 2.10: Chat Page

**src/pages/Chat.tsx:**
```typescript
import React, { useState, useEffect, useRef } from 'react';
import { useChatStore } from '../stores/chatStore';
import { useWebSocket } from '../hooks/useWebSocket';

export default function Chat() {
  const [input, setInput] = useState('');
  const [streamingMessage, setStreamingMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  const {
    currentConversation,
    messages,
    createConversation,
    selectConversation
  } = useChatStore();
  
  useEffect(() => {
    // Create default conversation if none exists
    if (!currentConversation) {
      createConversation();
    }
  }, []);
  
  const { sendMessage, isConnected } = useWebSocket({
    conversationId: currentConversation?.id || '',
    onMessage: (data) => {
      if (data.type === 'token') {
        setStreamingMessage((prev) => prev + data.content);
      } else if (data.type === 'message_end') {
        // Adicionar mensagem completa ao histórico
        useChatStore.setState((state) => ({
          messages: [
            ...state.messages,
            {
              id: data.message_id,
              role: 'assistant',
              content: streamingMessage,
              created_at: new Date().toISOString()
            }
          ]
        }));
        setStreamingMessage('');
      }
    }
  });
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    
    // Add user message
    useChatStore.setState((state) => ({
      messages: [
        ...state.messages,
        {
          id: Date.now().toString(),
          role: 'user',
          content: input,
          created_at: new Date().toISOString()
        }
      ]
    }));
    
    sendMessage(input);
    setInput('');
  };
  
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMessage]);
  
  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar com conversas */}
      <div className="w-64 bg-white border-r p-4">
        <h2 className="text-xl font-bold mb-4">Conversas</h2>
        {/* Lista de conversas aqui */}
      </div>
      
      {/* Chat area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="bg-white border-b p-4">
          <h1 className="text-xl font-semibold">
            {currentConversation?.title || 'NetGuru Chat'}
          </h1>
        </div>
        
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-2xl p-4 rounded-lg ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white border'
                }`}
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
              </div>
            </div>
          ))}
          
          {/* Streaming message */}
          {streamingMessage && (
            <div className="flex justify-start">
              <div className="max-w-2xl p-4 rounded-lg bg-white border">
                <p className="whitespace-pre-wrap">{streamingMessage}</p>
                <span className="inline-block w-2 h-4 bg-gray-400 animate-pulse ml-1" />
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>
        
        {/* Input */}
        <form onSubmit={handleSubmit} className="bg-white border-t p-4">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Digite sua pergunta..."
              className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={!isConnected}
            />
            <button
              type="submit"
              disabled={!isConnected || !input.trim()}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              Enviar
            </button>
          </div>
          {!isConnected && (
            <p className="text-sm text-amber-600 mt-2">Conectando...</p>
          )}
        </form>
      </div>
    </div>
  );
}
```

---

## ✅ Definition of Done

Fase 2 está completa quando:

- [ ] Usuário pode criar conversa
- [ ] Usuário pode enviar mensagem via WebSocket
- [ ] Resposta é streamada token por token
- [ ] RAG Global retorna chunks relevantes
- [ ] LLM gera resposta baseada no contexto
- [ ] Mensagens são salvas no banco
- [ ] Frontend renderiza mensagens em tempo real
- [ ] Sistema funciona com OpenAI E Anthropic
- [ ] Usuário pode configurar API key no perfil

---

## 🧪 Testes

```bash
# Testar RAG retrieval
pytest tests/test_rag.py -v

# Testar chat service
pytest tests/test_chat_service.py -v

# Testar WebSocket
pytest tests/test_websocket.py -v
```

---

## 🗺️ Próximos Passos

Fase 2 completa? Avance para:
- **[08-phase3-agents.md](08-phase3-agents.md)**: Implementar PCAP analysis + Topology

**Estimativa de tempo:** 12-14 dias (2 desenvolvedores)
