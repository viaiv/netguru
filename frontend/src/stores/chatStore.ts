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
  selectConversation: (id: string) => void;
  fetchMessages: (conversationId: string) => Promise<void>;

  // WS actions
  addUserMessage: (content: string) => void;
  handleStreamStart: (messageId: string) => void;
  handleStreamChunk: (content: string) => void;
  handleStreamEnd: (messageId: string, tokensUsed: number | null) => void;
  handleToolCallStart: (toolName: string, toolInput: string) => void;
  handleToolCallEnd: (toolName: string, resultPreview: string, durationMs: number) => void;
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

  handleToolCallStart: (toolName: string, toolInput: string) => {
    const newToolCall: IToolCall = {
      toolName,
      toolInput,
      status: 'running',
    };
    set((state) => ({
      activeToolCalls: [...state.activeToolCalls, newToolCall],
    }));
  },

  handleToolCallEnd: (toolName: string, resultPreview: string, durationMs: number) => {
    set((state) => ({
      activeToolCalls: state.activeToolCalls.map((tc) =>
        tc.toolName === toolName && tc.status === 'running'
          ? { ...tc, resultPreview, durationMs, status: 'completed' as const }
          : tc,
      ),
    }));
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
