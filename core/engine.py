import asyncio
from typing import List, Callable
from .models import SignalFrame

class PulseForgeEngine:
    def __init__(self):
        self.subscribers: List[Callable] = []
        self.queue = asyncio.Queue(maxsize=20)

    def add_subscriber(self, callback: Callable):
        """Registers an output module (TUI, Audio, Hardware)."""
        self.subscribers.append(callback)

    async def broadcast(self):
        """Main loop pumping frames to all subscribers concurrently."""
        while True:
            frame = await self.queue.get()
            # Non-blocking broadcast
            tasks = [sub(frame) for sub in self.subscribers]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self.queue.task_done()

    async def push_frame(self, frame: SignalFrame):
        """Producers call this to inject new data."""
        if not self.queue.full():
            await self.queue.put(frame)
