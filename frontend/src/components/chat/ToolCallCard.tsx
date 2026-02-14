/**
 * ToolCallCard — Card individual de tool call com expand/collapse.
 */
import { useState } from 'react';
import type { IToolCall } from '../../stores/chatStore';

const TOOL_LABELS: Record<string, string> = {
  search_rag_global: 'Buscando docs de vendors',
  search_rag_local: 'Buscando seus documentos',
  parse_config: 'Analisando configuracao',
  validate_config: 'Validando configuracao',
  diff_config_risk: 'Comparando running x golden',
  pre_change_review: 'Executando pre-change review',
  parse_show_commands: 'Analisando saida de comando',
  analyze_pcap: 'Analisando captura de pacotes',
};

interface ToolCallCardProps {
  toolCall: IToolCall;
  messageId?: string;
}

function ToolCallCard({ toolCall, messageId }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isCompleted = toolCall.status === 'completed';
  const isFailed = toolCall.status === 'failed';
  const isAwaitingConfirmation = toolCall.status === 'awaiting_confirmation';
  const isInProgress =
    toolCall.status === 'queued' || toolCall.status === 'running' || toolCall.status === 'progress';
  const canExpand = (isCompleted || isFailed) && (toolCall.toolInput || toolCall.resultPreview);
  const showDashboardLink = toolCall.toolName === 'analyze_pcap' && isCompleted && messageId;
  const progressValue = Math.max(0, Math.min(100, toolCall.progressPct ?? 0));
  const elapsedSeconds = toolCall.elapsedMs ? Math.max(0, Math.round(toolCall.elapsedMs / 1000)) : 0;
  const etaSeconds = toolCall.etaMs ? Math.max(0, Math.round(toolCall.etaMs / 1000)) : 0;
  const indicatorClass = isAwaitingConfirmation
    ? 'tool-call-indicator--awaiting'
    : isFailed
      ? 'tool-call-indicator--failed'
      : isCompleted
        ? 'tool-call-indicator--done'
        : 'tool-call-indicator--running';

  function handleToggle(): void {
    if (canExpand) {
      setExpanded((prev) => !prev);
    }
  }

  return (
    <div
      className={`tool-call-card ${canExpand ? 'tool-call-card--expandable' : ''}`}
      onClick={handleToggle}
    >
      <div className="tool-call-header">
        <span className={`tool-call-indicator ${indicatorClass}`} />
        <span className="tool-call-name">
          {TOOL_LABELS[toolCall.toolName] ?? toolCall.toolName}
        </span>
        {(isCompleted || isFailed) && toolCall.durationMs !== undefined && (
          <span className="tool-call-duration">{toolCall.durationMs}ms</span>
        )}
        {canExpand && (
          <span className={`tool-call-chevron ${expanded ? 'tool-call-chevron--open' : ''}`}>
            &#9654;
          </span>
        )}
      </div>

      {showDashboardLink && (
        <a
          href={`/pcap/${messageId}`}
          target="_blank"
          rel="noopener noreferrer"
          className="tool-call-dashboard-link"
          onClick={(e) => e.stopPropagation()}
        >
          Abrir Dashboard
        </a>
      )}

      {isInProgress && (
        <div className="tool-call-progress-wrap">
          <div className="tool-call-progress-track">
            <div
              className={`tool-call-progress-fill ${toolCall.status === 'queued' ? 'tool-call-progress-fill--queued' : ''}`}
              style={{ width: `${progressValue}%` }}
            />
          </div>
          <div className="tool-call-progress-meta">
            <span>
              {toolCall.status === 'queued'
                ? 'Na fila'
                : `Progresso ${progressValue}%`}
            </span>
            <span>
              {elapsedSeconds > 0 ? `${elapsedSeconds}s` : ''}
              {etaSeconds > 0 ? ` · ETA ${etaSeconds}s` : ''}
            </span>
          </div>
        </div>
      )}

      {isAwaitingConfirmation && toolCall.detail && (
        <p className="tool-call-preview">{toolCall.detail}</p>
      )}
      {!isAwaitingConfirmation && !expanded && (isCompleted || isFailed) && toolCall.resultPreview && (
        <p className="tool-call-preview">{toolCall.resultPreview}</p>
      )}
      {!isAwaitingConfirmation && !expanded && !toolCall.resultPreview && toolCall.detail && (
        <p className="tool-call-preview">{toolCall.detail}</p>
      )}

      {expanded && (
        <div className="tool-call-details">
          {toolCall.toolInput && (
            <>
              <p className="tool-call-detail-label">Input</p>
              <pre className="tool-call-detail-pre">{toolCall.toolInput}</pre>
            </>
          )}
          {toolCall.resultPreview && (
            <>
              <p className="tool-call-detail-label">Resultado</p>
              <pre className="tool-call-detail-pre">{toolCall.resultPreview}</pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default ToolCallCard;
