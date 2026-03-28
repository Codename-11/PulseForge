import pygame
from core.models import SignalFrame


class AudioConsumer:
    """
    Plays the audio file via pygame.mixer, synchronized with
    the engine's frame stream. Registered as an engine subscriber
    for future volume/effect control based on frame data.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._initialized = False

    def start_playback(self):
        """Initialize pygame mixer and begin audio playback."""
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        pygame.mixer.music.load(self.file_path)
        pygame.mixer.music.play()
        self._initialized = True

    def stop(self):
        """Stop playback and clean up."""
        if self._initialized:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
            self._initialized = False

    def is_playing(self) -> bool:
        """Check if audio is still playing."""
        return self._initialized and pygame.mixer.music.get_busy()

    async def on_frame(self, frame: SignalFrame):
        """
        Subscriber callback — called by the engine on each frame.
        Reserved for future use (volume ducking, effects, etc.).
        """
        pass
