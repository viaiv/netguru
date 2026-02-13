/**
 * StatCard — dashboard metric card.
 */
interface IStatCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
}

function StatCard({ label, value, subtitle }: IStatCardProps) {
  return (
    <div className="stat-card kv-card">
      <p className="stat-card__label">{label}</p>
      <p className="stat-card__value">{value}</p>
      {subtitle && <p className="stat-card__subtitle">{subtitle}</p>}
    </div>
  );
}

export default StatCard;
