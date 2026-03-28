import pygame
from core.models import SignalFrame


class AudioConsumer:
    """
    Plays audio via pygame.mixer, synchronized with the engine's
    frame stream. Supports loading new files without restarting.
    """

    def __init__(self):
        self.file_path: str = ""
        self.paused: bool = False
        self._initialized = False

    def _ensure_mixer(self):
        """Initialize the mixer once if not already initialized."""
        if not self._initialized:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            self._initialized = True

    def _mixer_ready(self) -> bool:
        """Check if the mixer is actually initialized (not just our flag)."""
        return self._initialized and pygame.mixer.get_init() is not None

    def load(self, file_path: str):
        """Stop any current playback, then load and play a new file."""
        self._ensure_mixer()
        if self._mixer_ready() and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        self.file_path = file_path
        self.paused = False
        pygame.mixer.music.load(self.file_path)
        pygame.mixer.music.play()

    def pause(self):
        """Pause playback."""
        if self._mixer_ready() and not self.paused:
            pygame.mixer.music.pause()
            self.paused = True

    def resume(self):
        """Resume playback."""
        if self._mixer_ready() and self.paused:
            pygame.mixer.music.unpause()
            self.paused = False

    def stop(self):
        """Stop playback and clean up."""
        if self._mixer_ready():
            try:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
            except pygame.error:
                pass
        self._initialized = False
        self.paused = False

    def is_playing(self) -> bool:
        """Check if audio is still playing."""
        return self._mixer_ready() and pygame.mixer.music.get_busy()

    async def on_frame(self, frame: SignalFrame):
        """
        Subscriber callback — called by the engine on each frame.
        Reserved for future use (volume ducking, effects, etc.).
        """
        pass
