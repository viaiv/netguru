"""add byollm_grace_notified_at and seed discount warning template

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-02-15 23:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b7c8d9e0f1a2"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None

# Estilo do botao (identidade visual da plataforma)
_BTN = (
    "background:linear-gradient(110deg,#81d742,#a7e375);color:#17330d;"
    "padding:12px 32px;border-radius:12px;text-decoration:none;"
    "font-weight:700;display:inline-block;text-transform:uppercase;"
    "letter-spacing:0.06em;font-size:14px"
)

_BODY_HTML = f"""
<p>Ola, {{{{user_name}}}}!</p>
<p>Notamos que sua <strong>API key BYO-LLM</strong> foi removida da sua conta no
<strong>NetGuru</strong>.</p>
<p>Seu desconto BYO-LLM sera <strong>revogado automaticamente em {{{{grace_days}}}} dias</strong>
caso a chave nao seja reconfigurada.</p>
<div style="text-align:center;margin:30px 0">
  <a href="{{{{action_url}}}}"
     style="{_BTN}">
    Reconfigurar API Key
  </a>
</div>
<p style="color:#4c5448;font-size:13px">
  Se voce removeu intencionalmente a API key e nao deseja mais o desconto, nenhuma acao e necessaria.
</p>
"""


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "byollm_grace_notified_at",
            sa.DateTime(),
            nullable=True,
            comment="When BYO-LLM removal warning was sent; NULL = no pending grace",
        ),
    )

    # Seed email template for BYO-LLM discount warning
    op.execute(
        sa.text(
            """
            INSERT INTO email_templates (id, email_type, subject, body_html, variables, is_active, updated_at)
            VALUES (
                gen_random_uuid(),
                'byollm_discount_warning',
                'Seu desconto BYO-LLM sera revogado - NetGuru',
                :body_html,
                CAST(:variables AS jsonb),
                true,
                NOW()
            )
            ON CONFLICT (email_type) DO NOTHING
            """
        ).bindparams(
            body_html=_BODY_HTML,
            variables='[{"name": "user_name", "description": "Nome do usuario"}, '
            '{"name": "grace_days", "description": "Dias restantes do grace period"}, '
            '{"name": "action_url", "description": "Link para reconfigurar API key"}]',
        )
    )


def downgrade() -> None:
    op.execute("DELETE FROM email_templates WHERE email_type = 'byollm_discount_warning'")
    op.drop_column("subscriptions", "byollm_grace_notified_at")
