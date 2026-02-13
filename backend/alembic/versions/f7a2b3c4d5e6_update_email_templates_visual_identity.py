"""update email templates visual identity

Revision ID: f7a2b3c4d5e6
Revises: d93f1a8b7e24
Create Date: 2026-02-13 20:50:00.000000

Alinha os body_html dos 4 templates com a identidade visual
da plataforma (brainwork): verde accent #81d742, botoes com
gradiente, border-radius 12px, texto escuro #1f1f1f.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f7a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'd93f1a8b7e24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Estilo compartilhado do botao (identidade visual da plataforma)
_BTN = (
    "background:linear-gradient(110deg,#81d742,#a7e375);color:#17330d;"
    "padding:12px 32px;border-radius:12px;text-decoration:none;"
    "font-weight:700;display:inline-block;text-transform:uppercase;"
    "letter-spacing:0.06em;font-size:14px"
)

_TEMPLATES = {
    "verification": f"""<p>Ola!</p>
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

    "password_reset": f"""<p>Ola!</p>
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

    "welcome": f"""<p>{{{{user_name}}}}</p>
<p>Sua conta foi verificada com sucesso. Voce ja pode comecar a usar o
<strong>NetGuru</strong> — sua plataforma AI-powered para Network Operations.</p>
<div style="text-align:center;margin:30px 0">
  <a href="{{{{action_url}}}}" style="{_BTN}">
    Acessar Plataforma
  </a>
</div>
<p>Duvidas? Responda este email ou acesse nossa documentacao.</p>""",

    "test": """<p>Este e um email de teste enviado pelo painel admin do <strong>NetGuru</strong>.</p>
<p>Se voce esta vendo esta mensagem, a configuracao do Mailtrap esta funcionando corretamente.</p>""",
}


def upgrade() -> None:
    """Atualiza body_html dos templates para a nova identidade visual."""
    conn = op.get_bind()
    for email_type, body_html in _TEMPLATES.items():
        conn.execute(
            sa.text(
                "UPDATE email_templates SET body_html = :body WHERE email_type = :etype"
            ),
            {"body": body_html, "etype": email_type},
        )


def downgrade() -> None:
    """Noop — templates podem ser reeditados via admin."""
    pass
