"""
EmailService — envia emails transacionais via Mailtrap SDK e registra logs.

Uso sincronizado (Celery workers). Le configuracao do banco via get_sync_db().
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.email_log import EmailLog
from app.services.system_settings_service import SystemSettingsService

logger = logging.getLogger(__name__)


class EmailService:
    """Envia emails transacionais usando Mailtrap e registra cada envio."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._api_key: Optional[str] = None
        self._sender_email: Optional[str] = None
        self._sender_name: Optional[str] = None

    def _load_config(self) -> None:
        """Carrega configuracoes do banco."""
        self._api_key = SystemSettingsService.get_sync(self._db, "mailtrap_api_key")
        self._sender_email = (
            SystemSettingsService.get_sync(self._db, "mailtrap_sender_email")
            or "noreply@netguru.app"
        )
        self._sender_name = (
            SystemSettingsService.get_sync(self._db, "mailtrap_sender_name")
            or "NetGuru"
        )

    def is_configured(self) -> bool:
        """Verifica se o servico de email esta habilitado e configurado."""
        enabled = SystemSettingsService.get_sync(self._db, "email_enabled")
        if enabled != "true":
            return False
        self._load_config()
        return bool(self._api_key)

    # ------------------------------------------------------------------
    # Log helper
    # ------------------------------------------------------------------

    def _log(
        self,
        *,
        recipient_email: str,
        recipient_user_id: Optional[UUID],
        email_type: str,
        subject: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Persiste um registro de envio na tabela email_logs."""
        entry = EmailLog(
            recipient_email=recipient_email,
            recipient_user_id=recipient_user_id,
            email_type=email_type,
            subject=subject,
            status=status,
            error_message=error_message,
        )
        self._db.add(entry)
        self._db.flush()

    # ------------------------------------------------------------------
    # Envio
    # ------------------------------------------------------------------

    def _send(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        *,
        email_type: str,
        recipient_user_id: Optional[UUID] = None,
    ) -> None:
        """Envia email via Mailtrap SDK e registra o resultado."""
        import mailtrap as mt

        if not self._api_key:
            self._load_config()

        try:
            mail = mt.Mail(
                sender=mt.Address(email=self._sender_email, name=self._sender_name),
                to=[mt.Address(email=to_email)],
                subject=subject,
                html=html_body,
                category="transactional",
            )
            client = mt.MailtrapClient(token=self._api_key)
            client.send(mail)

            self._log(
                recipient_email=to_email,
                recipient_user_id=recipient_user_id,
                email_type=email_type,
                subject=subject,
                status="sent",
            )
            logger.info("Email enviado para %s: %s", to_email, subject)

        except Exception as exc:
            self._log(
                recipient_email=to_email,
                recipient_user_id=recipient_user_id,
                email_type=email_type,
                subject=subject,
                status="failed",
                error_message=str(exc)[:500],
            )
            raise

    def log_skipped(
        self,
        to_email: str,
        email_type: str,
        *,
        recipient_user_id: Optional[UUID] = None,
    ) -> None:
        """Registra que um email foi pulado (servico nao configurado)."""
        self._log(
            recipient_email=to_email,
            recipient_user_id=recipient_user_id,
            email_type=email_type,
            subject="(skipped)",
            status="skipped",
            error_message="email_not_configured",
        )

    # ------------------------------------------------------------------
    # Emails transacionais
    # ------------------------------------------------------------------

    def send_verification_email(
        self,
        to_email: str,
        token: str,
        *,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Envia email de verificacao de conta."""
        link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        subject = "Verifique seu email - NetGuru"
        html = _render_template(
            title="Verifique seu email",
            body=f"""
            <p>Ola!</p>
            <p>Obrigado por se cadastrar no <strong>NetGuru</strong>.</p>
            <p>Clique no botao abaixo para verificar seu email:</p>
            <div style="text-align:center;margin:30px 0">
              <a href="{link}"
                 style="background:#6366f1;color:#fff;padding:12px 32px;
                        border-radius:6px;text-decoration:none;font-weight:600;
                        display:inline-block">
                Verificar Email
              </a>
            </div>
            <p style="color:#888;font-size:13px">
              Este link expira em 24 horas. Se voce nao criou esta conta, ignore este email.
            </p>
            """,
        )
        self._send(
            to_email, subject, html,
            email_type="verification",
            recipient_user_id=user_id,
        )

    def send_password_reset_email(
        self,
        to_email: str,
        token: str,
        *,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Envia email de redefinicao de senha."""
        link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        subject = "Redefinir senha - NetGuru"
        html = _render_template(
            title="Redefinir senha",
            body=f"""
            <p>Ola!</p>
            <p>Recebemos uma solicitacao para redefinir sua senha no <strong>NetGuru</strong>.</p>
            <p>Clique no botao abaixo para criar uma nova senha:</p>
            <div style="text-align:center;margin:30px 0">
              <a href="{link}"
                 style="background:#6366f1;color:#fff;padding:12px 32px;
                        border-radius:6px;text-decoration:none;font-weight:600;
                        display:inline-block">
                Redefinir Senha
              </a>
            </div>
            <p style="color:#888;font-size:13px">
              Este link expira em 1 hora. Se voce nao solicitou a redefinicao, ignore este email.
            </p>
            """,
        )
        self._send(
            to_email, subject, html,
            email_type="password_reset",
            recipient_user_id=user_id,
        )

    def send_welcome_email(
        self,
        to_email: str,
        full_name: Optional[str] = None,
        *,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Envia email de boas-vindas apos verificacao."""
        greeting = f"Ola, {full_name}!" if full_name else "Ola!"
        link = f"{settings.FRONTEND_URL}/login"
        subject = "Bem-vindo ao NetGuru!"
        html = _render_template(
            title="Bem-vindo ao NetGuru!",
            body=f"""
            <p>{greeting}</p>
            <p>Sua conta foi verificada com sucesso. Voce ja pode comecar a usar o
            <strong>NetGuru</strong> — sua plataforma AI-powered para Network Operations.</p>
            <div style="text-align:center;margin:30px 0">
              <a href="{link}"
                 style="background:#6366f1;color:#fff;padding:12px 32px;
                        border-radius:6px;text-decoration:none;font-weight:600;
                        display:inline-block">
                Acessar Plataforma
              </a>
            </div>
            <p>Duvidas? Responda este email ou acesse nossa documentacao.</p>
            """,
        )
        self._send(
            to_email, subject, html,
            email_type="welcome",
            recipient_user_id=user_id,
        )

    def send_test_email(
        self,
        to_email: str,
        *,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Envia email de teste para validar configuracao."""
        subject = "Email de Teste - NetGuru"
        html = _render_template(
            title="Email de teste",
            body="""
            <p>Este e um email de teste enviado pelo painel admin do <strong>NetGuru</strong>.</p>
            <p>Se voce esta vendo esta mensagem, a configuracao do Mailtrap esta funcionando corretamente.</p>
            """,
        )
        self._send(
            to_email, subject, html,
            email_type="test",
            recipient_user_id=user_id,
        )


def _render_template(title: str, body: str) -> str:
    """Renderiza template HTML inline para emails transacionais."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0f0f23;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
  <div style="max-width:560px;margin:40px auto;background:#1a1a2e;border-radius:12px;
              border:1px solid rgba(99,102,241,0.2);overflow:hidden">
    <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:24px 32px">
      <h1 style="margin:0;color:#fff;font-size:20px">{title}</h1>
    </div>
    <div style="padding:32px;color:#e2e8f0;font-size:15px;line-height:1.6">
      {body}
    </div>
    <div style="padding:16px 32px;border-top:1px solid rgba(255,255,255,0.06);
                text-align:center;color:#64748b;font-size:12px">
      NetGuru &mdash; Agentic Network Console
    </div>
  </div>
</body>
</html>"""
