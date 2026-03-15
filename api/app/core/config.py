from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    h4ckath0n_database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/manifold"
    cadvisor_metrics_api_token: str = "my-secret-token"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        """Return an asyncpg-compatible URL derived from H4CKATH0N_DATABASE_URL."""
        url = self.h4ckath0n_database_url
        # Replace sync drivers with asyncpg
        for sync_driver in ("+psycopg2", "+psycopg"):
            if sync_driver in url:
                return url.replace(sync_driver, "+asyncpg")
        if "postgresql://" in url and "+asyncpg" not in url:
            return url.replace("postgresql://", "postgresql+asyncpg://")
        return url


settings = Settings()


def get_sync_database_url() -> str:
    """Return a sync-compatible (psycopg) version of the database URL."""
    return settings.h4ckath0n_database_url
