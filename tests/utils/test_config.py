import pytest
from alembic.config import Config
from sqlalchemy.engine import make_url

from app.utils.config import Settings

JWT_SECRET = "test"
PLAIN_PASSWORD = "secret"
SPECIAL_PASSWORD = "p@ss/w:rd%#?"


def _settings(user: str, password: str) -> Settings:
    return Settings(
        _env_file=None,  # don't read the developer's .env
        jwt_secret=JWT_SECRET,
        postgres_user=user,
        postgres_password=password,
        postgres_db="bp",
        postgres_host="db.example",
        postgres_port=6543,
    )


def test_database_url_plain_credentials_unchanged() -> None:
    url = _settings("bp", PLAIN_PASSWORD).database_url

    assert url == "postgresql+asyncpg://bp:secret@db.example:6543/bp"


@pytest.mark.parametrize(
    ("user", "password"),
    [("bp", SPECIAL_PASSWORD), ("b@p:user", PLAIN_PASSWORD), ("bp", "%41 space")],
)
def test_database_url_round_trips_special_characters(user: str, password: str) -> None:
    url = make_url(_settings(user, password).database_url)

    assert url.drivername == "postgresql+asyncpg"
    assert url.username == user
    assert url.password == password
    assert url.host == "db.example"
    assert url.port == 6543
    assert url.database == "bp"


def test_database_url_survives_alembic_interpolation() -> None:
    # migrations/env.py escapes "%" because set_main_option runs it through ConfigParser interpolation
    database_url = _settings("bp", SPECIAL_PASSWORD).database_url
    config = Config()

    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    assert config.get_main_option("sqlalchemy.url") == database_url
    assert config.get_section(config.config_ini_section, {})["sqlalchemy.url"] == database_url
