/**
 * WebSocket client for real-time chat streaming.
 */
import { getStoredAccessToken } from './api';

export type TWebSocketEventType =
  | 'stream_start'
  | 'stream_chunk'
  | 'stream_end'
  | 'stream_cancelled'
  | 'tool_call_start'
  | 'tool_call_state'
  | 'tool_call_end'
  | 'title_updated'
  | 'error'
  | 'pong';

export interface IWebSocketEvent {
  type: TWebSocketEventType;
  message_id?: string;
  content?: string;
  tokens_used?: number | null;
  metadata?: Record<string, unknown> | null;
  code?: string;
  detail?: string;
  tool_call_id?: string;
  tool_name?: string;
  tool_input?: string;
  status?: 'queued' | 'running' | 'progress' | 'completed' | 'failed';
  progress_pct?: number;
  elapsed_ms?: number;
  eta_ms?: number | null;
  result_preview?: string;
  duration_ms?: number;
  title?: string;
  reason?: string;
  using_free_llm?: boolean;
  llm_provider?: string;
}

export interface IOutgoingAttachmentRef {
  document_id: string;
  filename?: string;
  file_type?: string;
}

type TEventHandler = (event: IWebSocketEvent) => void;

function resolveWsUrl(conversationId: string): string {
  const apiUrl = (import.meta.env.VITE_API_URL?.trim() as string) || '';
  let base: string;

  if (apiUrl) {
    base = apiUrl.endsWith('/api/v1') ? apiUrl : `${apiUrl}/api/v1`;
  } else {
    const fallback = import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin;
    base = `${fallback}/api/v1`;
  }

  // http(s) → ws(s)
  base = base.replace(/^http/, 'ws');

  const token = getStoredAccessToken() ?? '';
  return `${base}/ws/chat/${conversationId}?token=${encodeURIComponent(token)}`;
}

export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private handler: TEventHandler;
  private onOpen: (() => void) | null = null;
  private onClose: ((code: number, reason: string) => void) | null = null;

  constructor(handler: TEventHandler) {
    this.handler = handler;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  connect(
    conversationId: string,
    onOpen?: () => void,
    onClose?: (code: number, reason: string) => void,
  ): void {
    this.disconnect();

    this.onOpen = onOpen ?? null;
    this.onClose = onClose ?? null;

    const url = resolveWsUrl(conversationId);
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.startPing();
      this.onOpen?.();
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data as string) as IWebSocketEvent;
        this.handler(data);
      } catch {
        // Ignore malformed messages
      }
    };

    this.ws.onclose = (event: CloseEvent) => {
      this.stopPing();
      this.onClose?.(event.code, event.reason);
    };

    this.ws.onerror = () => {
      // onclose fires after onerror, handled there
    };
  }

  sendMessage(content: string, attachments?: IOutgoingAttachmentRef[]): void {
    if (!this.isConnected) return;
    const payload: Record<string, unknown> = { type: 'message', content };
    if (attachments && attachments.length > 0) {
      payload.attachments = attachments;
    }
    this.ws!.send(JSON.stringify(payload));
  }

  sendCancel(): void {
    if (!this.isConnected) return;
    this.ws!.send(JSON.stringify({ type: 'cancel' }));
  }

  disconnect(): void {
    this.stopPing();
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
      this.ws = null;
    }
  }

  private startPing(): void {
    this.stopPing();
    this.pingInterval = setInterval(() => {
      if (this.isConnected) {
        this.ws!.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30_000);
  }

  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
}
