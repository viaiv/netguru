import { Link } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';

const FEATURES = [
  {
    icon: '\uD83D\uDCAC',
    title: 'Chat Inteligente',
    description: 'RAG Global com documentação curada de Cisco, Juniper e Arista. Respostas precisas com referências.',
  },
  {
    icon: '\uD83D\uDCE6',
    title: 'Análise de PCAPs',
    description: 'Upload de capturas de pacotes com diagnóstico automático, top talkers e detecção de anomalias.',
  },
  {
    icon: '\u2705',
    title: 'Validação de Configs',
    description: '15+ regras de best practices para segurança, confiabilidade e performance. Multi-vendor.',
  },
  {
    icon: '\uD83D\uDDFA\uFE0F',
    title: 'Topologia Visual',
    description: 'Geração automática de diagramas de rede a partir de configs e show commands.',
  },
  {
    icon: '\uD83D\uDD10',
    title: 'BYO-LLM',
    description: 'Traga sua API Key (OpenAI, Anthropic, Azure). Seus dados nunca saem da sua infraestrutura.',
  },
  {
    icon: '\uD83D\uDCC2',
    title: 'RAG Local',
    description: 'Indexe sua documentação interna, runbooks e templates. Contexto personalizado para sua infra.',
  },
];

const STEPS = [
  {
    number: '01',
    title: 'Traga sua API Key',
    description: 'Configure sua chave OpenAI, Anthropic ou Azure. Total controle sobre custos e privacidade.',
  },
  {
    number: '02',
    title: 'Pergunte ou envie arquivos',
    description: 'Chat em linguagem natural, upload de PCAPs, configs ou outputs de show commands.',
  },
  {
    number: '03',
    title: 'Agent analisa e responde',
    description: 'O agent seleciona as tools certas, consulta documentação e entrega diagnósticos acionáveis.',
  },
];

const PLANS = [
  {
    name: 'Solo Engineer',
    price: '$29-49',
    period: '/mês',
    features: ['1 usuário', 'RAG Global', 'Todas as tools', 'Suporte por email'],
    highlighted: false,
  },
  {
    name: 'Team / MSP',
    price: '$199',
    period: '/mês',
    features: ['Até 10 usuários', 'RAG Local', 'Topologia visual', 'Suporte prioritário'],
    highlighted: true,
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    period: 'licença anual',
    features: ['Usuários ilimitados', 'On-premise', 'SLA dedicado', 'Integração ITSM'],
    highlighted: false,
  },
];

function HomePage() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  return (
    <div className="landing">
      <div className="bg-grid" />
      <div className="bg-glow bg-glow-a" />
      <div className="bg-glow bg-glow-b" />

      {/* Nav */}
      <nav className="landing-nav">
        <span className="landing-nav-logo">NetGuru</span>
        <div className="landing-nav-actions">
          {isAuthenticated ? (
            <Link to="/chat" className="btn btn-primary">Ir ao Chat</Link>
          ) : (
            <>
              <Link to="/login" className="ghost-btn">Entrar</Link>
              <Link to="/register" className="btn btn-primary">Criar Conta</Link>
            </>
          )}
        </div>
      </nav>

      {/* Hero */}
      <section className="landing-hero">
        <p className="landing-hero-kicker">NetGuru</p>
        <h1 className="landing-hero-title">Agentic Network Console</h1>
        <p className="landing-hero-subtitle">
          Seu engenheiro de rede virtual com inteligência artificial. Diagnósticos, validações e automações
          para Cisco, Juniper e Arista — tudo via chat.
        </p>
        <div className="landing-hero-cta">
          {isAuthenticated ? (
            <Link to="/chat" className="btn btn-primary btn--lg">Ir ao Chat</Link>
          ) : (
            <>
              <Link to="/register" className="btn btn-primary btn--lg">Começar Agora</Link>
              <Link to="/login" className="ghost-btn btn--lg">Já tenho conta</Link>
            </>
          )}
        </div>
      </section>

      {/* Features */}
      <section className="landing-section">
        <h2 className="landing-section-title">Tudo que você precisa</h2>
        <p className="landing-section-subtitle">Ferramentas especializadas para operações de rede, orquestradas por um agent inteligente.</p>
        <div className="landing-features">
          {FEATURES.map((f) => (
            <div key={f.title} className="landing-feature-card">
              <span className="landing-feature-icon">{f.icon}</span>
              <h3 className="landing-feature-title">{f.title}</h3>
              <p className="landing-feature-desc">{f.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How It Works */}
      <section className="landing-section">
        <h2 className="landing-section-title">Como funciona</h2>
        <p className="landing-section-subtitle">Três passos para transformar sua operação de rede.</p>
        <div className="landing-steps">
          {STEPS.map((s) => (
            <div key={s.number} className="landing-step">
              <span className="landing-step-number">{s.number}</span>
              <h3 className="landing-step-title">{s.title}</h3>
              <p className="landing-step-desc">{s.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section className="landing-section">
        <h2 className="landing-section-title">Planos</h2>
        <p className="landing-section-subtitle">Escolha o plano ideal para sua operação.</p>
        <div className="landing-pricing">
          {PLANS.map((p) => (
            <div key={p.name} className={`landing-plan-card ${p.highlighted ? 'landing-plan-card--highlighted' : ''}`}>
              <h3 className="landing-plan-name">{p.name}</h3>
              <p className="landing-plan-price">
                {p.price}
                <span className="landing-plan-period">{p.period}</span>
              </p>
              <ul className="landing-plan-features">
                {p.features.map((feat) => (
                  <li key={feat}>{feat}</li>
                ))}
              </ul>
              <Link
                to={isAuthenticated ? '/chat' : '/register'}
                className={`btn ${p.highlighted ? 'btn-primary' : 'btn-secondary'} landing-plan-cta`}
              >
                {isAuthenticated ? 'Ir ao Chat' : 'Começar'}
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* Footer CTA */}
      <section className="landing-footer-cta">
        <h2 className="landing-section-title">Pronto para começar?</h2>
        <p className="landing-section-subtitle">
          Configure em minutos. Traga sua API Key e comece a usar agora.
        </p>
        {isAuthenticated ? (
          <Link to="/chat" className="btn btn-primary btn--lg">Ir ao Chat</Link>
        ) : (
          <Link to="/register" className="btn btn-primary btn--lg">Criar Conta Grátis</Link>
        )}
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        <span className="landing-footer-brand">NetGuru</span>
        <span className="landing-footer-copy">&copy; {new Date().getFullYear()} NetGuru. Todos os direitos reservados.</span>
      </footer>
    </div>
  );
}

export default HomePage;
