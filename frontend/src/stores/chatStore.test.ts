import { beforeEach, describe, expect, it } from 'vitest';

import { useChatStore } from './chatStore';

function resetChatStore(): void {
  useChatStore.setState({
    conversations: [],
    currentConversationId: 'conv-1',
    messages: [],
    isStreaming: false,
    streamingContent: '',
    streamingMessageId: null,
    activeToolCalls: [],
    isConnected: false,
    error: null,
  });
}

describe('useChatStore tool call correlation', () => {
  beforeEach(() => {
    resetChatStore();
  });

  it('matches tool_call_end by tool call id when tool names repeat', () => {
    const store = useChatStore.getState();

    store.handleToolCallStart('tc-1', 'parse_config', 'config A');
    store.handleToolCallStart('tc-2', 'parse_config', 'config B');
    store.handleToolCallEnd('tc-2', 'parse_config', 'parsed B', 45);

    const calls = useChatStore.getState().activeToolCalls;
    const first = calls.find((c) => c.id === 'tc-1');
    const second = calls.find((c) => c.id === 'tc-2');

    expect(first?.status).toBe('running');
    expect(first?.resultPreview).toBeUndefined();

    expect(second?.status).toBe('completed');
    expect(second?.resultPreview).toBe('parsed B');
    expect(second?.durationMs).toBe(45);
  });

  it('clears transient stream state on stream cancellation without appending assistant message', () => {
    useChatStore.setState({
      messages: [
        {
          id: 'temp-user-1',
          conversation_id: 'conv-1',
          role: 'user',
          content: 'hello',
          tokens_used: null,
          metadata: null,
          created_at: new Date().toISOString(),
        },
      ],
    });

    const store = useChatStore.getState();
    store.handleStreamStart('assistant-1');
    store.handleStreamChunk('partial answer');
    store.handleStreamCancelled();

    const next = useChatStore.getState();
    expect(next.isStreaming).toBe(false);
    expect(next.streamingContent).toBe('');
    expect(next.streamingMessageId).toBeNull();
    expect(next.activeToolCalls).toHaveLength(0);
    expect(next.messages).toHaveLength(1);
    expect(next.messages[0]?.role).toBe('user');
  });

  it('applies incremental tool_call_state updates with progress and failed status', () => {
    const store = useChatStore.getState();

    store.handleToolCallStart('tc-42', 'analyze_pcap', "{document_id:'x'}");
    store.handleToolCallState('tc-42', 'analyze_pcap', 'queued', 0, 0, null);
    store.handleToolCallState('tc-42', 'analyze_pcap', 'progress', 48, 12000, 13000);
    store.handleToolCallState('tc-42', 'analyze_pcap', 'failed', 48, 22000, null, 'timeout');
    store.handleToolCallEnd('tc-42', 'analyze_pcap', 'Error analyzing PCAP: timeout', 23000);

    const call = useChatStore.getState().activeToolCalls.find((c) => c.id === 'tc-42');
    expect(call).toBeDefined();
    expect(call?.status).toBe('failed');
    expect(call?.progressPct).toBe(48);
    expect(call?.elapsedMs).toBe(22000);
    expect(call?.detail).toBe('timeout');
    expect(call?.durationMs).toBe(23000);
  });
});
