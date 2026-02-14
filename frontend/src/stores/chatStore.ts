/**
 * Zustand store for chat state management.
 */
import { create } from 'zustand';
import { api, getErrorMessage } from '../services/api';

export interface IConversation {
  id: string;
  user_id: string;
  title: string;
  model_used: string | null;
  created_at: string;
  updated_at: string;
}

export interface IMessage {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  tokens_used: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface IToolCall {
  id: string;
  toolName: string;
  toolInput: string;
  resultPreview?: string;
  durationMs?: number;
  status: 'running' | 'completed';
}

interface IChatState {
  // Data
  conversations: IConversation[];
  currentConversationId: string | null;
  messages: IMessage[];

  // Streaming
  isStreaming: boolean;
  streamingContent: string;
  streamingMessageId: string | null;

  // Tool calls
  activeToolCalls: IToolCall[];

  // Connection
  isConnected: boolean;

  // Error
  error: string | null;

  // REST actions
  fetchConversations: () => Promise<void>;
  createConversation: (title?: string) => Promise<IConversation | null>;
  deleteConversation: (id: string) => Promise<boolean>;
  renameConversation: (id: string, title: string) => Promise<boolean>;
  selectConversation: (id: string) => void;
  fetchMessages: (conversationId: string) => Promise<void>;

  // Title
  updateConversationTitle: (conversationId: string, title: string) => void;

  // WS actions
  addUserMessage: (content: string) => void;
  handleStreamStart: (messageId: string) => void;
  handleStreamChunk: (content: string) => void;
  handleStreamEnd: (messageId: string, tokensUsed: number | null) => void;
  handleStreamCancelled: () => void;
  handleToolCallStart: (toolCallId: string, toolName: string, toolInput: string) => void;
  handleToolCallEnd: (
    toolCallId: string,
    toolName: string,
    resultPreview: string,
    durationMs: number,
  ) => void;
  handleWsError: (detail: string) => void;
  setConnected: (connected: boolean) => void;
  clearError: () => void;
}

export const useChatStore = create<IChatState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  messages: [],
  isStreaming: false,
  streamingContent: '',
  streamingMessageId: null,
  activeToolCalls: [],
  isConnected: false,
  error: null,

  fetchConversations: async () => {
    try {
      const response = await api.get<IConversation[]>('/chat/conversations', {
        params: { limit: 50, offset: 0 },
      });
      set({ conversations: response.data, error: null });
    } catch (err) {
      set({ error: getErrorMessage(err) });
    }
  },

  createConversation: async (title?: string) => {
    try {
      const response = await api.post<IConversation>('/chat/conversations', {
        title: title || 'Nova Conversa',
      });
      const newConv = response.data;
      set((state) => ({
        conversations: [newConv, ...state.conversations],
        error: null,
      }));
      return newConv;
    } catch (err) {
      set({ error: getErrorMessage(err) });
      return null;
    }
  },

  deleteConversation: async (id: string) => {
    try {
      await api.delete(`/chat/conversations/${id}`);
      const wasCurrent = get().currentConversationId === id;
      set((state) => ({
        conversations: state.conversations.filter((c) => c.id !== id),
        ...(wasCurrent
          ? {
              currentConversationId: null,
              messages: [],
              streamingContent: '',
              streamingMessageId: null,
              isStreaming: false,
              activeToolCalls: [],
            }
          : {}),
        error: null,
      }));
      return true;
    } catch (err) {
      set({ error: getErrorMessage(err) });
      return false;
    }
  },

  renameConversation: async (id: string, title: string) => {
    try {
      const response = await api.patch<IConversation>(`/chat/conversations/${id}`, { title });
      const updated = response.data;
      set((state) => ({
        conversations: state.conversations.map((c) =>
          c.id === id ? { ...c, title: updated.title } : c,
        ),
        error: null,
      }));
      return true;
    } catch (err) {
      set({ error: getErrorMessage(err) });
      return false;
    }
  },

  selectConversation: (id: string) => {
    set({
      currentConversationId: id,
      messages: [],
      streamingContent: '',
      streamingMessageId: null,
      isStreaming: false,
      activeToolCalls: [],
      error: null,
    });
  },

  fetchMessages: async (conversationId: string) => {
    try {
      const response = await api.get<IMessage[]>(
        `/chat/conversations/${conversationId}/messages`,
      );
      set({ messages: response.data, error: null });
    } catch (err) {
      set({ error: getErrorMessage(err) });
    }
  },

  updateConversationTitle: (conversationId: string, title: string) => {
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === conversationId ? { ...c, title } : c,
      ),
    }));
  },

  addUserMessage: (content: string) => {
    const tempMsg: IMessage = {
      id: `temp-${Date.now()}`,
      conversation_id: get().currentConversationId ?? '',
      role: 'user',
      content,
      tokens_used: null,
      metadata: null,
      created_at: new Date().toISOString(),
    };
    set((state) => ({
      messages: [...state.messages, tempMsg],
      error: null,
    }));
  },

  handleStreamStart: (messageId: string) => {
    set({
      isStreaming: true,
      streamingContent: '',
      streamingMessageId: messageId,
      activeToolCalls: [],
    });
  },

  handleStreamChunk: (content: string) => {
    set((state) => ({
      streamingContent: state.streamingContent + content,
    }));
  },

  handleStreamEnd: (messageId: string, tokensUsed: number | null) => {
    const finalContent = get().streamingContent;
    const assistantMsg: IMessage = {
      id: messageId,
      conversation_id: get().currentConversationId ?? '',
      role: 'assistant',
      content: finalContent,
      tokens_used: tokensUsed,
      metadata: null,
      created_at: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, assistantMsg],
      isStreaming: false,
      streamingContent: '',
      streamingMessageId: null,
      activeToolCalls: [],
    }));
  },

  handleStreamCancelled: () => {
    set({
      isStreaming: false,
      streamingContent: '',
      streamingMessageId: null,
      activeToolCalls: [],
    });
  },

  handleToolCallStart: (toolCallId: string, toolName: string, toolInput: string) => {
    const resolvedToolCallId =
      toolCallId || `tc-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const newToolCall: IToolCall = {
      id: resolvedToolCallId,
      toolName,
      toolInput,
      status: 'running',
    };
    set((state) => ({
      activeToolCalls: [...state.activeToolCalls, newToolCall],
    }));
  },

  handleToolCallEnd: (
    toolCallId: string,
    toolName: string,
    resultPreview: string,
    durationMs: number,
  ) => {
    set((state) => {
      let matchedById = false;
      const updatedById = state.activeToolCalls.map((tc) => {
        if (!matchedById && tc.id === toolCallId && tc.status === 'running') {
          matchedById = true;
          return { ...tc, resultPreview, durationMs, status: 'completed' as const };
        }
        return tc;
      });

      if (matchedById || !toolName) {
        return { activeToolCalls: updatedById };
      }

      let matchedByName = false;
      const updatedByName = updatedById.map((tc) => {
        if (!matchedByName && tc.toolName === toolName && tc.status === 'running') {
          matchedByName = true;
          return { ...tc, resultPreview, durationMs, status: 'completed' as const };
        }
        return tc;
      });

      return { activeToolCalls: updatedByName };
    });
  },

  handleWsError: (detail: string) => {
    set({
      error: detail,
      isStreaming: false,
      streamingContent: '',
      streamingMessageId: null,
      activeToolCalls: [],
    });
  },

  setConnected: (connected: boolean) => {
    set({ isConnected: connected });
  },

  clearError: () => {
    set({ error: null });
  },
}));
