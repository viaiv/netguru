/**
 * ToolCallDisplay — Exibe tool calls do agent durante streaming.
 */
import type { IToolCall } from '../../stores/chatStore';

const TOOL_LABELS: Record<string, string> = {
  search_rag_global: 'Buscando docs de vendors',
  search_rag_local: 'Buscando seus documentos',
};

interface ToolCallDisplayProps {
  toolCalls: IToolCall[];
}

function ToolCallDisplay({ toolCalls }: ToolCallDisplayProps) {
  if (toolCalls.length === 0) return null;

  return (
    <div className="tool-calls-container">
      {toolCalls.map((tc, idx) => (
        <div key={`${tc.toolName}-${idx}`} className="tool-call-card">
          <div className="tool-call-header">
            <span className={`tool-call-indicator ${tc.status === 'running' ? 'tool-call-indicator--running' : 'tool-call-indicator--done'}`} />
            <span className="tool-call-name">
              {TOOL_LABELS[tc.toolName] ?? tc.toolName}
            </span>
            {tc.status === 'completed' && tc.durationMs !== undefined && (
              <span className="tool-call-duration">{tc.durationMs}ms</span>
            )}
          </div>
          {tc.status === 'completed' && tc.resultPreview && (
            <p className="tool-call-preview">{tc.resultPreview}</p>
          )}
        </div>
      ))}
    </div>
  );
}

export default ToolCallDisplay;
