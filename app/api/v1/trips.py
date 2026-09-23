import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_active_user
from app.db import get_session
from app.models.trip import ChecklistItemKey, Trip
from app.models.user import User
from app.schemas.trip import (
    ChecklistItemRead,
    ChecklistItemUpdate,
    FoodPlannerRead,
    FoodPlannerUpdate,
    TripCreate,
    TripFoodCreate,
    TripFoodRead,
    TripFoodUpdate,
    TripGearCreate,
    TripGearRead,
    TripGearUpdate,
    TripNoteCreate,
    TripNoteRead,
    TripNoteUpdate,
    TripRead,
    TripUpdate,
)
from app.services import gear as gear_service
from app.services import trip as trip_service

router = APIRouter(prefix="/trips", tags=["trips"])


async def get_owned_trip(
    trip_id: uuid.UUID,
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
) -> Trip:
    trip = await trip_service.get_trip(session, trip_id)
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    if trip.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your trip")
    return trip


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
async def create_trip(
    data: TripCreate,
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
) -> TripRead:
    trip = await trip_service.create_trip(session, user.id, data)
    return TripRead.model_validate(trip)


@router.get("", response_model=list[TripRead])
async def list_trips(
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
) -> list[TripRead]:
    trips = await trip_service.list_trips(session, user.id)
    return [TripRead.model_validate(t) for t in trips]


@router.get("/{trip_id}", response_model=TripRead)
async def get_trip(trip: Trip = Depends(get_owned_trip)) -> TripRead:
    return TripRead.model_validate(trip)


@router.patch("/{trip_id}", response_model=TripRead)
async def update_trip(
    data: TripUpdate,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> TripRead:
    trip = await trip_service.update_trip(session, trip, data)
    return TripRead.model_validate(trip)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await trip_service.delete_trip(session, trip)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{trip_id}/gear", response_model=TripGearRead, status_code=status.HTTP_201_CREATED)
async def add_trip_gear(
    data: TripGearCreate,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> TripGearRead:
    item = await gear_service.get_item(session, trip.user_id, data.gear_item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gear item not found")
    trip_gear = await trip_service.add_trip_gear(session, trip.id, item, data)
    return TripGearRead.model_validate(trip_gear)


@router.post("/{trip_id}/gear/copy-from/{source_trip_id}", response_model=list[TripGearRead])
async def copy_trip_gear(
    source_trip_id: uuid.UUID,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> list[TripGearRead]:
    source = await trip_service.get_trip(session, source_trip_id)
    if not source or source.user_id != trip.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source trip not found")
    gear = await trip_service.copy_trip_gear(session, trip, source)
    return [TripGearRead.model_validate(tg) for tg in gear]


@router.patch("/{trip_id}/gear/{trip_gear_id}", response_model=TripGearRead)
async def update_trip_gear(
    trip_gear_id: uuid.UUID,
    data: TripGearUpdate,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> TripGearRead:
    trip_gear = await trip_service.get_trip_gear(session, trip.id, trip_gear_id)
    if not trip_gear:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gear not found on this trip")
    trip_gear = await trip_service.update_trip_gear(session, trip_gear, data)
    return TripGearRead.model_validate(trip_gear)


@router.delete("/{trip_id}/gear/{trip_gear_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_trip_gear(
    trip_gear_id: uuid.UUID,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Remove the item from this trip; it stays in the closet."""
    trip_gear = await trip_service.get_trip_gear(session, trip.id, trip_gear_id)
    if not trip_gear:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gear not found on this trip")
    await trip_service.delete_trip_gear(session, trip_gear)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{trip_id}/notes", response_model=TripNoteRead, status_code=status.HTTP_201_CREATED)
async def add_note(
    data: TripNoteCreate,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> TripNoteRead:
    note = await trip_service.add_note(session, trip.id, data)
    return TripNoteRead.model_validate(note)


@router.patch("/{trip_id}/notes/{note_id}", response_model=TripNoteRead)
async def update_note(
    note_id: uuid.UUID,
    data: TripNoteUpdate,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> TripNoteRead:
    note = await trip_service.get_note(session, trip.id, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    note = await trip_service.update_note(session, note, data)
    return TripNoteRead.model_validate(note)


@router.delete("/{trip_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> Response:
    note = await trip_service.get_note(session, trip.id, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    await trip_service.delete_note(session, note)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{trip_id}/checklist/{item_key}", response_model=ChecklistItemRead)
async def update_checklist_item(
    item_key: ChecklistItemKey,
    data: ChecklistItemUpdate,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> ChecklistItemRead:
    item = await trip_service.get_checklist_item(session, trip.id, item_key)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found")
    item = await trip_service.update_checklist_item(session, item, data)
    return ChecklistItemRead.model_validate(item)


@router.patch("/{trip_id}/food-plan", response_model=FoodPlannerRead)
async def update_food_plan(
    data: FoodPlannerUpdate,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> FoodPlannerRead:
    if trip.food_plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Food plan not found")
    planner = await trip_service.update_food_planner(session, trip.food_plan, data)
    return FoodPlannerRead.model_validate(planner)


@router.post("/{trip_id}/food-plan/items", response_model=TripFoodRead, status_code=status.HTTP_201_CREATED)
async def add_food_item(
    data: TripFoodCreate,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> TripFoodRead:
    if trip.food_plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Food plan not found")
    food = await trip_service.add_food_item(session, trip.food_plan.id, data)
    return TripFoodRead.model_validate(food)


@router.patch("/{trip_id}/food-plan/items/{food_id}", response_model=TripFoodRead)
async def update_food_item(
    food_id: uuid.UUID,
    data: TripFoodUpdate,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> TripFoodRead:
    if trip.food_plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Food plan not found")
    food = await trip_service.get_food_item(session, trip.food_plan.id, food_id)
    if not food:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Food item not found")
    food = await trip_service.update_food_item(session, food, data)
    return TripFoodRead.model_validate(food)


@router.delete("/{trip_id}/food-plan/items/{food_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_food_item(
    food_id: uuid.UUID,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if trip.food_plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Food plan not found")
    food = await trip_service.get_food_item(session, trip.food_plan.id, food_id)
    if not food:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Food item not found")
    await trip_service.delete_food_item(session, food)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
