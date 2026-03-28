import asyncio

import pytest

from core.models import SignalFrame


@pytest.mark.asyncio
async def test_push_frame(engine, sample_frame):
    """Pushing a frame should place exactly one item on the queue."""
    await engine.push_frame(sample_frame)
    assert engine.queue.qsize() == 1


@pytest.mark.asyncio
async def test_broadcast_delivers(engine, sample_frame):
    """A subscriber should receive the frame after broadcast runs."""
    received = []

    async def subscriber(frame: SignalFrame):
        received.append(frame)

    engine.add_subscriber(subscriber)
    await engine.push_frame(sample_frame)

    # Run broadcast as a task; cancel after the frame is delivered.
    task = asyncio.create_task(engine.broadcast())
    await asyncio.sleep(0.05)
    task.cancel()

    assert len(received) == 1
    assert received[0] is sample_frame


def test_subscriber_registration(engine):
    """Adding multiple subscribers should be reflected in the subscribers list."""

    async def sub_a(frame):
        pass

    async def sub_b(frame):
        pass

    async def sub_c(frame):
        pass

    engine.add_subscriber(sub_a)
    engine.add_subscriber(sub_b)
    engine.add_subscriber(sub_c)

    assert len(engine.subscribers) == 3
