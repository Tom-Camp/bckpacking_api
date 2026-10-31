from urllib.parse import quote

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    admin_email: str | None = None

    cors_origins: list[str] | None = None

    log_level: str = "INFO"
    json_logs: bool = False

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Email via Resend. Without a key, services/email logs messages instead of sending them.
    resend_api_key: SecretStr | None = None
    # Must be an address on the domain verified in Resend
    email_from: str = "bckpack.ing <no-reply@reset.bckpack.ing>"
    # The UI origin that links in emails point to. The API runs behind nginx, so it can't work this out
    # from the request.
    app_base_url: str = "http://localhost:5173"

    # Dev only: the password for the accounts scripts/seed.py creates. The script refuses to run without
    # it, so never set it on a server.
    seed_password: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        # Percent-encode the credentials so "@", "/", ":", "#", "?" or "%" in them can't break the URL
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
