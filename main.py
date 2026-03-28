import asyncio
import sys
import os
from pathlib import Path
from core.engine import PulseForgeEngine
from inputs.wav_producer import AudioProducer
from outputs.tui_display import PulseForgeTUI
from outputs.audio_consumer import AudioConsumer


class PulseForgeApp:
    """Persistent application shell — wires engine, producer, audio, and TUI."""

    def __init__(self):
        self.engine = PulseForgeEngine()
        self.producer = AudioProducer(self.engine)
        self.audio = AudioConsumer()
        self.tui = PulseForgeTUI(self.engine)
        self._producer_task: asyncio.Task | None = None

        # Wire the TUI's callbacks
        self.tui.on_file_load = self.load_file
        self.tui.on_pause_toggle = self._handle_pause

    async def load_file(self, file_path: str):
        """Load and play a new audio file."""
        path = Path(file_path)
        if not path.exists():
            return

        ext = path.suffix.lower()
        if ext not in (".wav", ".mp3"):
            return

        # Cancel any running producer
        if self._producer_task and not self._producer_task.done():
            self._producer_task.cancel()
            try:
                await self._producer_task
            except asyncio.CancelledError:
                pass

        # Reset engine state for new track
        self.engine.reset()

        # Start audio playback
        self.audio.load(file_path)

        # Launch producer in background
        self._producer_task = asyncio.create_task(
            self.producer.load_and_run(file_path)
        )

    def _handle_pause(self, paused: bool):
        """Sync audio playback with TUI pause state."""
        if paused:
            self.audio.pause()
        else:
            self.audio.resume()

    async def run(self, initial_file: str | None = None):
        """Start the persistent app."""
        # Register audio consumer as subscriber
        self.engine.add_subscriber(self.audio.on_frame)

        # Start engine broadcast loop (runs forever)
        broadcast_task = asyncio.create_task(self.engine.broadcast())

        # Load initial file if provided
        if initial_file:
            await self.load_file(initial_file)

        try:
            # TUI runs until user quits
            await self.tui.run_async()
        finally:
            # Cleanup
            broadcast_task.cancel()
            if self._producer_task and not self._producer_task.done():
                self._producer_task.cancel()
            self.audio.stop()


def main():
    initial_file = sys.argv[1] if len(sys.argv) > 1 else None

    if initial_file and not os.path.exists(initial_file):
        print(f"File not found: {initial_file}")
        sys.exit(1)

    app = PulseForgeApp()
    try:
        asyncio.run(app.run(initial_file))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
