import asyncio
from typing import List, Callable
from .models import SignalFrame

SMOOTHING_FACTOR = 0.3  # EMA alpha — higher = more responsive, lower = smoother


class PulseForgeEngine:
    def __init__(self):
        self.subscribers: List[Callable] = []
        self.queue = asyncio.Queue(maxsize=20)
        self.running = True
        self.playing: bool = False
        self.current_file: str = ""
        self._prev_bins: List[float] = []
        self._smoothing_factor: float = SMOOTHING_FACTOR

    def add_subscriber(self, callback: Callable):
        """Registers an output module (TUI, Audio, Hardware)."""
        self.subscribers.append(callback)

    def reset(self):
        """Clear state for a new track without tearing down the engine."""
        # Drain the queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break
        self._prev_bins = []
        self.running = True
        self.playing = False

    def _smooth(self, frame: SignalFrame) -> SignalFrame:
        """Apply exponential moving average to FFT bins for smoother visuals."""
        if not self._prev_bins:
            self._prev_bins = list(frame.fft_bins)
            return frame

        smoothed = []
        for i, val in enumerate(frame.fft_bins):
            prev = self._prev_bins[i] if i < len(self._prev_bins) else 0.0
            s = self._smoothing_factor * val + (1 - self._smoothing_factor) * prev
            smoothed.append(s)

        self._prev_bins = smoothed
        frame.fft_bins = smoothed
        frame.peak_amplitude = max(smoothed) if smoothed else 0.0
        return frame

    async def broadcast(self):
        """Main loop pumping frames to all subscribers concurrently. Runs forever."""
        while True:
            try:
                frame = await asyncio.wait_for(self.queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            frame = self._smooth(frame)

            tasks = [sub(frame) for sub in self.subscribers]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self.queue.task_done()

    def stop(self):
        """Signal the engine to stop after current frame."""
        self.running = False

    async def push_frame(self, frame: SignalFrame):
        """Producers call this to inject new data."""
        if not self.queue.full():
            await self.queue.put(frame)
