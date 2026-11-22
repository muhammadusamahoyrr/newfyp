"""bcrypt (~250 ms at 12 rounds) must not freeze the event loop.

Called inline from an async route, each login stopped every other request,
websocket and timer for its whole duration. The async wrappers run it in a
worker thread; bcrypt releases the GIL, so the loop keeps ticking meanwhile.
"""
import asyncio

from app.core.security import (
    hash_password, hash_password_async, verify_password_async,
)


def test_the_loop_keeps_running_while_a_password_is_verified():
    hashed = hash_password("Correct-horse-1")

    async def main():
        ticks = 0
        stop = False

        async def ticker():
            nonlocal ticks
            while not stop:
                ticks += 1
                await asyncio.sleep(0.005)

        t = asyncio.create_task(ticker())
        await asyncio.sleep(0)
        ok = await verify_password_async("Correct-horse-1", hashed)
        stop = True
        await t
        return ok, ticks

    ok, ticks = asyncio.run(main())
    assert ok is True
    # Inline bcrypt would allow ~1 tick; off-loop it allows dozens.
    assert ticks >= 5


def test_async_wrappers_give_the_same_answers():
    async def main():
        h = await hash_password_async("Pw-12345678")
        return (await verify_password_async("Pw-12345678", h),
                await verify_password_async("wrong", h),
                await verify_password_async("x", "!closed"))
    assert asyncio.run(main()) == (True, False, False)
