import { useCallback, useEffect, useRef, useState } from 'react';

import AutoResizeTextarea from '../components/chat/AutoResizeTextarea';
import ConnectionStatus from '../components/chat/ConnectionStatus';
import EmptyState from '../components/chat/EmptyState';
import EvidencePanel from '../components/chat/EvidencePanel';
import FileAttachmentChip from '../components/chat/FileAttachmentChip';
import MarkdownContent from '../components/chat/MarkdownContent';
import ToolCallDisplay from '../components/chat/ToolCallDisplay';
import { useWebSocketReconnect } from '../hooks/useWebSocketReconnect';
import { getErrorMessage } from '../services/api';
import { ALLOWED_EXTENSIONS, uploadFile, validateFile } from '../services/fileApi';
import type { IWebSocketEvent } from '../services/websocket';
import { useChatStore, type IMessage } from '../stores/chatStore';

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function extractLimitCode(err: unknown): string | null {
  if (
    typeof err === 'object' &&
    err !== null &&
    'response' in err
  ) {
    const resp = (err as { response?: { data?: { detail?: { code?: string } } } }).response;
    const code = resp?.data?.detail?.code;
    if (typeof code === 'string' && code.endsWith('_limit_exceeded')) return code;
  }
  return null;
}

/* ------------------------------------------------------------------ */
/*  ChatPage — chat content (messages + input), sem aside/sidebar     */
/* ------------------------------------------------------------------ */

function ChatPage() {
  const {
    currentConversationId,
    messages,
    isStreaming,
    streamingContent,
    streamingMessageId,
    activeToolCalls,
    usingFreeLlm,
    llmProvider,
    error,
    errorCode,
    fetchConversations,
    createConversation,
    selectConversation,
    fetchMessages,
    addUserMessage,
    handleStreamStart,
    handleStreamChunk,
    handleStreamEnd,
    handleStreamCancelled,
    handleToolCallStart,
    handleToolCallState,
    handleToolCallEnd,
    handleWsError,
    setConnected,
    clearError,
    updateConversationTitle,
  } = useChatStore();

  const chatWindowRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState('');

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
          handleStreamStart(event.message_id!, event.using_free_llm, event.llm_provider);
          break;
        case 'stream_chunk':
          handleStreamChunk(event.content!);
          break;
        case 'stream_end':
          if (event.message_id) {
            handleStreamEnd(event.message_id, event.tokens_used ?? null, event.metadata ?? null);
          } else {
            handleStreamCancelled();
          }
          break;
        case 'stream_cancelled':
          handleStreamCancelled();
          break;
        case 'tool_call_start':
          if (event.tool_name && event.tool_input !== undefined) {
            handleToolCallStart(
              event.tool_call_id ?? event.tool_name,
              event.tool_name,
              event.tool_input,
            );
          }
          break;
        case 'tool_call_end':
          if (event.tool_name && event.result_preview !== undefined) {
            handleToolCallEnd(
              event.tool_call_id ?? event.tool_name,
              event.tool_name,
              event.result_preview,
              event.duration_ms ?? 0,
            );
          }
          break;
        case 'tool_call_state':
          if (event.tool_name && event.status) {
            handleToolCallState(
              event.tool_call_id ?? event.tool_name,
              event.tool_name,
              event.status,
              event.progress_pct,
              event.elapsed_ms,
              event.eta_ms,
              event.detail,
            );
          }
          break;
        case 'title_updated':
          if (currentConversationId && event.title) {
            updateConversationTitle(currentConversationId, event.title);
          }
          break;
        case 'error':
          handleWsError(event.detail ?? 'Erro desconhecido', event.code);
          break;
        case 'pong':
          break;
      }
    },
    [
      handleStreamStart,
      handleStreamChunk,
      handleStreamEnd,
      handleStreamCancelled,
      handleToolCallStart,
      handleToolCallState,
      handleToolCallEnd,
      handleWsError,
      currentConversationId,
      updateConversationTitle,
    ],
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

        const fileLabel = `[Arquivo anexado: ${result.filename} (${result.file_type})]`;
        const fullMessage = text ? `${fileLabel}\n${text}` : fileLabel;

        addUserMessage(fullMessage);
        sendMessage(fullMessage, [
          {
            document_id: result.id,
            filename: result.filename,
            file_type: result.file_type,
          },
        ]);

        // Reset file + input
        setAttachedFile(null);
        setUploadProgress(null);
        setUploadError(null);
        setInputValue('');
      } catch (err) {
        setUploadProgress(null);
        const msg = getErrorMessage(err);
        setUploadError(msg);
        // Detectar codigo de limite de plano na resposta HTTP
        const limitCode = extractLimitCode(err);
        handleWsError(`Upload falhou: ${msg}`, limitCode ?? undefined);
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

  // ---- Derived state ----

  const isUploading = uploadProgress !== null && uploadProgress < 100;
  const canSend =
    isConnected &&
    !isStreaming &&
    !isUploading &&
    (!!inputValue.trim() || (attachedFile !== null && uploadError === null));

  // ---- Render helpers ----

  function renderMessage(msg: IMessage, msgIndex: number) {
    const isLastMessage = msgIndex === messages.length - 1;
    const isUser = msg.role === 'user';
    const metadata =
      msg.metadata && typeof msg.metadata === 'object' && !Array.isArray(msg.metadata)
        ? (msg.metadata as Record<string, unknown>)
        : null;
    const metaToolCalls = metadata?.tool_calls as Array<{
      tool: string;
      input?: string;
      result_preview?: string;
      duration_ms?: number;
      status?: 'queued' | 'running' | 'progress' | 'completed' | 'failed' | 'awaiting_confirmation';
      progress_pct?: number;
      elapsed_ms?: number;
      eta_ms?: number | null;
      detail?: string;
    }> | undefined;
    const resolvedAttachment = (metadata?.attachment_context as Record<string, unknown> | undefined)
      ?.resolved_attachment as
      | {
          filename?: string;
          file_type?: string;
        }
      | undefined;
    const llmExecution = metadata?.llm_execution as Record<string, unknown> | undefined;
    const selectedProvider =
      typeof llmExecution?.selected_provider === 'string'
        ? llmExecution.selected_provider
        : null;
    const selectedModel =
      typeof llmExecution?.selected_model === 'string'
        ? llmExecution.selected_model
        : null;
    const msgUsingFreeLlm = llmExecution?.using_free_llm === true;
    const fallbackTriggered = llmExecution?.fallback_triggered === true;
    const hasPcapTool = metaToolCalls?.some((tc) => tc.tool === 'analyze_pcap');

    return (
      <div key={msg.id} className={`message-row ${isUser ? 'message-row--user' : 'message-row--assistant'}`}>
        {/* Tool calls from historical messages */}
        {!isUser && metaToolCalls && metaToolCalls.length > 0 && (() => {
          const hasAwaitingConfirmation = metaToolCalls.some(
            (tc) => tc.status === 'awaiting_confirmation',
          );
          return (
            <ToolCallDisplay
              toolCalls={metaToolCalls.map((tc, i) => ({
                id: `hist-${msg.id}-${i}`,
                toolName: tc.tool,
                toolInput: tc.input ?? '',
                resultPreview: tc.result_preview,
                durationMs: tc.duration_ms,
                status: tc.status ?? ('completed' as const),
                progressPct: tc.progress_pct,
                elapsedMs: tc.elapsed_ms,
                etaMs: tc.eta_ms,
                detail: tc.detail,
              }))}
              messageId={hasPcapTool ? msg.id : undefined}
              onConfirm={isLastMessage && hasAwaitingConfirmation ? () => {
                addUserMessage('confirmo');
                sendMessage('confirmo');
              } : undefined}
            />
          );
        })()}
        <div className={`message-block ${isUser ? 'message-block--user' : 'message-block--assistant'}`}>
          <p className="message-role">
            {isUser ? (
              <>
                <svg className="message-role-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                Voce
              </>
            ) : (
              <>
                <svg className="message-role-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                NetGuru
              </>
            )}
          </p>
          {isUser ? (
            <div className="message-content">{msg.content}</div>
          ) : (
            <>
              {resolvedAttachment?.filename && (
                <p className="message-context-file">
                  Arquivo usado: {resolvedAttachment.filename}
                  {resolvedAttachment.file_type ? ` (${resolvedAttachment.file_type})` : ''}
                </p>
              )}
              {selectedProvider && !msgUsingFreeLlm && (
                <p className="message-llm-meta">
                  Modelo ativo: {selectedProvider}
                  {selectedModel ? ` / ${selectedModel}` : ''}
                  {fallbackTriggered ? ' (fallback)' : ''}
                </p>
              )}
              <MarkdownContent content={msg.content} />
              <EvidencePanel metadata={metadata} />
            </>
          )}
        </div>
      </div>
    );
  }

  if (!currentConversationId) {
    return <EmptyState onSuggestion={handleSuggestion} />;
  }

  return (
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
        <div className="chat-content-container">
          {messages.map((msg, idx) => renderMessage(msg, idx))}

          {/* Tool calls display */}
          {isStreaming && activeToolCalls.length > 0 && (
            <ToolCallDisplay
              toolCalls={activeToolCalls}
              messageId={streamingMessageId ?? undefined}
              onConfirm={() => {
                addUserMessage('confirmo');
                sendMessage('confirmo');
              }}
            />
          )}

          {/* Streaming block */}
          {isStreaming && streamingContent && (
            <div className="message-block message-block--assistant">
              <p className="message-role">
                <svg className="message-role-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                NetGuru
                {!usingFreeLlm && llmProvider && (
                  <span className="chip chip-byo-llm">{llmProvider}</span>
                )}
              </p>
              <MarkdownContent content={streamingContent} isStreaming />
              <span className="typing-cursor" />
            </div>
          )}

          {/* Waiting indicator (streaming started but no text yet) */}
          {isStreaming && !streamingContent && activeToolCalls.length === 0 && (
            <div className="message-block message-block--assistant">
              <p className="message-role">
                <svg className="message-role-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                NetGuru
                {!usingFreeLlm && llmProvider && (
                  <span className="chip chip-byo-llm">{llmProvider}</span>
                )}
              </p>
              <div className="message-content">
                <span className="typing-cursor" />
              </div>
            </div>
          )}

          {/* Error banner */}
          {error && (
            <div className={`error-banner chat-error${errorCode?.endsWith('_limit_exceeded') || errorCode === 'byo_required' ? ' chat-error--limit' : ''}`}>
              <span>{error}</span>
              <span className="chat-error-actions">
                {errorCode?.endsWith('_limit_exceeded') && (
                  <a href="/me" className="ghost-btn chat-upgrade-cta">
                    Fazer upgrade
                  </a>
                )}
                {(errorCode === 'byo_required' || errorCode === 'llm_not_configured') && (
                  <a href="/me" className="ghost-btn chat-upgrade-cta">
                    Configurar LLM
                  </a>
                )}
                <button type="button" className="ghost-btn chat-dismiss" onClick={clearError}>
                  fechar
                </button>
              </span>
            </div>
          )}

          <div />
        </div>
      </div>

      {/* Input wrapper — centralizado */}
      <div className="chat-input-wrapper">
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
      </div>
    </>
  );
}

export default ChatPage;
