import pytest
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

import scripts.seed as seed_script
from app.auth.passwords import hash_password, verify_password
from app.models.gear import GearItem, GearKind
from app.models.trip import ChecklistItemKey, ChecklistStatus, Trip
from app.models.user import Unit, User, UserRole, UserStatus
from app.schemas.trip import SharedTripRead, TripRead
from app.services import trip as trip_service
from app.utils.config import settings
from scripts.seed import seed
from scripts.seed_data import (
    CARVERS_GAP,
    HIKER_CLOSET,
    METRIC_CLOSET,
    SHAKEDOWN_CRUISE,
    USERS,
)

# The seed password from .env, so the tests exercise the one you seed with (a weak one fails here). CI has
# no .env, so it falls back to a test-only value.
PASSWORD = (
    settings.seed_password
    if settings.seed_password and settings.seed_password.strip()
    else "test-only-ridgeline-cairn-7"
)


async def _count(session: AsyncSession, model: type[User | Trip | GearItem]) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _trips(session: AsyncSession, user: User) -> dict[str, Trip]:
    return {trip.name: trip for trip in await trip_service.list_trips(session, user.id)}


def test_every_trip_gear_name_is_in_the_closet() -> None:
    closet = {item.name for item in HIKER_CLOSET}
    for trip in (CARVERS_GAP, SHAKEDOWN_CRUISE):
        assert set(trip.gear) <= closet, trip.name


async def test_seed_creates_the_accounts(session: AsyncSession) -> None:
    result = await seed(session, PASSWORD)

    users = result.users
    assert set(users) == {u.username for u in USERS}
    assert all(verify_password(PASSWORD, user.password_hash) for user in users.values())
    assert users["admin"].role == UserRole.ADMIN
    assert users["blocked"].status == UserStatus.BLOCKED
    assert users["metric"].measurements == Unit.METRIC
    assert users["hiker"].measurements == Unit.IMPERIAL
    assert users["hiker"].body_weight_g == pytest.approx(86182.55, abs=0.01)  # 190 lb


async def test_seed_builds_the_hikers_closet_and_trips(session: AsyncSession) -> None:
    result = await seed(session, PASSWORD)
    hiker = result.users["hiker"]

    closet = {
        item.name: item
        for item in await session.scalars(select(GearItem).where(GearItem.user_id == hiker.id))
    }
    assert len(closet) == len(HIKER_CLOSET)
    assert closet["Backpack"].weight_g == pytest.approx(1026.3, abs=0.05)  # 36.2 oz
    assert closet["Fuel canister"].kind == GearKind.CONSUMABLE

    trips = await _trips(session, hiker)
    assert set(trips) == {CARVERS_GAP.name, SHAKEDOWN_CRUISE.name}

    carvers = trips[CARVERS_GAP.name]
    assert carvers.total_distance_m == 21243  # 13.2 mi
    assert carvers.elevation_gain_m == 974  # 3195 ft
    assert len(carvers.gear_list) == len(CARVERS_GAP.gear)
    assert all(gear.packed for gear in carvers.gear_list)
    assert carvers.food_plan is not None and carvers.food_plan.food == []
    assert carvers.share_token is None

    shakedown = trips[SHAKEDOWN_CRUISE.name]
    quantities = {gear.gear_item.name: gear.quantity for gear in shakedown.gear_list}
    assert quantities == SHAKEDOWN_CRUISE.gear
    assert not any(gear.packed for gear in shakedown.gear_list)
    assert shakedown.food_plan is not None
    assert sum(food.kcal for food in shakedown.food_plan.food) == 2365
    assert len(shakedown.notes) == len(SHAKEDOWN_CRUISE.notes)
    statuses = {item.item: item.status for item in shakedown.checklist_items}
    assert statuses[ChecklistItemKey.PERMIT] == ChecklistStatus.NOT_APPLICABLE
    assert statuses[ChecklistItemKey.WATER_SOURCES] == ChecklistStatus.DONE
    assert statuses[ChecklistItemKey.WEATHER_CHECKED] == ChecklistStatus.TODO

    # Serializes the way GET /trips returns it.
    for trip in trips.values():
        TripRead.model_validate(trip)


async def test_seed_shares_the_shakedown_with_its_sections(session: AsyncSession) -> None:
    result = await seed(session, PASSWORD)

    token = result.share_tokens[SHAKEDOWN_CRUISE.name]
    trip = await trip_service.get_shared_trip(session, token)
    assert trip is not None
    shared = SharedTripRead.from_trip(trip)
    assert shared.gear_list is not None and shared.food_plan is not None
    assert shared.checklist_items is not None
    assert shared.emergency_contact is None


async def test_seed_gives_the_metric_user_only_their_own_closet(session: AsyncSession) -> None:
    result = await seed(session, PASSWORD)
    metric = result.users["metric"]

    names = set(await session.scalars(select(GearItem.name).where(GearItem.user_id == metric.id)))
    assert names == {item.name for item in METRIC_CLOSET}
    assert await _trips(session, metric) == {}


async def test_seed_is_rerunnable_and_leaves_other_users_alone(session: AsyncSession) -> None:
    other = User(email="someone@example.org", username="someone", password_hash=hash_password(PASSWORD))
    session.add(other)
    await session.commit()
    first = await seed(session, PASSWORD)
    counts = [await _count(session, model) for model in (User, Trip, GearItem)]

    result = await seed(session, PASSWORD)

    assert [await _count(session, model) for model in (User, Trip, GearItem)] == counts
    assert (await session.execute(select(User).where(col(User.email) == "someone@example.org"))).scalar_one()
    # A rerun recreates the accounts, so a stale share link from the first run stops working.
    old_token = first.share_tokens[SHAKEDOWN_CRUISE.name]
    assert result.share_tokens[SHAKEDOWN_CRUISE.name] != old_token
    assert await trip_service.get_shared_trip(session, old_token) is None


async def test_seed_rejects_a_weak_password_before_touching_existing_accounts(session: AsyncSession) -> None:
    await seed(session, PASSWORD)
    counts = [await _count(session, model) for model in (User, Trip, GearItem)]

    with pytest.raises(ValidationError):
        await seed(session, "password")

    assert [await _count(session, model) for model in (User, Trip, GearItem)] == counts


def _fail_if_called(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("the seed must not start")


@pytest.mark.parametrize("password", [None, "", "   "], ids=["unset", "empty", "blank"])
def test_main_refuses_to_run_without_a_password(
    monkeypatch: pytest.MonkeyPatch, password: str | None
) -> None:
    monkeypatch.setattr(settings, "seed_password", password)
    monkeypatch.setattr(seed_script, "_main", _fail_if_called)
    monkeypatch.setattr("sys.argv", ["seed"])

    with pytest.raises(SystemExit) as exc:
        seed_script.main()

    assert exc.value.code == "Set SEED_PASSWORD in .env (or pass --password) to seed."


def test_main_refuses_a_blank_password_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "seed_password", PASSWORD)
    monkeypatch.setattr(seed_script, "_main", _fail_if_called)
    monkeypatch.setattr("sys.argv", ["seed", "--password", " "])

    with pytest.raises(SystemExit):
        seed_script.main()


@pytest.mark.parametrize(
    ("env_password", "argv"),
    [(PASSWORD, []), (None, ["--password", PASSWORD]), ("from-the-env-file", ["--password", PASSWORD])],
    ids=["env", "flag", "flag-overrides-env"],
)
def test_main_seeds_with_the_configured_password(
    monkeypatch: pytest.MonkeyPatch, env_password: str | None, argv: list[str]
) -> None:
    calls: list[tuple[str, bool]] = []

    async def _record(password: str, allow_remote: bool) -> None:
        calls.append((password, allow_remote))

    monkeypatch.setattr(settings, "seed_password", env_password)
    monkeypatch.setattr(seed_script, "_main", _record)
    monkeypatch.setattr("sys.argv", ["seed", *argv])

    seed_script.main()

    assert calls == [(PASSWORD, False)]
