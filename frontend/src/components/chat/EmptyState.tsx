/**
 * EmptyState — Tela de boas-vindas quando nenhuma conversa esta selecionada.
 */

interface EmptyStateProps {
  onSuggestion: (text: string) => void;
}

const SUGGESTIONS = [
  { title: 'Configurar OSPF', desc: 'Area 0, autenticacao, timers' },
  { title: 'Validar config Cisco', desc: 'Best practices e seguranca' },
  { title: 'Analisar topologia BGP', desc: 'Peers, AS-path, communities' },
  { title: 'OSPF vs EIGRP', desc: 'Comparativo de protocolos' },
];

function EmptyState({ onSuggestion }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <h2 className="empty-state-title">NetGuru Chat</h2>
      <p className="empty-state-subtitle">
        Seu assistente AI para engenharia de redes. Pergunte sobre configuracoes,
        protocolos, troubleshooting ou envie arquivos para analise.
      </p>
      <div className="empty-state-grid">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.title}
            type="button"
            className="empty-state-card"
            onClick={() => onSuggestion(s.title)}
          >
            <span className="empty-state-card-title">{s.title}</span>
            <span className="empty-state-card-desc">{s.desc}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default EmptyState;
