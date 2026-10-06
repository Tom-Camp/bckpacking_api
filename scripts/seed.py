"""Fill a development database with users, gear closets and trips.

    uv run python -m scripts.seed

Every seed account gets the password in SEED_PASSWORD (from .env) or --password, which must pass the same
strength check as registration. With neither set the script refuses to run, so a server without
SEED_PASSWORD can't be seeded whatever its POSTGRES_HOST. Re-running is safe: each seed account (matched by
email) is deleted first, which cascades to its trips and closet, then created again. Nothing else in the
database is touched. Writes go through the service layer so seeded rows get the same validation and
derived state as API writes.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from app.models.gear import GearItem
from app.models.trip import Trip
from app.models.user import User, UserRole, UserStatus
from app.schemas.gear import GearItemCreate
from app.schemas.trip import (
    ChecklistItemUpdate,
    TripCreate,
    TripFoodCreate,
    TripGearCreate,
    TripNoteCreate,
    TripUpdate,
)
from app.schemas.user import UserCreate, UserUpdate
from app.services import gear as gear_service
from app.services import trip as trip_service
from app.services import user as user_service
from app.utils.config import settings
from scripts.seed_data import (
    HIKER,
    HIKER_CLOSET,
    HIKER_TRIPS,
    METRIC_CLOSET,
    USERS,
    SeedGear,
    SeedTrip,
    SeedUser,
)

OZ_TO_G = 28.349523125
LB_TO_G = 453.59237
MI_TO_M = 1609.344
FT_TO_M = 0.3048

# Hosts a dev database is reached on: the compose service name, or a port published on this machine.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db"})


@dataclass
class SeedResult:
    users: dict[str, User]
    share_tokens: dict[str, str]


def _user_create(seed: SeedUser, password: str) -> UserCreate:
    return UserCreate(
        email=seed.email,
        password=password,
        username=seed.username,
        first_name=seed.first_name,
        last_name=seed.last_name,
    )


async def _create_user(session: AsyncSession, seed: SeedUser, data: UserCreate) -> User:
    user = await user_service.create_user(session, data)
    body_weight_g = seed.body_weight_lb * LB_TO_G if seed.body_weight_lb is not None else None
    user = await user_service.update_user(
        session, user, UserUpdate(measurements=seed.measurements, body_weight_g=body_weight_g)
    )
    if seed.role != UserRole.USER:
        user = await user_service.set_role(session, user, seed.role)
    if seed.status == UserStatus.BLOCKED:
        user = await user_service.suspend_user(session, user)
    return user


async def _create_closet(session: AsyncSession, user: User, items: list[SeedGear]) -> dict[str, GearItem]:
    closet = {}
    for item in items:
        closet[item.name] = await gear_service.create_item(
            session,
            user.id,
            GearItemCreate(
                name=item.name,
                category=item.category,
                weight_g=round(item.weight_oz * OZ_TO_G, 1),
                kind=item.kind,
                notes=item.notes,
            ),
        )
    return closet


async def _create_trip(
    session: AsyncSession, user: User, closet: dict[str, GearItem], seed: SeedTrip
) -> Trip:
    trip = await trip_service.create_trip(
        session,
        user.id,
        TripCreate(
            name=seed.name,
            description=seed.description,
            area=seed.area,
            trip_type=seed.trip_type,
            start_date=seed.start_date,
            end_date=seed.end_date,
            start_trailhead=seed.start_trailhead,
            end_trailhead=seed.end_trailhead,
            total_distance_m=round(seed.distance_mi * MI_TO_M),
            elevation_gain_m=round(seed.elevation_gain_ft * FT_TO_M),
            water_carry_l=seed.water_carry_l,
            map_link=seed.map_link,
            emergency_contact=seed.emergency_contact,
        ),
    )
    for name, quantity in seed.gear.items():
        await trip_service.add_trip_gear(
            session,
            trip.id,
            closet[name],
            TripGearCreate(gear_item_id=closet[name].id, quantity=quantity, packed=seed.gear_packed),
        )
    for key, status in seed.checklist.items():
        item = await trip_service.get_checklist_item(session, trip.id, key)
        if item is None:
            raise RuntimeError(f"Trip {seed.name!r} has no {key} checklist item")
        await trip_service.update_checklist_item(session, item, ChecklistItemUpdate(status=status))
    if seed.food:
        if trip.food_plan is None:
            raise RuntimeError(f"Trip {seed.name!r} has no food planner")
        for food in seed.food:
            await trip_service.add_food_item(
                session,
                trip.food_plan.id,
                TripFoodCreate(
                    day=food.day,
                    name=food.name,
                    meal_type=food.meal_type,
                    weight_g=round(food.weight_oz * OZ_TO_G, 1),
                    kcal=food.kcal,
                ),
            )
    for content in seed.notes:
        await trip_service.add_note(session, trip.id, TripNoteCreate(content=content))
    if seed.share_sections is not None:
        trip = await trip_service.update_trip(
            session, trip, TripUpdate.model_validate(dict.fromkeys(seed.share_sections, True))
        )
    return trip


async def seed(session: AsyncSession, password: str) -> SeedResult:
    # Validate every account (including the password's strength) before deleting the old ones.
    payloads = {seed_user.username: _user_create(seed_user, password) for seed_user in USERS}
    existing = await session.execute(select(User).where(col(User.email).in_([u.email for u in USERS])))
    for user in existing.scalars().all():
        await user_service.delete_user(session, user)

    users = {u.username: await _create_user(session, u, payloads[u.username]) for u in USERS}

    hiker = users[HIKER.username]
    closet = await _create_closet(session, hiker, HIKER_CLOSET)
    share_tokens = {}
    for seed_trip in HIKER_TRIPS:
        trip = await _create_trip(session, hiker, closet, seed_trip)
        if seed_trip.share_sections is not None:
            share_tokens[seed_trip.name] = await trip_service.enable_sharing(session, trip)

    await _create_closet(session, users["metric"], METRIC_CLOSET)
    return SeedResult(users=users, share_tokens=share_tokens)


async def _main(password: str, allow_remote: bool) -> None:
    # Imported here so nothing builds a database engine before the checks in main() pass.
    from app.db import engine

    if settings.postgres_host not in LOCAL_HOSTS and not allow_remote:
        sys.exit(
            f"Refusing to seed {settings.postgres_host!r}: not a local database. "
            "Pass --allow-remote-host if that's intended."
        )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            result = await seed(session, password)
    except ValidationError as exc:
        sys.exit(f"The seed password was rejected: {exc.errors()[0]['msg']}")
    finally:
        await engine.dispose()

    print(
        f"Seeded {settings.postgres_db} on {settings.postgres_host}. Every seed account uses the seed password."
    )
    for user in result.users.values():
        print(f"  {user.email:<22} {user.role.value:<6} {user.status.value:<8} {user.measurements.value}")
    for name, token in result.share_tokens.items():
        print(f"Share link for {name!r}: /shared#{token}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--password",
        default=settings.seed_password,
        help="password for every seed account (default: SEED_PASSWORD)",
    )
    parser.add_argument(
        "--allow-remote-host", action="store_true", help="seed even when POSTGRES_HOST isn't a local host"
    )
    args = parser.parse_args()
    # Checked before anything touches the database. Never fall back to a generated or built-in password:
    # a missing one is what keeps the seed from running on a server.
    if not args.password or not args.password.strip():
        sys.exit("Set SEED_PASSWORD in .env (or pass --password) to seed.")
    asyncio.run(_main(args.password, args.allow_remote_host))


if __name__ == "__main__":
    main()
