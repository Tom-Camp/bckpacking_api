# 🥾 ⛰️ BckPack.ing 🏕️ 🌳

BckPack.ing is a site for planning backpacking trips with food calculations and gear lists
and other checklists. It doesn't provide the functionality that GaiaGPS or other trail mapping
apps provide, but instead is for logistics and planning.

### Trips

A registered user can create Trips for their upcoming backpacking trip. The Trip allows the user
to plan their food 🍲, their equipment ⛺, and to keep track of their logistics such as scheduling a
shuttle 🚐 or checking the forecast ⛈️.

#### Overview

Create a Trip. Give it a name and add a description, notes and some basic info like start and end
dates, start and end trailheads, total miles and elevation, maybe provide link to their GaiaGPS
route. Overview fields include:

* Start date
* End date
* Starting trailhead
* Ending trailhead
* Total distance
* Elevation gain
* Map link
* Emergency contact

There is also a checklist to ensure that you didn't forget anything before hitting the trial:

* ✅ Permit required
* ✅ Water sources checked
* ✅ Resupply points noted
* ❌ Shuttle scheduled
* ✅ Weather checked
* ❌ Cell coverage checked
* ✅ Offline map downloaded
* ✅ Fire restriction
* ❌ Was the route shared

#### Food planner

Calculate the calories need for the trip and plan your food accordingly. The food planner will
total up your calories as well as the weight of your food, which will then be used to calculate
your total pack weight.

#### Gear planner

Add and categorize you gear so that you can get an accurate calculation of your pack weight, as
well as to ensure that you don't forget something really important like that raincoat you forgot
the last time out.

---

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
