"""
Workspace service — CRUD e gerenciamento de membros.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember


class WorkspaceService:
    """Operacoes de workspace e membros."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_workspace(
        self,
        owner: User,
        name: str,
        *,
        plan_tier: str = "free",
    ) -> Workspace:
        """
        Cria workspace, adiciona owner como membro, e seta como workspace ativo.

        Args:
            owner: Usuario dono do workspace.
            name: Nome do workspace.
            plan_tier: Tier do plano (default free).

        Returns:
            Workspace criado.
        """
        slug = uuid4().hex

        workspace = Workspace(
            id=uuid4(),
            name=name,
            slug=slug,
            owner_id=owner.id,
            plan_tier=plan_tier,
        )
        self.db.add(workspace)
        await self.db.flush()

        member = WorkspaceMember(
            id=uuid4(),
            workspace_id=workspace.id,
            user_id=owner.id,
            workspace_role="owner",
        )
        self.db.add(member)

        owner.active_workspace_id = workspace.id

        await self.db.flush()
        return workspace

    async def get_user_workspaces(self, user_id: UUID) -> list[Workspace]:
        """
        Lista workspaces onde o usuario e membro.

        Args:
            user_id: ID do usuario.

        Returns:
            Lista de workspaces.
        """
        stmt = (
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.created_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_workspace(self, workspace_id: UUID) -> Workspace | None:
        """
        Busca workspace por ID.

        Args:
            workspace_id: ID do workspace.

        Returns:
            Workspace ou None.
        """
        stmt = select(Workspace).where(Workspace.id == workspace_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_workspace_with_members(self, workspace_id: UUID) -> Workspace | None:
        """
        Busca workspace com membros pre-carregados.

        Args:
            workspace_id: ID do workspace.

        Returns:
            Workspace com members loaded ou None.
        """
        stmt = (
            select(Workspace)
            .options(selectinload(Workspace.members))
            .where(Workspace.id == workspace_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_workspace_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> WorkspaceMember | None:
        """
        Busca membership de um usuario em um workspace.

        Args:
            workspace_id: ID do workspace.
            user_id: ID do usuario.

        Returns:
            WorkspaceMember ou None.
        """
        stmt = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def invite_member(
        self,
        workspace_id: UUID,
        email: str,
        workspace_role: str,
        invited_by: UUID,
    ) -> WorkspaceMember:
        """
        Convida usuario existente para o workspace.

        Args:
            workspace_id: ID do workspace.
            email: Email do usuario a convidar.
            workspace_role: Role do membro (admin|member|viewer).
            invited_by: ID do usuario que convidou.

        Returns:
            WorkspaceMember criado.

        Raises:
            ValueError: Se usuario nao encontrado ou ja e membro.
        """
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        target_user = result.scalar_one_or_none()
        if target_user is None:
            raise ValueError(f"Usuario com email '{email}' nao encontrado")

        existing = await self.get_workspace_member(workspace_id, target_user.id)
        if existing is not None:
            raise ValueError("Usuario ja e membro deste workspace")

        member = WorkspaceMember(
            id=uuid4(),
            workspace_id=workspace_id,
            user_id=target_user.id,
            workspace_role=workspace_role,
            invited_by=invited_by,
        )
        self.db.add(member)
        await self.db.flush()
        return member

    async def remove_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        """
        Remove membro do workspace.

        Args:
            workspace_id: ID do workspace.
            user_id: ID do usuario a remover.

        Raises:
            ValueError: Se membro nao encontrado ou e o owner.
        """
        member = await self.get_workspace_member(workspace_id, user_id)
        if member is None:
            raise ValueError("Membro nao encontrado")

        if member.workspace_role == "owner":
            raise ValueError("Nao e possivel remover o owner do workspace")

        await self.db.delete(member)
        await self.db.flush()

    async def update_member_role(
        self,
        workspace_id: UUID,
        user_id: UUID,
        new_role: str,
    ) -> WorkspaceMember:
        """
        Atualiza role de um membro.

        Args:
            workspace_id: ID do workspace.
            user_id: ID do usuario.
            new_role: Novo role (admin|member|viewer).

        Returns:
            WorkspaceMember atualizado.

        Raises:
            ValueError: Se membro nao encontrado ou tentando alterar owner.
        """
        member = await self.get_workspace_member(workspace_id, user_id)
        if member is None:
            raise ValueError("Membro nao encontrado")

        if member.workspace_role == "owner":
            raise ValueError("Nao e possivel alterar role do owner via este metodo")

        member.workspace_role = new_role
        await self.db.flush()
        return member

    async def transfer_ownership(
        self,
        workspace_id: UUID,
        current_owner_id: UUID,
        new_owner_id: UUID,
    ) -> None:
        """
        Transfere ownership do workspace para outro membro.

        Args:
            workspace_id: ID do workspace.
            current_owner_id: ID do owner atual.
            new_owner_id: ID do novo owner.

        Raises:
            ValueError: Se membros nao encontrados ou nao e owner.
        """
        current_member = await self.get_workspace_member(workspace_id, current_owner_id)
        if current_member is None or current_member.workspace_role != "owner":
            raise ValueError("Somente o owner pode transferir ownership")

        new_member = await self.get_workspace_member(workspace_id, new_owner_id)
        if new_member is None:
            raise ValueError("Novo owner nao e membro do workspace")

        # Transferir
        current_member.workspace_role = "admin"
        new_member.workspace_role = "owner"

        # Atualizar owner_id no workspace
        workspace = await self.get_workspace(workspace_id)
        if workspace:
            workspace.owner_id = new_owner_id

        await self.db.flush()

    async def switch_workspace(
        self,
        user: User,
        workspace_id: UUID,
    ) -> Workspace:
        """
        Troca workspace ativo do usuario.

        Args:
            user: Usuario.
            workspace_id: ID do workspace alvo.

        Returns:
            Workspace ativado.

        Raises:
            ValueError: Se usuario nao e membro do workspace.
        """
        member = await self.get_workspace_member(workspace_id, user.id)
        if member is None:
            raise ValueError("Usuario nao e membro deste workspace")

        workspace = await self.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError("Workspace nao encontrado")

        user.active_workspace_id = workspace_id
        await self.db.flush()
        return workspace

    async def get_workspace_members_with_users(
        self,
        workspace_id: UUID,
    ) -> list[dict]:
        """
        Lista membros do workspace com dados do usuario.

        Args:
            workspace_id: ID do workspace.

        Returns:
            Lista de dicts com dados do membro + usuario.
        """
        stmt = (
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.joined_at)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        members = []
        for member, user in rows:
            members.append({
                "id": member.id,
                "workspace_id": member.workspace_id,
                "user_id": member.user_id,
                "email": user.email,
                "full_name": user.full_name,
                "workspace_role": member.workspace_role,
                "joined_at": member.joined_at,
            })
        return members
