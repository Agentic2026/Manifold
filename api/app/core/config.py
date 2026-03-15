from pydantic_settings import BaseSettings, SettingsConfigDict


# Drivers that require a synchronous connection
_SYNC_DRIVERS = ("+psycopg2", "+psycopg")
# Drivers that require an asynchronous connection
_ASYNC_DRIVERS = ("+asyncpg",)


def _to_asyncpg(url: str) -> str:
    """Return *url* with the driver replaced by asyncpg."""
    for driver in _SYNC_DRIVERS:
        if driver in url:
            return url.replace(driver, "+asyncpg")
    # bare postgresql:// with no driver suffix
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # already asyncpg (or unknown driver) – return as-is
    return url


def _to_psycopg(url: str) -> str:
    """Return *url* with the driver replaced by psycopg (sync)."""
    for driver in _ASYNC_DRIVERS:
        if driver in url:
            return url.replace(driver, "+psycopg")
    # bare postgresql:// with no driver suffix
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    # already a sync driver (or unknown) – return as-is
    return url


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
        """Async (asyncpg) URL derived from H4CKATH0N_DATABASE_URL."""
        return _to_asyncpg(self.h4ckath0n_database_url)


settings = Settings()


def get_sync_database_url() -> str:
    """Sync (psycopg) URL derived from H4CKATH0N_DATABASE_URL."""
    return _to_psycopg(settings.h4ckath0n_database_url)
