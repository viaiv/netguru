/**
 * ToolCallDisplay — Container de tool calls do agent.
 * Cada tool call e renderizado por ToolCallCard.
 */
import type { IToolCall } from '../../stores/chatStore';
import ToolCallCard from './ToolCallCard';

interface ToolCallDisplayProps {
  toolCalls: IToolCall[];
}

function ToolCallDisplay({ toolCalls }: ToolCallDisplayProps) {
  if (toolCalls.length === 0) return null;

  return (
    <div className="tool-calls-container">
      {toolCalls.map((tc) => (
        <ToolCallCard key={tc.id} toolCall={tc} />
      ))}
    </div>
  );
}

export default ToolCallDisplay;
