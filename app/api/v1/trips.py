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
    GearCreate,
    GearRead,
    GearUpdate,
    TripCreate,
    TripFoodCreate,
    TripFoodRead,
    TripFoodUpdate,
    TripNoteCreate,
    TripNoteRead,
    TripNoteUpdate,
    TripRead,
    TripUpdate,
)
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


@router.post("/{trip_id}/gear", response_model=GearRead, status_code=status.HTTP_201_CREATED)
async def add_gear(
    data: GearCreate,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> GearRead:
    gear = await trip_service.add_gear(session, trip.id, data)
    return GearRead.model_validate(gear)


@router.patch("/{trip_id}/gear/{gear_id}", response_model=GearRead)
async def update_gear(
    gear_id: uuid.UUID,
    data: GearUpdate,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> GearRead:
    gear = await trip_service.get_gear(session, trip.id, gear_id)
    if not gear:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gear item not found")
    gear = await trip_service.update_gear(session, gear, data)
    return GearRead.model_validate(gear)


@router.delete("/{trip_id}/gear/{gear_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gear(
    gear_id: uuid.UUID,
    trip: Trip = Depends(get_owned_trip),
    session: AsyncSession = Depends(get_session),
) -> Response:
    gear = await trip_service.get_gear(session, trip.id, gear_id)
    if not gear:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gear item not found")
    await trip_service.delete_gear(session, gear)
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
