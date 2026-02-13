/**
 * ConnectionStatus — Indicador de conexao WebSocket com reconexao.
 */

interface ConnectionStatusProps {
  isConnected: boolean;
  isReconnecting: boolean;
  reconnectAttempt: number;
  onRetry: () => void;
}

function ConnectionStatus({ isConnected, isReconnecting, reconnectAttempt, onRetry }: ConnectionStatusProps) {
  if (isConnected) {
    return (
      <span className="ws-status ws-status--online">
        Conectado
      </span>
    );
  }

  if (isReconnecting) {
    return (
      <span className="ws-status ws-status--reconnecting">
        Reconectando...
        <span className="ws-status-attempt">(tentativa {reconnectAttempt})</span>
      </span>
    );
  }

  return (
    <span className="ws-status ws-status--offline">
      Desconectado
      <button type="button" className="ws-status-retry" onClick={onRetry}>
        Reconectar
      </button>
    </span>
  );
}

export default ConnectionStatus;
