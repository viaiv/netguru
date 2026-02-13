import { useCallback, useEffect, useRef, useState } from 'react';

import AutoResizeTextarea from '../components/chat/AutoResizeTextarea';
import ConnectionStatus from '../components/chat/ConnectionStatus';
import EmptyState from '../components/chat/EmptyState';
import MarkdownContent from '../components/chat/MarkdownContent';
import ToolCallDisplay from '../components/chat/ToolCallDisplay';
import { useWebSocketReconnect } from '../hooks/useWebSocketReconnect';
import type { IWebSocketEvent } from '../services/websocket';
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
    activeToolCalls,
    error,
    fetchConversations,
    createConversation,
    deleteConversation,
    selectConversation,
    fetchMessages,
    addUserMessage,
    handleStreamStart,
    handleStreamChunk,
    handleStreamEnd,
    handleToolCallStart,
    handleToolCallEnd,
    handleWsError,
    setConnected,
    clearError,
  } = useChatStore();

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
        case 'tool_call_start':
          handleToolCallStart(event.tool_name!, event.tool_input!);
          break;
        case 'tool_call_end':
          handleToolCallEnd(event.tool_name!, event.result_preview!, event.duration_ms!);
          break;
        case 'error':
          handleWsError(event.detail ?? 'Erro desconhecido');
          break;
        case 'pong':
          break;
      }
    },
    [handleStreamStart, handleStreamChunk, handleStreamEnd, handleToolCallStart, handleToolCallEnd, handleWsError],
  );

  // ---- WebSocket with auto-reconnect ----

  const { isConnected, isReconnecting, reconnectAttempt, sendMessage, manualRetry } =
    useWebSocketReconnect({
      conversationId: currentConversationId,
      onEvent: onWsEvent,
    });

  // Sync connection state to store
  useEffect(() => {
    setConnected(isConnected);
  }, [isConnected, setConnected]);

  // ---- Load conversations on mount ----

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // ---- Fetch messages when conversation changes ----

  useEffect(() => {
    if (currentConversationId) {
      fetchMessages(currentConversationId);
    }
  }, [currentConversationId, fetchMessages]);

  // ---- Auto-scroll (dentro do container, sem mover a pagina) ----

  useEffect(() => {
    const el = chatWindowRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    });
  }, [messages, streamingContent, activeToolCalls]);

  // ---- Send message ----

  function handleSend(): void {
    const text = inputValue.trim();
    if (!text || isStreaming || !isConnected) return;

    addUserMessage(text);
    sendMessage(text);
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

  // ---- Suggestion from EmptyState ----

  async function handleSuggestion(text: string): Promise<void> {
    const conv = await createConversation();
    if (conv) {
      selectConversation(conv.id);
      // Aguardar proximo tick para que o WS conecte
      setTimeout(() => {
        setInputValue(text);
      }, 100);
    }
  }

  // ---- Delete conversation ----

  async function handleDeleteConversation(e: React.MouseEvent, convId: string): Promise<void> {
    e.stopPropagation();
    await deleteConversation(convId);
  }

  // ---- Render helpers ----

  function renderMessage(msg: IMessage) {
    const isUser = msg.role === 'user';
    return (
      <div key={msg.id} className={`message-bubble ${isUser ? 'message-bubble--user' : 'message-bubble--assistant'}`}>
        <p className="message-role">{isUser ? 'Voce' : 'NetGuru'}</p>
        {isUser ? (
          <div className="message-content">{msg.content}</div>
        ) : (
          <MarkdownContent content={msg.content} />
        )}
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
            <div
              key={conv.id}
              className={`conversation-item ${conv.id === currentConversationId ? 'conversation-item--active' : ''}`}
            >
              <button
                type="button"
                className="conversation-item-body"
                onClick={() => selectConversation(conv.id)}
              >
                <span className="conversation-title">{conv.title}</span>
                <span className="conversation-date">
                  {new Date(conv.updated_at).toLocaleDateString('pt-BR')}
                </span>
              </button>
              <button
                type="button"
                className="conversation-delete-btn"
                title="Excluir conversa"
                onClick={(e) => handleDeleteConversation(e, conv.id)}
              >
                &times;
              </button>
            </div>
          ))}
          {conversations.length === 0 && (
            <p className="chat-empty-hint">Nenhuma conversa ainda. Crie uma para comecar!</p>
          )}
        </div>
      </aside>

      {/* ---- Main chat area ---- */}
      <section className="chat-main">
        {!currentConversationId ? (
          <EmptyState onSuggestion={handleSuggestion} />
        ) : (
          <>
            {/* Connection status */}
            <div className="chat-toolbar">
              <ConnectionStatus
                isConnected={isConnected}
                isReconnecting={isReconnecting}
                reconnectAttempt={reconnectAttempt}
                onRetry={manualRetry}
              />
            </div>

            {/* Messages */}
            <div className="chat-window" ref={chatWindowRef}>
              {messages.map(renderMessage)}

              {/* Tool calls display */}
              {isStreaming && activeToolCalls.length > 0 && (
                <ToolCallDisplay toolCalls={activeToolCalls} />
              )}

              {/* Streaming bubble */}
              {isStreaming && streamingContent && (
                <div className="message-bubble message-bubble--assistant">
                  <p className="message-role">NetGuru</p>
                  <MarkdownContent content={streamingContent} isStreaming />
                  <span className="typing-cursor" />
                </div>
              )}

              {/* Waiting indicator (streaming started but no text yet) */}
              {isStreaming && !streamingContent && activeToolCalls.length === 0 && (
                <div className="message-bubble message-bubble--assistant">
                  <p className="message-role">NetGuru</p>
                  <div className="message-content">
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
              <AutoResizeTextarea
                placeholder={isConnected ? 'Digite sua mensagem...' : 'Aguardando conexao...'}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={!isConnected || isStreaming}
                maxRows={8}
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
