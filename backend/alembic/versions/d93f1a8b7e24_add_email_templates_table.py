"""add email_templates table

Revision ID: d93f1a8b7e24
Revises: 46b0f69aa27e
Create Date: 2026-02-13 20:35:00.000000

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'd93f1a8b7e24'
down_revision: Union[str, Sequence[str], None] = '46b0f69aa27e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Seed data — default templates extracted from EmailService hardcoded HTML
# ---------------------------------------------------------------------------

# Estilo do botao alinhado com a identidade visual da plataforma (brainwork)
_BTN = (
    "background:linear-gradient(110deg,#81d742,#a7e375);color:#17330d;"
    "padding:12px 32px;border-radius:12px;text-decoration:none;"
    "font-weight:700;display:inline-block;text-transform:uppercase;"
    "letter-spacing:0.06em;font-size:14px"
)

_TEMPLATES = [
    {
        "email_type": "verification",
        "subject": "Verifique seu email - NetGuru",
        "variables": [
            {"name": "action_url", "description": "Link de verificacao de email"},
        ],
        "body_html": f"""<p>Ola!</p>
<p>Obrigado por se cadastrar no <strong>NetGuru</strong>.</p>
<p>Clique no botao abaixo para verificar seu email:</p>
<div style="text-align:center;margin:30px 0">
  <a href="{{{{action_url}}}}" style="{_BTN}">
    Verificar Email
  </a>
</div>
<p style="color:#4c5448;font-size:13px">
  Este link expira em 24 horas. Se voce nao criou esta conta, ignore este email.
</p>""",
    },
    {
        "email_type": "password_reset",
        "subject": "Redefinir senha - NetGuru",
        "variables": [
            {"name": "action_url", "description": "Link para redefinir senha"},
        ],
        "body_html": f"""<p>Ola!</p>
<p>Recebemos uma solicitacao para redefinir sua senha no <strong>NetGuru</strong>.</p>
<p>Clique no botao abaixo para criar uma nova senha:</p>
<div style="text-align:center;margin:30px 0">
  <a href="{{{{action_url}}}}" style="{_BTN}">
    Redefinir Senha
  </a>
</div>
<p style="color:#4c5448;font-size:13px">
  Este link expira em 1 hora. Se voce nao solicitou a redefinicao, ignore este email.
</p>""",
    },
    {
        "email_type": "welcome",
        "subject": "Bem-vindo ao NetGuru!",
        "variables": [
            {"name": "user_name", "description": "Nome do usuario (ou 'Ola!' se vazio)"},
            {"name": "action_url", "description": "Link para login na plataforma"},
        ],
        "body_html": f"""<p>{{{{user_name}}}}</p>
<p>Sua conta foi verificada com sucesso. Voce ja pode comecar a usar o
<strong>NetGuru</strong> — sua plataforma AI-powered para Network Operations.</p>
<div style="text-align:center;margin:30px 0">
  <a href="{{{{action_url}}}}" style="{_BTN}">
    Acessar Plataforma
  </a>
</div>
<p>Duvidas? Responda este email ou acesse nossa documentacao.</p>""",
    },
    {
        "email_type": "test",
        "subject": "Email de Teste - NetGuru",
        "variables": [
            {"name": "user_name", "description": "Nome do admin que enviou o teste"},
        ],
        "body_html": """<p>Este e um email de teste enviado pelo painel admin do <strong>NetGuru</strong>.</p>
<p>Se voce esta vendo esta mensagem, a configuracao do Mailtrap esta funcionando corretamente.</p>""",
    },
]


def upgrade() -> None:
    """Upgrade schema."""
    email_templates = op.create_table(
        'email_templates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email_type', sa.String(length=50), nullable=False,
                   comment='verification|password_reset|welcome|test'),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('variables', JSONB(), nullable=False, server_default='[]'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email_type'),
    )
    op.create_index(op.f('ix_email_templates_email_type'), 'email_templates', ['email_type'], unique=True)
    op.create_index(op.f('ix_email_templates_id'), 'email_templates', ['id'], unique=False)

    # Seed default templates
    from datetime import datetime
    now = datetime.utcnow()
    op.bulk_insert(email_templates, [
        {
            "id": str(uuid4()),
            "email_type": t["email_type"],
            "subject": t["subject"],
            "body_html": t["body_html"],
            "variables": t["variables"],
            "is_active": True,
            "updated_at": now,
            "updated_by": None,
        }
        for t in _TEMPLATES
    ])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_email_templates_id'), table_name='email_templates')
    op.drop_index(op.f('ix_email_templates_email_type'), table_name='email_templates')
    op.drop_table('email_templates')
