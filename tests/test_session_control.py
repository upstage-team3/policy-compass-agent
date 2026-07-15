from __future__ import annotations

import asyncio

from app.core.session_control import SessionLockPool, SlidingWindowRateLimiter


async def test_same_session_turns_are_serialized_and_lock_is_released():
    pool = SessionLockPool()
    active = 0
    maximum_active = 0

    async def work() -> None:
        nonlocal active, maximum_active
        async with pool.hold("same-session"):
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0)
            active -= 1

    await asyncio.gather(work(), work(), work())

    assert maximum_active == 1
    assert pool.active_session_count == 0


async def test_different_sessions_can_run_concurrently():
    pool = SessionLockPool()
    both_entered = asyncio.Event()
    entered = 0

    async def work(session_id: str) -> None:
        nonlocal entered
        async with pool.hold(session_id):
            entered += 1
            if entered == 2:
                both_entered.set()
            await asyncio.wait_for(both_entered.wait(), timeout=1)

    await asyncio.gather(work("session-a"), work("session-b"))

    assert pool.active_session_count == 0


async def test_sliding_window_rate_limiter_returns_retry_after_and_recovers():
    limiter = SlidingWindowRateLimiter()

    assert await limiter.acquire("session", limit=2, window_seconds=60, now=100) is None
    assert await limiter.acquire("session", limit=2, window_seconds=60, now=101) is None
    retry_after = await limiter.acquire("session", limit=2, window_seconds=60, now=102)
    recovered = await limiter.acquire("session", limit=2, window_seconds=60, now=161)

    assert retry_after == 58
    assert recovered is None
