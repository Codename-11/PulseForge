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
        self.tui.on_settings_change = self._handle_setting
        self.tui.on_restart = self._handle_restart

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

        # Pre-load the audio data for FFT (before starting playback mixer)
        self.producer.file_path = file_path
        self.producer._load()

        # Pre-load audio into mixer but don't play yet
        self.audio.preload(file_path)

        # Launch producer — it will signal us to start audio on first frame
        self._producer_task = asyncio.create_task(
            self._produce_with_sync(file_path)
        )

    async def _produce_with_sync(self, file_path: str):
        """Run the producer, starting audio playback on the first frame."""
        first_frame = True

        original_push = self.engine.push_frame

        async def synced_push(frame):
            nonlocal first_frame
            if first_frame:
                first_frame = False
                self.audio.play()
            await original_push(frame)

        self.engine.push_frame = synced_push
        try:
            await self.producer._run_frames(file_path)
        finally:
            self.engine.push_frame = original_push

    def _handle_pause(self, paused: bool):
        """Sync audio playback with TUI pause state."""
        if paused:
            self.audio.pause()
        else:
            self.audio.resume()

    def _handle_setting(self, key: str, value: float):
        """Apply a setting change from the TUI to the backend."""
        if key == "smoothing":
            from core.engine import SMOOTHING_FACTOR
            # Update the engine's smoothing factor directly
            self.engine._smoothing_factor = value
        elif key == "volume":
            if self.audio._mixer_ready():
                import pygame
                pygame.mixer.music.set_volume(value)

    async def _handle_restart(self):
        """Restart the current track from the beginning."""
        if self.engine.current_file:
            await self.load_file(self.engine.current_file)

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
