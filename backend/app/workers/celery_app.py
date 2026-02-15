"""
Celery application factory.

Configura broker, backend, serialização, limites e beat schedule.
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery("netguru")

celery_app.conf.update(
    # Broker / Backend
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    # Serialização
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Reliability
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Limites
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    # Resultados
    result_expires=3600,
    # Beat schedule file path (writeable in containers)
    beat_schedule_filename="/tmp/celerybeat-schedule",
)

# Registrar modulos de tasks explicitamente
celery_app.conf.include = [
    "app.workers.tasks.document_tasks",
    "app.workers.tasks.maintenance_tasks",
    "app.workers.tasks.pcap_tasks",
    "app.workers.tasks.email_tasks",
    "app.workers.tasks.billing_tasks",
    "app.workers.tasks.brainwork_tasks",
]

# Garantir que todos os models SQLAlchemy sao importados antes de qualquer task
# rodar, evitando falha de mapper initialization (ex: Topology nao encontrado).
import app.models  # noqa: F401, E402

# Registrar signal handlers para logging de task events
import app.workers.signals  # noqa: F401, E402

# Beat schedule — tarefas periodicas de manutencao
celery_app.conf.beat_schedule = {
    "cleanup-orphan-uploads": {
        "task": "app.workers.tasks.maintenance_tasks.cleanup_orphan_uploads",
        "schedule": settings.CLEANUP_ORPHAN_UPLOADS_HOURS * 3600,
    },
    "cleanup-expired-tokens": {
        "task": "app.workers.tasks.maintenance_tasks.cleanup_expired_tokens",
        "schedule": settings.CLEANUP_EXPIRED_TOKENS_HOURS * 3600,
    },
    "service-health-check": {
        "task": "app.workers.tasks.maintenance_tasks.service_health_check",
        "schedule": settings.HEALTH_CHECK_MINUTES * 60,
    },
    "recalculate-stale-embeddings": {
        "task": "app.workers.tasks.maintenance_tasks.recalculate_stale_embeddings",
        "schedule": settings.STALE_EMBEDDINGS_HOURS * 3600,
    },
    "mark-stale-tasks-timeout": {
        "task": "app.workers.tasks.maintenance_tasks.mark_stale_tasks_timeout",
        "schedule": 5 * 60,  # a cada 5 minutos
    },
    "downgrade-expired-trials": {
        "task": "app.workers.tasks.maintenance_tasks.downgrade_expired_trials",
        "schedule": settings.DOWNGRADE_EXPIRED_TRIALS_HOURS * 3600,
    },
    "reconcile-seat-quantities": {
        "task": "app.workers.tasks.billing_tasks.reconcile_seat_quantities",
        "schedule": settings.SEAT_RECONCILIATION_HOURS * 3600,
    },
    "check-byollm-discount-eligibility": {
        "task": "app.workers.tasks.billing_tasks.check_byollm_discount_eligibility",
        "schedule": settings.BYOLLM_CHECK_HOURS * 3600,
    },
    "crawl-brainwork-blog": {
        "task": "app.workers.tasks.brainwork_tasks.crawl_brainwork_blog",
        "schedule": settings.BRAINWORK_CRAWL_HOURS * 3600,
    },
}
