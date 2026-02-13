"""
Application Configuration
Loads settings from environment variables using Pydantic Settings.
"""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """
    
    # Application
    APP_NAME: str = "NetGuru"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    UVICORN_PORT: int = 8000
    
    # Security
    SECRET_KEY: str
    FERNET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 0
    
    # Redis
    REDIS_URL: str
    REDIS_MAX_CONNECTIONS: int = 10
    
    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    
    # File Upload
    MAX_FILE_SIZE_MB: int = 100
    ALLOWED_FILE_EXTENSIONS: str = "pcap,pcapng,txt,conf,cfg,log,pdf,md"
    UPLOAD_DIR: str = "/app/uploads"
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # AI Providers
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    
    # RAG Settings
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    TOP_K_RESULTS: int = 5
    
    # Vector Store
    VECTOR_DIMENSION: int = 384
    USE_QDRANT: bool = False
    QDRANT_URL: str = "http://localhost:6333"
    
    # Agent
    AGENT_MAX_ITERATIONS: int = 5
    RAG_TOP_K_GLOBAL: int = 3
    RAG_TOP_K_LOCAL: int = 2
    RAG_MIN_SIMILARITY: float = 0.3

    # PCAP Analysis
    PCAP_MAX_PACKETS: int = 10000
    PCAP_ANALYSIS_TIMEOUT: int = 30  # seconds

    # Chat / Agent
    CHAT_HISTORY_LIMIT: int = 20
    CHAT_MAX_MESSAGE_LENGTH: int = 10000
    DEFAULT_LLM_MODEL_OPENAI: str = "gpt-4o"
    DEFAULT_LLM_MODEL_ANTHROPIC: str = "claude-sonnet-4-20250514"
    DEFAULT_LLM_MODEL_AZURE: str = "gpt-4o"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.7

    # Monitoring
    PROMETHEUS_ENABLED: bool = False
    SENTRY_DSN: str = ""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    @property
    def allowed_file_extensions_list(self) -> List[str]:
        """Parse allowed file extensions from comma-separated string"""
        return [ext.strip() for ext in self.ALLOWED_FILE_EXTENSIONS.split(",")]


# Singleton instance
settings = Settings()
