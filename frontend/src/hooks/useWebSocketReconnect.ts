/**
 * useWebSocketReconnect — Hook que encapsula lifecycle do WS com auto-reconnect.
 *
 * Exponential backoff: 1s, 2s, 4s, 8s, 16s (max 5 retries).
 * Reset do retry count apos conexao bem-sucedida.
 * Cleanup no unmount e troca de conversa.
 */
import { useRef, useEffect, useState, useCallback } from 'react';
import {
  ChatWebSocket,
  type IOutgoingAttachmentRef,
  type IWebSocketEvent,
} from '../services/websocket';

interface UseWebSocketReconnectOptions {
  conversationId: string | null;
  onEvent: (event: IWebSocketEvent) => void;
  maxRetries?: number;
  baseDelayMs?: number;
}

interface UseWebSocketReconnectReturn {
  isConnected: boolean;
  isReconnecting: boolean;
  reconnectAttempt: number;
  sendMessage: (content: string, attachments?: IOutgoingAttachmentRef[]) => void;
  sendCancel: () => void;
  manualRetry: () => void;
}

export function useWebSocketReconnect({
  conversationId,
  onEvent,
  maxRetries = 5,
  baseDelayMs = 1000,
}: UseWebSocketReconnectOptions): UseWebSocketReconnectReturn {
  const wsRef = useRef<ChatWebSocket | null>(null);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const conversationIdRef = useRef(conversationId);

  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  // Manter ref atualizada
  conversationIdRef.current = conversationId;

  const clearRetryTimeout = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    clearRetryTimeout();
    wsRef.current?.disconnect();
    wsRef.current = null;
    setIsConnected(false);
    setIsReconnecting(false);
    setReconnectAttempt(0);
    attemptRef.current = 0;
  }, [clearRetryTimeout]);

  const connect = useCallback(
    (convId: string) => {
      wsRef.current?.disconnect();

      const ws = new ChatWebSocket(onEvent);
      wsRef.current = ws;

      ws.connect(
        convId,
        () => {
          // onOpen — conexao bem-sucedida
          attemptRef.current = 0;
          setIsConnected(true);
          setIsReconnecting(false);
          setReconnectAttempt(0);
        },
        () => {
          // onClose — tentar reconectar
          setIsConnected(false);

          // So reconectar se ainda estamos na mesma conversa
          if (conversationIdRef.current !== convId) return;

          attemptRef.current += 1;
          const attempt = attemptRef.current;

          if (attempt > maxRetries) {
            setIsReconnecting(false);
            setReconnectAttempt(attempt);
            return;
          }

          setIsReconnecting(true);
          setReconnectAttempt(attempt);

          const delay = baseDelayMs * Math.pow(2, attempt - 1);
          retryTimeoutRef.current = setTimeout(() => {
            if (conversationIdRef.current === convId) {
              connect(convId);
            }
          }, delay);
        },
      );
    },
    [onEvent, maxRetries, baseDelayMs],
  );

  // Conectar/desconectar quando conversationId muda
  useEffect(() => {
    if (!conversationId) {
      disconnect();
      return;
    }

    attemptRef.current = 0;
    setReconnectAttempt(0);
    setIsReconnecting(false);
    connect(conversationId);

    return () => {
      disconnect();
    };
  }, [conversationId]); // eslint-disable-line react-hooks/exhaustive-deps

  const sendMessage = useCallback((content: string, attachments?: IOutgoingAttachmentRef[]) => {
    wsRef.current?.sendMessage(content, attachments);
  }, []);

  const sendCancel = useCallback(() => {
    wsRef.current?.sendCancel();
  }, []);

  const manualRetry = useCallback(() => {
    if (!conversationId) return;
    clearRetryTimeout();
    attemptRef.current = 0;
    setReconnectAttempt(0);
    setIsReconnecting(false);
    connect(conversationId);
  }, [conversationId, connect, clearRetryTimeout]);

  return { isConnected, isReconnecting, reconnectAttempt, sendMessage, sendCancel, manualRetry };
}
