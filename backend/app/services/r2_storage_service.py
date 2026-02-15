"""
R2StorageService — gerencia uploads/downloads no Cloudflare R2 (S3-compatible).

Fornece factories async (FastAPI) e sync (Celery) para carregar credenciais
do system_settings com Fernet encryption.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.services.system_settings_service import SystemSettingsService

logger = logging.getLogger(__name__)


class R2NotConfiguredError(Exception):
    """Credenciais R2 nao configuradas no system_settings."""


class R2OperationError(Exception):
    """Erro ao executar operacao no R2."""


class R2StorageService:
    """Cliente S3-compatible para Cloudflare R2."""

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ) -> None:
        self._bucket = bucket_name
        self._endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
        self._client = boto3.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=BotoConfig(
                signature_version="s3v4",
                retries={"max_attempts": 2, "mode": "standard"},
            ),
            region_name="auto",
        )

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    async def from_settings(cls, db: AsyncSession) -> R2StorageService:
        """
        Factory async — carrega credenciais do system_settings (FastAPI).

        Args:
            db: Sessao async do banco.

        Returns:
            Instancia configurada do R2StorageService.

        Raises:
            R2NotConfiguredError: Se alguma credencial obrigatoria estiver faltando.
        """
        account_id = await SystemSettingsService.get(db, "r2_account_id")
        access_key = await SystemSettingsService.get(db, "r2_access_key_id")
        secret_key = await SystemSettingsService.get(db, "r2_secret_access_key")
        bucket = await SystemSettingsService.get(db, "r2_bucket_name")

        if not all([account_id, access_key, secret_key, bucket]):
            raise R2NotConfiguredError(
                "Credenciais R2 incompletas. Configure account_id, access_key_id, "
                "secret_access_key e bucket_name nas configuracoes do sistema."
            )

        return cls(
            account_id=account_id,  # type: ignore[arg-type]
            access_key_id=access_key,  # type: ignore[arg-type]
            secret_access_key=secret_key,  # type: ignore[arg-type]
            bucket_name=bucket,  # type: ignore[arg-type]
        )

    @classmethod
    def from_settings_sync(cls, db: Session) -> R2StorageService:
        """
        Factory sync — carrega credenciais do system_settings (Celery).

        Args:
            db: Sessao sync do banco.

        Returns:
            Instancia configurada do R2StorageService.

        Raises:
            R2NotConfiguredError: Se alguma credencial obrigatoria estiver faltando.
        """
        account_id = SystemSettingsService.get_sync(db, "r2_account_id")
        access_key = SystemSettingsService.get_sync(db, "r2_access_key_id")
        secret_key = SystemSettingsService.get_sync(db, "r2_secret_access_key")
        bucket = SystemSettingsService.get_sync(db, "r2_bucket_name")

        if not all([account_id, access_key, secret_key, bucket]):
            raise R2NotConfiguredError(
                "Credenciais R2 incompletas. Configure no painel admin."
            )

        return cls(
            account_id=account_id,  # type: ignore[arg-type]
            access_key_id=access_key,  # type: ignore[arg-type]
            secret_access_key=secret_key,  # type: ignore[arg-type]
            bucket_name=bucket,  # type: ignore[arg-type]
        )

    # ------------------------------------------------------------------
    # Object key generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_object_key(user_id: UUID, extension: str) -> str:
        """
        Gera chave unica para objeto no R2.

        Args:
            user_id: UUID do usuario.
            extension: Extensao do arquivo (sem ponto).

        Returns:
            Chave no formato `uploads/{user_id}/{uuid}.{ext}`.
        """
        return f"uploads/{user_id}/{uuid4().hex}.{extension}"

    # ------------------------------------------------------------------
    # Presigned URLs
    # ------------------------------------------------------------------

    def generate_presigned_upload_url(
        self,
        object_key: str,
        content_type: str,
        expires_in: int = 600,
    ) -> str:
        """
        Gera URL presigned para PUT (upload direto do frontend).

        Args:
            object_key: Chave do objeto no bucket.
            content_type: MIME type do arquivo.
            expires_in: Tempo de validade em segundos (padrao 10min).

        Returns:
            URL presigned para upload PUT.

        Raises:
            R2OperationError: Se falhar ao gerar URL.
        """
        try:
            url = self._client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": object_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )
            return url
        except (BotoCoreError, ClientError) as e:
            raise R2OperationError(f"Falha ao gerar URL de upload: {e}") from e

    def generate_presigned_download_url(
        self,
        object_key: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Gera URL presigned para GET (download).

        Args:
            object_key: Chave do objeto no bucket.
            expires_in: Tempo de validade em segundos (padrao 1h).

        Returns:
            URL presigned para download GET.

        Raises:
            R2OperationError: Se falhar ao gerar URL.
        """
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": object_key,
                },
                ExpiresIn=expires_in,
            )
            return url
        except (BotoCoreError, ClientError) as e:
            raise R2OperationError(f"Falha ao gerar URL de download: {e}") from e

    # ------------------------------------------------------------------
    # Object operations
    # ------------------------------------------------------------------

    def head_object(self, object_key: str) -> dict[str, Any]:
        """
        Verifica existencia e retorna metadata do objeto.

        Args:
            object_key: Chave do objeto no bucket.

        Returns:
            Dict com ContentLength, ContentType, etc.

        Raises:
            R2OperationError: Se objeto nao existir ou erro de comunicacao.
        """
        try:
            response = self._client.head_object(
                Bucket=self._bucket,
                Key=object_key,
            )
            return {
                "content_length": response.get("ContentLength", 0),
                "content_type": response.get("ContentType", ""),
                "last_modified": response.get("LastModified"),
            }
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                raise R2OperationError(
                    f"Objeto '{object_key}' nao encontrado no R2."
                ) from e
            raise R2OperationError(f"Erro ao verificar objeto: {e}") from e
        except BotoCoreError as e:
            raise R2OperationError(f"Erro ao verificar objeto: {e}") from e

    def download_partial(self, object_key: str, byte_count: int = 8192) -> bytes:
        """
        Baixa os primeiros N bytes de um objeto no R2 (Range request).

        Args:
            object_key: Chave do objeto no bucket.
            byte_count: Numero de bytes a baixar (padrao 8KB).

        Returns:
            Bytes lidos do inicio do objeto.

        Raises:
            R2OperationError: Se falhar ao baixar.
        """
        try:
            response = self._client.get_object(
                Bucket=self._bucket,
                Key=object_key,
                Range=f"bytes=0-{byte_count - 1}",
            )
            return response["Body"].read()
        except (BotoCoreError, ClientError) as e:
            raise R2OperationError(f"Falha ao baixar bytes parciais: {e}") from e

    def download_to_tempfile(self, object_key: str, suffix: str) -> Path:
        """
        Baixa objeto do R2 para arquivo temporario.

        Args:
            object_key: Chave do objeto no bucket.
            suffix: Sufixo do arquivo temporario (ex: ".pcap").

        Returns:
            Path do arquivo temporario (caller deve deletar).

        Raises:
            R2OperationError: Se falhar ao baixar.
        """
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            self._client.download_fileobj(
                Bucket=self._bucket,
                Key=object_key,
                Fileobj=tmp,
            )
            tmp.close()
            return Path(tmp.name)
        except (BotoCoreError, ClientError) as e:
            raise R2OperationError(f"Falha ao baixar objeto: {e}") from e

    def upload_object(
        self,
        object_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """
        Faz upload de bytes diretamente para o R2.

        Args:
            object_key: Chave do objeto no bucket.
            data: Bytes do conteudo.
            content_type: MIME type do arquivo.

        Raises:
            R2OperationError: Se falhar ao fazer upload.
        """
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=object_key,
                Body=data,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as e:
            raise R2OperationError(f"Falha ao fazer upload: {e}") from e

    def delete_object(self, object_key: str) -> None:
        """
        Deleta objeto do R2.

        Args:
            object_key: Chave do objeto no bucket.

        Raises:
            R2OperationError: Se falhar ao deletar.
        """
        try:
            self._client.delete_object(
                Bucket=self._bucket,
                Key=object_key,
            )
        except (BotoCoreError, ClientError) as e:
            raise R2OperationError(f"Falha ao deletar objeto: {e}") from e

    def ensure_cors(self, allowed_origins: list[str] | None = None) -> None:
        """
        Configura regras CORS no bucket para permitir upload direto do browser.

        Args:
            allowed_origins: Lista de origens permitidas.
                Se nao informado, usa ["*"] (nao recomendado em producao).

        Raises:
            R2OperationError: Se falhar ao configurar CORS.
        """
        origins = allowed_origins or ["*"]
        if "*" in origins:
            import logging
            logging.getLogger(__name__).warning(
                "R2 CORS configurado com wildcard (*) — recomendado restringir em producao"
            )
        try:
            self._client.put_bucket_cors(
                Bucket=self._bucket,
                CORSConfiguration={
                    "CORSRules": [
                        {
                            "AllowedOrigins": origins,
                            "AllowedMethods": ["PUT", "GET", "HEAD"],
                            "AllowedHeaders": ["Content-Type", "Content-Length"],
                            "MaxAgeSeconds": 3600,
                        },
                    ],
                },
            )
        except (BotoCoreError, ClientError) as e:
            raise R2OperationError(f"Falha ao configurar CORS: {e}") from e

    def list_objects(self, max_keys: int = 1) -> list[dict[str, Any]]:
        """
        Lista objetos no bucket (usado para teste de conexao).

        Args:
            max_keys: Numero maximo de objetos a retornar.

        Returns:
            Lista de dicts com Key e Size.

        Raises:
            R2OperationError: Se falhar na comunicacao.
        """
        try:
            response = self._client.list_objects_v2(
                Bucket=self._bucket,
                MaxKeys=max_keys,
            )
            contents = response.get("Contents", [])
            return [{"key": obj["Key"], "size": obj["Size"]} for obj in contents]
        except (BotoCoreError, ClientError) as e:
            raise R2OperationError(f"Falha ao listar objetos: {e}") from e
