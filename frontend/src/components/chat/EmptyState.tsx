/**
 * EmptyState — Tela de boas-vindas quando nenhuma conversa esta selecionada.
 */

interface EmptyStateProps {
  onSuggestion: (text: string) => void;
}

const SUGGESTIONS = [
  'Como configurar OSPF area 0?',
  'Valide esta config Cisco',
  'Analise minha topologia BGP',
  'Diferenca entre OSPF e EIGRP',
];

function EmptyState({ onSuggestion }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <h2 className="empty-state-title">NetGuru Chat</h2>
      <p className="empty-state-subtitle">
        Seu assistente AI para engenharia de redes. Pergunte sobre configuracoes,
        protocolos, troubleshooting ou envie arquivos para analise.
      </p>
      <div className="empty-state-chips">
        {SUGGESTIONS.map((text) => (
          <button
            key={text}
            type="button"
            className="empty-state-chip"
            onClick={() => onSuggestion(text)}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}

export default EmptyState;
