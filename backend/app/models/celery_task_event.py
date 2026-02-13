"""
CeleryTaskEvent model — persistent log of Celery task executions.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID

from app.core.database import Base


class CeleryTaskEvent(Base):
    """
    Stores execution metadata for every Celery task invocation.

    Populated automatically by Celery signals (task_prerun / task_postrun / task_failure).
    """

    __tablename__ = "celery_task_events"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    task_id = Column(String(255), nullable=False, index=True, comment="UUID atribuido pelo Celery")
    task_name = Column(String(255), nullable=False, index=True, comment="Full dotted path da task")
    status = Column(String(20), nullable=False, index=True, comment="STARTED|SUCCESS|FAILURE|RETRY")
    args_summary = Column(String(500), nullable=True, comment="str(args)[:500] sanitizado")
    result_summary = Column(String(500), nullable=True, comment="str(retval)[:500]")
    error = Column(Text, nullable=True, comment="Traceback completo (truncado a 2000 chars)")
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    worker = Column(String(100), nullable=True, comment="Hostname do worker Celery")

    def __repr__(self) -> str:
        return (
            f"<CeleryTaskEvent(id={self.id}, task_name='{self.task_name}', "
            f"status='{self.status}')>"
        )
