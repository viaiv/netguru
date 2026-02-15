interface GenericSidebarProps {
  title: string;
  subtitle: string;
}

function GenericSidebar({ title, subtitle }: GenericSidebarProps) {
  return (
    <div className="sidebar-content">
      <div className="panel-top">
        <div className="sidebar-header">
          <p className="panel-section-label">{title}</p>
          <p className="sidebar-desc">{subtitle}</p>
        </div>
      </div>
    </div>
  );
}

export default GenericSidebar;
