"""
EmbeddingService — Singleton que carrega SentenceTransformer e gera embeddings.
"""
from __future__ import annotations

import threading

from app.core.config import settings


class EmbeddingService:
    """
    Gerencia o modelo de embeddings como singleton thread-safe.

    Uso:
        svc = EmbeddingService.get_instance()
        vec = svc.encode("texto de exemplo")
    """

    _instance: EmbeddingService | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        raise RuntimeError("Use EmbeddingService.get_instance()")

    @classmethod
    def get_instance(cls) -> EmbeddingService:
        """Retorna singleton, carregando o modelo na primeira chamada."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = object.__new__(cls)
                    obj._init_model()
                    cls._instance = obj
        return cls._instance

    def _init_model(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(settings.EMBEDDING_MODEL)

    def encode(self, text: str) -> list[float]:
        """Gera embedding para um texto. Retorna lista de floats."""
        vector = self._model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Gera embeddings para uma lista de textos."""
        vectors = self._model.encode(texts, normalize_embeddings=True, batch_size=64)
        return [v.tolist() for v in vectors]
