import { useState } from 'react';

import { useChatStore } from '../../stores/chatStore';

interface ChatSidebarProps {
  onSelectConversation?: () => void;
}

function ChatSidebar({ onSelectConversation }: ChatSidebarProps) {
  const {
    conversations,
    currentConversationId,
    createConversation,
    deleteConversation,
    renameConversation,
    selectConversation,
  } = useChatStore();

  const [editingConvId, setEditingConvId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  async function handleNewConversation(): Promise<void> {
    const conv = await createConversation();
    if (conv) {
      selectConversation(conv.id);
      onSelectConversation?.();
    }
  }

  function handleSelectConversation(convId: string): void {
    selectConversation(convId);
    onSelectConversation?.();
  }

  async function handleDeleteConversation(e: React.MouseEvent, convId: string): Promise<void> {
    e.stopPropagation();
    await deleteConversation(convId);
  }

  function handleStartRename(e: React.MouseEvent, convId: string, currentTitle: string): void {
    e.stopPropagation();
    setEditingConvId(convId);
    setEditingTitle(currentTitle);
  }

  async function handleFinishRename(): Promise<void> {
    if (!editingConvId) return;
    const trimmed = editingTitle.trim();
    if (trimmed && trimmed.length <= 255) {
      await renameConversation(editingConvId, trimmed);
    }
    setEditingConvId(null);
    setEditingTitle('');
  }

  function handleRenameKeyDown(e: React.KeyboardEvent): void {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleFinishRename();
    } else if (e.key === 'Escape') {
      setEditingConvId(null);
      setEditingTitle('');
    }
  }

  return (
    <div className="sidebar-content">
      <div className="panel-top">
        <button type="button" className="panel-action-btn" onClick={handleNewConversation}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Nova conversa
        </button>
      </div>

      <div className="panel-section-header">
        <span className="panel-section-label">Todas as conversas</span>
      </div>

      <div className="conversation-list">
        {conversations.map((conv) => (
          <div
            key={conv.id}
            className={`conversation-item ${conv.id === currentConversationId ? 'conversation-item--active' : ''}`}
          >
            {editingConvId === conv.id ? (
              <div className="conversation-item-body">
                <input
                  className="conversation-title-input"
                  value={editingTitle}
                  onChange={(e) => setEditingTitle(e.target.value)}
                  onBlur={handleFinishRename}
                  onKeyDown={handleRenameKeyDown}
                  maxLength={255}
                  autoFocus
                />
              </div>
            ) : (
              <>
                <button
                  type="button"
                  className="conversation-item-body"
                  onClick={() => handleSelectConversation(conv.id)}
                >
                  <svg className="conversation-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  <span className="conversation-title">{conv.title}</span>
                  <span className="conversation-date">
                    {new Date(conv.updated_at).toLocaleDateString('pt-BR')}
                  </span>
                </button>
                <button
                  type="button"
                  className="conversation-action-btn conversation-rename-btn"
                  title="Renomear conversa"
                  onClick={(e) => handleStartRename(e, conv.id, conv.title)}
                >
                  &#9998;
                </button>
                <button
                  type="button"
                  className="conversation-action-btn conversation-delete-btn"
                  title="Excluir conversa"
                  onClick={(e) => handleDeleteConversation(e, conv.id)}
                >
                  &times;
                </button>
              </>
            )}
          </div>
        ))}
        {conversations.length === 0 && (
          <p className="chat-empty-hint">Nenhuma conversa ainda. Crie uma para comecar!</p>
        )}
      </div>
    </div>
  );
}

export default ChatSidebar;
