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
  parse_show_commands: 'Analisando saida de comando',
  analyze_pcap: 'Analisando captura de pacotes',
};

interface ToolCallCardProps {
  toolCall: IToolCall;
}

function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isCompleted = toolCall.status === 'completed';
  const canExpand = isCompleted && (toolCall.toolInput || toolCall.resultPreview);

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
        <span
          className={`tool-call-indicator ${
            toolCall.status === 'running' ? 'tool-call-indicator--running' : 'tool-call-indicator--done'
          }`}
        />
        <span className="tool-call-name">
          {TOOL_LABELS[toolCall.toolName] ?? toolCall.toolName}
        </span>
        {isCompleted && toolCall.durationMs !== undefined && (
          <span className="tool-call-duration">{toolCall.durationMs}ms</span>
        )}
        {canExpand && (
          <span className={`tool-call-chevron ${expanded ? 'tool-call-chevron--open' : ''}`}>
            &#9654;
          </span>
        )}
      </div>

      {!expanded && isCompleted && toolCall.resultPreview && (
        <p className="tool-call-preview">{toolCall.resultPreview}</p>
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
