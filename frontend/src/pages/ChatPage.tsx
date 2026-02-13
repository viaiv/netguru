import { useCallback, useEffect, useRef, useState } from 'react';

import { ChatWebSocket, type IWebSocketEvent } from '../services/websocket';
import { useChatStore, type IMessage } from '../stores/chatStore';

/* ------------------------------------------------------------------ */
/*  ChatPage — full-screen chat with sidebar + message area + input   */
/* ------------------------------------------------------------------ */

function ChatPage() {
  const {
    conversations,
    currentConversationId,
    messages,
    isStreaming,
    streamingContent,
    isConnected,
    error,
    fetchConversations,
    createConversation,
    selectConversation,
    fetchMessages,
    addUserMessage,
    handleStreamStart,
    handleStreamChunk,
    handleStreamEnd,
    handleWsError,
    setConnected,
    clearError,
  } = useChatStore();

  const wsRef = useRef<ChatWebSocket | null>(null);
  const chatWindowRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState('');

  // ---- WS event handler ----

  const onWsEvent = useCallback(
    (event: IWebSocketEvent) => {
      switch (event.type) {
        case 'stream_start':
          handleStreamStart(event.message_id!);
          break;
        case 'stream_chunk':
          handleStreamChunk(event.content!);
          break;
        case 'stream_end':
          handleStreamEnd(event.message_id!, event.tokens_used ?? null);
          break;
        case 'error':
          handleWsError(event.detail ?? 'Erro desconhecido');
          break;
        case 'pong':
          break;
      }
    },
    [handleStreamStart, handleStreamChunk, handleStreamEnd, handleWsError],
  );

  // ---- Load conversations on mount ----

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // ---- Connect/disconnect WS when conversation changes ----

  useEffect(() => {
    if (!currentConversationId) {
      wsRef.current?.disconnect();
      setConnected(false);
      return;
    }

    // Fetch history
    fetchMessages(currentConversationId);

    // Connect WS
    const ws = new ChatWebSocket(onWsEvent);
    ws.connect(
      currentConversationId,
      () => setConnected(true),
      () => setConnected(false),
    );
    wsRef.current = ws;

    return () => {
      ws.disconnect();
      setConnected(false);
    };
  }, [currentConversationId, fetchMessages, onWsEvent, setConnected]);

  // ---- Auto-scroll (dentro do container, sem mover a página) ----

  useEffect(() => {
    const el = chatWindowRef.current;
    if (!el) return;
    // Aguarda o DOM renderizar antes de scrollar
    requestAnimationFrame(() => {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    });
  }, [messages, streamingContent]);

  // ---- Send message ----

  function handleSend(): void {
    const text = inputValue.trim();
    if (!text || isStreaming || !isConnected) return;

    addUserMessage(text);
    wsRef.current?.sendMessage(text);
    setInputValue('');
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>): void {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  // ---- Create new conversation ----

  async function handleNewConversation(): Promise<void> {
    const conv = await createConversation();
    if (conv) {
      selectConversation(conv.id);
    }
  }

  // ---- Render helpers ----

  function renderMessage(msg: IMessage) {
    const isUser = msg.role === 'user';
    return (
      <div key={msg.id} className={`message-bubble ${isUser ? 'message-bubble--user' : 'message-bubble--assistant'}`}>
        <p className="message-role">{isUser ? 'Voce' : 'NetGuru'}</p>
        <div className="message-content">{msg.content}</div>
      </div>
    );
  }

  return (
    <div className="chat-page">
      {/* ---- Sidebar ---- */}
      <aside className="chat-sidebar">
        <button type="button" className="btn btn-primary chat-new-btn" onClick={handleNewConversation}>
          + Nova Conversa
        </button>

        <div className="conversation-list">
          {conversations.map((conv) => (
            <button
              key={conv.id}
              type="button"
              className={`conversation-item ${conv.id === currentConversationId ? 'conversation-item--active' : ''}`}
              onClick={() => selectConversation(conv.id)}
            >
              <span className="conversation-title">{conv.title}</span>
              <span className="conversation-date">
                {new Date(conv.updated_at).toLocaleDateString('pt-BR')}
              </span>
            </button>
          ))}
          {conversations.length === 0 && (
            <p className="chat-empty-hint">Nenhuma conversa ainda. Crie uma para comecar!</p>
          )}
        </div>
      </aside>

      {/* ---- Main chat area ---- */}
      <section className="chat-main">
        {!currentConversationId ? (
          <div className="chat-placeholder">
            <h2 className="view-title">NetGuru Chat</h2>
            <p className="view-subtitle">
              Selecione ou crie uma conversa para comecar.
            </p>
          </div>
        ) : (
          <>
            {/* Connection status */}
            <div className="chat-toolbar">
              <span className={`ws-status ${isConnected ? 'ws-status--online' : 'ws-status--offline'}`}>
                {isConnected ? 'Conectado' : 'Desconectado'}
              </span>
            </div>

            {/* Messages */}
            <div className="chat-window" ref={chatWindowRef}>
              {messages.map(renderMessage)}

              {/* Streaming bubble */}
              {isStreaming && (
                <div className="message-bubble message-bubble--assistant">
                  <p className="message-role">NetGuru</p>
                  <div className="message-content">
                    {streamingContent}
                    <span className="typing-cursor" />
                  </div>
                </div>
              )}

              {/* Error banner */}
              {error && (
                <div className="error-banner chat-error">
                  {error}
                  <button type="button" className="ghost-btn chat-dismiss" onClick={clearError}>
                    fechar
                  </button>
                </div>
              )}

              <div />
            </div>

            {/* Input area */}
            <div className="chat-input-area">
              <textarea
                className="chat-textarea"
                rows={2}
                placeholder={isConnected ? 'Digite sua mensagem...' : 'Aguardando conexao...'}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={!isConnected || isStreaming}
              />
              <button
                type="button"
                className="btn btn-primary chat-send-btn"
                onClick={handleSend}
                disabled={!isConnected || isStreaming || !inputValue.trim()}
              >
                Enviar
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

export default ChatPage;
