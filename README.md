# 🥾 ⛰️ BckPack.ing 🏕️ 🌳

BckPack.ing is a site for planning backpacking trips with food calculations and gear lists
and other checklists. It doesn't provide the functionality that GaiaGPS or other trail mapping
apps provide, but instead is for logistics and planning.


## Tech Stack

- **Python 3.14** — managed with [uv](https://docs.astral.sh/uv/)
- **FastAPI** — async web framework
- **SQLModel** — ORM (SQLAlchemy + Pydantic)
- **PostgreSQL** — database
- **Alembic** — migrations
- **structlog** — structured logging

## Getting Started

### Prerequisites

- Docker (for Postgres)
- Python 3.14
- uv

### 1. Clone and install

```shell
git clone <repo>
cd bckpack.ing
uv sync
```

### 2. Configure environment

Copy the example .env and fill in your values:

```shell
cp .env.example .env
```

### 3. Start Postgres

```shell
docker compose up -d
```

### 4. Run migrations

```shell
uv run alembic upgrade head
```

### 5. Start the server

```shell
uv run uvicorn app.main:app --reload
```

API docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Maintainers

* [@Tom-Camp](https://github.com/Tom-Camp)

## License

[AGPL](LICENSE) © Tom Camp
