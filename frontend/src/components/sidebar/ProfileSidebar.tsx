function ProfileSidebar() {
  return (
    <div className="sidebar-content">
      <div className="panel-top">
        <div className="sidebar-header">
          <p className="panel-section-label">Conta</p>
          <h3 className="sidebar-title">Perfil</h3>
          <p className="sidebar-desc">Dados pessoais, assinatura e configuracao LLM.</p>
        </div>
      </div>
      <nav className="sidebar-nav">
        <a href="#dados" className="sidebar-nav-link">Dados pessoais</a>
        <a href="#assinatura" className="sidebar-nav-link">Assinatura</a>
        <a href="#llm" className="sidebar-nav-link">Configuracao LLM</a>
      </nav>
    </div>
  );
}

export default ProfileSidebar;
