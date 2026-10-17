import threading
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import passwords
from app.schemas.user import UserCreate, UserLogin
from app.services import user as user_service

_PASSWORD = "r1GRB3$ZB0*mbwymrJuJcdUTtdqESdf%AuD"  # nosec B105


def _record_thread(fn: Callable[..., Any], threads: list[threading.Thread]) -> Callable[..., Any]:
    def wrapper(*args: Any) -> Any:
        threads.append(threading.current_thread())
        return fn(*args)

    return wrapper


async def test_bcrypt_runs_off_the_event_loop_thread(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # bcrypt takes ~100 ms+ per call; on the event loop thread it would stall every other request.
    threads: list[threading.Thread] = []
    monkeypatch.setattr(user_service, "hash_password", _record_thread(passwords.hash_password, threads))
    monkeypatch.setattr(user_service, "verify_password", _record_thread(passwords.verify_password, threads))
    loop_thread = threading.current_thread()

    await user_service.create_user(
        session, UserCreate(email="hiker@example.com", password=_PASSWORD, username="hiker")
    )
    good = await user_service.authenticate(session, UserLogin(email="hiker@example.com", password=_PASSWORD))
    bad = await user_service.authenticate(
        session, UserLogin(email="hiker@example.com", password=_PASSWORD + "x")
    )

    assert good is not None
    assert bad is None
    assert len(threads) == 3
    assert loop_thread not in threads


async def test_zxcvbn_runs_off_the_event_loop_thread(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # zxcvbn can take ~400 ms on a long password, longer than a bcrypt hash.
    threads: list[threading.Thread] = []
    monkeypatch.setattr(passwords, "zxcvbn", _record_thread(passwords.zxcvbn, threads))

    await user_service.create_user(
        session, UserCreate(email="hiker@example.com", password=_PASSWORD, username="hiker")
    )

    assert len(threads) == 1
    assert threading.current_thread() not in threads
