import { useCallback, useEffect, useRef, useState } from 'react';

import AutoResizeTextarea from '../components/chat/AutoResizeTextarea';
import ConnectionStatus from '../components/chat/ConnectionStatus';
import EmptyState from '../components/chat/EmptyState';
import FileAttachmentChip from '../components/chat/FileAttachmentChip';
import MarkdownContent from '../components/chat/MarkdownContent';
import ToolCallDisplay from '../components/chat/ToolCallDisplay';
import { useMobile } from '../hooks/useMediaQuery';
import { useWebSocketReconnect } from '../hooks/useWebSocketReconnect';
import { ALLOWED_EXTENSIONS, uploadFile, validateFile } from '../services/fileApi';
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
    streamingMessageId,
    activeToolCalls,
    error,
    fetchConversations,
    createConversation,
    deleteConversation,
    renameConversation,
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
    updateConversationTitle,
  } = useChatStore();

  const chatWindowRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState('');
  const isMobile = useMobile();
  const [showSidebar, setShowSidebar] = useState(false);

  // ---- Inline rename state ----
  const [editingConvId, setEditingConvId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  // ---- File attachment state ----

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

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
        case 'title_updated':
          if (currentConversationId && event.title) {
            updateConversationTitle(currentConversationId, event.title);
          }
          break;
        case 'error':
          handleWsError(event.detail ?? 'Erro desconhecido');
          break;
        case 'pong':
          break;
      }
    },
    [handleStreamStart, handleStreamChunk, handleStreamEnd, handleToolCallStart, handleToolCallEnd, handleWsError, currentConversationId, updateConversationTitle],
  );

  // ---- WebSocket with auto-reconnect ----

  const { isConnected, isReconnecting, reconnectAttempt, sendMessage, sendCancel, manualRetry } =
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

  // ---- File attachment handlers ----

  function handleAttachClick(): void {
    fileInputRef.current?.click();
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>): void {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset input so the same file can be re-selected
    e.target.value = '';

    const validationError = validateFile(file);
    if (validationError) {
      setAttachedFile(file);
      setUploadError(validationError);
      return;
    }

    setAttachedFile(file);
    setUploadProgress(null);
    setUploadError(null);
  }

  function handleRemoveFile(): void {
    setAttachedFile(null);
    setUploadProgress(null);
    setUploadError(null);
  }

  // ---- Send message ----

  async function handleSend(): Promise<void> {
    const text = inputValue.trim();
    const hasFile = attachedFile !== null && uploadError === null;

    if ((!text && !hasFile) || isStreaming || !isConnected) return;

    if (hasFile && attachedFile) {
      try {
        setUploadProgress(0);
        const result = await uploadFile(attachedFile, (progress) => {
          setUploadProgress(progress.percentage);
        });

        const fileLabel = `[Arquivo anexado: ${result.filename} (${result.file_type}, ${result.id})]`;
        const fullMessage = text ? `${fileLabel}\n${text}` : fileLabel;

        addUserMessage(fullMessage);
        sendMessage(fullMessage);

        // Reset file + input
        setAttachedFile(null);
        setUploadProgress(null);
        setUploadError(null);
        setInputValue('');
      } catch (err) {
        setUploadProgress(null);
        const msg = err instanceof Error ? err.message : 'Falha no upload';
        setUploadError(msg);
      }
      return;
    }

    // Text-only message
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

  // ---- Rename conversation ----

  function handleStartRename(e: React.MouseEvent, convId: string, currentTitle: string): void {
    e.stopPropagation();
    setEditingConvId(convId);
    setEditingTitle(currentTitle);
  }

  async function handleFinishRename(): Promise<void> {
    if (!editingConvId) return;
    const trimmed = editingTitle.trim();
    if (trimmed && trimmed.length <= 255) {
      await renameConversation(editingConvId, trimmed);
    }
    setEditingConvId(null);
    setEditingTitle('');
  }

  function handleRenameKeyDown(e: React.KeyboardEvent): void {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleFinishRename();
    } else if (e.key === 'Escape') {
      setEditingConvId(null);
      setEditingTitle('');
    }
  }

  // ---- Mobile sidebar helpers ----

  function handleSelectConversation(convId: string): void {
    selectConversation(convId);
    if (isMobile) setShowSidebar(false);
  }

  // ---- Derived state ----

  const isUploading = uploadProgress !== null && uploadProgress < 100;
  const canSend =
    isConnected &&
    !isStreaming &&
    !isUploading &&
    (!!inputValue.trim() || (attachedFile !== null && uploadError === null));

  // ---- Render helpers ----

  function renderMessage(msg: IMessage) {
    const isUser = msg.role === 'user';
    const metaToolCalls = (msg.metadata as Record<string, unknown>)?.tool_calls as Array<{
      tool: string;
      input?: string;
      result_preview?: string;
      duration_ms?: number;
    }> | undefined;
    const hasPcapTool = metaToolCalls?.some((tc) => tc.tool === 'analyze_pcap');

    return (
      <div key={msg.id} className={`message-row ${isUser ? 'message-row--user' : 'message-row--assistant'}`}>
        {/* Tool calls from historical messages */}
        {!isUser && metaToolCalls && metaToolCalls.length > 0 && (
          <ToolCallDisplay
            toolCalls={metaToolCalls.map((tc, i) => ({
              id: `hist-${msg.id}-${i}`,
              toolName: tc.tool,
              toolInput: tc.input ?? '',
              resultPreview: tc.result_preview,
              durationMs: tc.duration_ms,
              status: 'completed' as const,
            }))}
            messageId={hasPcapTool ? msg.id : undefined}
          />
        )}
        <div className={`message-bubble ${isUser ? 'message-bubble--user' : 'message-bubble--assistant'}`}>
          <p className="message-role">{isUser ? 'Voce' : 'NetGuru'}</p>
          {isUser ? (
            <div className="message-content">{msg.content}</div>
          ) : (
            <MarkdownContent content={msg.content} />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="chat-page">
      {/* ---- Mobile drawer overlay ---- */}
      {isMobile && showSidebar && (
        <div className="chat-drawer-overlay" onClick={() => setShowSidebar(false)} />
      )}

      {/* ---- Sidebar ---- */}
      <aside className={`chat-sidebar ${isMobile && showSidebar ? 'chat-sidebar--open' : ''}`}>
        <button type="button" className="btn btn-primary chat-new-btn" onClick={handleNewConversation}>
          + Nova Conversa
        </button>

        <div className="conversation-list">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={`conversation-item ${conv.id === currentConversationId ? 'conversation-item--active' : ''}`}
            >
              {editingConvId === conv.id ? (
                <div className="conversation-item-body">
                  <input
                    className="conversation-title-input"
                    value={editingTitle}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    onBlur={handleFinishRename}
                    onKeyDown={handleRenameKeyDown}
                    maxLength={255}
                    autoFocus
                  />
                </div>
              ) : (
                <>
                  <button
                    type="button"
                    className="conversation-item-body"
                    onClick={() => handleSelectConversation(conv.id)}
                  >
                    <span className="conversation-title">{conv.title}</span>
                    <span className="conversation-date">
                      {new Date(conv.updated_at).toLocaleDateString('pt-BR')}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="conversation-action-btn conversation-rename-btn"
                    title="Renomear conversa"
                    onClick={(e) => handleStartRename(e, conv.id, conv.title)}
                  >
                    &#9998;
                  </button>
                  <button
                    type="button"
                    className="conversation-action-btn conversation-delete-btn"
                    title="Excluir conversa"
                    onClick={(e) => handleDeleteConversation(e, conv.id)}
                  >
                    &times;
                  </button>
                </>
              )}
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
          <>
            {isMobile && (
              <div className="chat-toolbar">
                <button
                  type="button"
                  className="chat-drawer-toggle"
                  onClick={() => setShowSidebar((v) => !v)}
                  aria-label="Conversas"
                >
                  &#9776;
                </button>
              </div>
            )}
            <EmptyState onSuggestion={handleSuggestion} />
          </>
        ) : (
          <>
            {/* Connection status */}
            <div className="chat-toolbar">
              <button
                type="button"
                className="chat-drawer-toggle"
                onClick={() => setShowSidebar((v) => !v)}
                aria-label="Conversas"
              >
                &#9776;
              </button>
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
                <ToolCallDisplay toolCalls={activeToolCalls} messageId={streamingMessageId ?? undefined} />
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

            {/* File attachment preview */}
            {attachedFile && (
              <div className="chat-input-attachment">
                <FileAttachmentChip
                  file={attachedFile}
                  uploadProgress={uploadProgress}
                  uploadError={uploadError}
                  onRemove={handleRemoveFile}
                />
              </div>
            )}

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              style={{ display: 'none' }}
              accept={ALLOWED_EXTENSIONS.join(',')}
              onChange={handleFileChange}
            />

            {/* Input area */}
            <div className="chat-input-area">
              <button
                type="button"
                className="chat-attach-btn"
                onClick={handleAttachClick}
                disabled={!isConnected || isStreaming || attachedFile !== null}
                title="Anexar arquivo"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                </svg>
              </button>
              <AutoResizeTextarea
                placeholder={isConnected ? 'Digite sua mensagem...' : 'Aguardando conexao...'}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={!isConnected || isStreaming}
                maxRows={8}
              />
              {isStreaming ? (
                <button
                  type="button"
                  className="btn btn-danger chat-send-btn"
                  onClick={sendCancel}
                >
                  Cancelar
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-primary chat-send-btn"
                  onClick={handleSend}
                  disabled={!canSend}
                >
                  Enviar
                </button>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}

export default ChatPage;
