from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://selfops:password@postgres-postgresql.platform.svc.cluster.local:5432/selfops"
    redis_url: str = "redis://redis-master.platform.svc.cluster.local:6379"
    openrouter_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    environment: str = "production"
    log_level: str = "INFO"
    analysis_service_url: str = "http://selfops-analysis.platform.svc.cluster.local:8001"
    prometheus_url: str = "http://prometheus-operated.monitoring.svc.cluster.local:9090"
    loki_url: str = "http://loki.monitoring.svc.cluster.local:3100"

    class Config:
        env_file = ".env"


settings = Settings()
