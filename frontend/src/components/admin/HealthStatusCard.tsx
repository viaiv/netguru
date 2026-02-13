/**
 * HealthStatusCard — card for service health status.
 */
import type { IServiceStatus } from '../../services/adminApi';

interface IHealthStatusCardProps {
  service: IServiceStatus;
}

function HealthStatusCard({ service }: IHealthStatusCardProps) {
  const statusClass = `health-card--${service.status}`;

  return (
    <div className={`health-card kv-card ${statusClass}`}>
      <div className="health-card__header">
        <span className={`health-card__dot health-card__dot--${service.status}`} />
        <h3 className="health-card__name">{service.name}</h3>
      </div>
      <p className="health-card__status">{service.status}</p>
      {service.latency_ms != null && (
        <p className="health-card__latency">{service.latency_ms} ms</p>
      )}
      {service.details && (
        <p className="health-card__details">{service.details}</p>
      )}
    </div>
  );
}

export default HealthStatusCard;
