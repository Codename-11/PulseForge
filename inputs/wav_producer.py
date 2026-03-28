import asyncio
import numpy as np
from pathlib import Path
from scipy.fft import rfft, rfftfreq
from scipy.io import wavfile
from core.models import SignalFrame


class AudioProducer:
    """
    Reads audio files (WAV or MP3), chunks into windows,
    performs FFT, and pushes SignalFrames at playback rate.
    """

    BANDS = 8
    WINDOW_MS = 33  # ~30 FPS
    FREQ_EDGES = [20, 60, 160, 400, 1000, 2500, 6000, 12000, 20000]  # 8 bands

    def __init__(self, engine):
        self.engine = engine
        self.file_path: str = ""
        self.sample_rate = 0
        self.samples = np.array([])

    def _load(self):
        """Load audio file and convert to mono float64 normalized to [-1, 1]."""
        ext = Path(self.file_path).suffix.lower()

        if ext == ".wav":
            self._load_wav()
        elif ext == ".mp3":
            self._load_mp3()
        else:
            raise ValueError(f"Unsupported format: {ext} (supported: .wav, .mp3)")

    def _load_wav(self):
        """Load WAV via scipy."""
        self.sample_rate, data = wavfile.read(self.file_path)
        self.samples = self._to_mono_float(data)

    def _load_mp3(self):
        """Load MP3 via pygame-ce's SDL_mixer decoder."""
        import pygame
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        sound = pygame.mixer.Sound(self.file_path)
        data = pygame.sndarray.array(sound)
        self.sample_rate = 44100
        self.samples = self._to_mono_float(data)
        pygame.mixer.quit()

    @staticmethod
    def _to_mono_float(data: np.ndarray) -> np.ndarray:
        """Convert any integer/float PCM array to mono float64 in [-1, 1]."""
        if data.dtype == np.int16:
            data = data.astype(np.float64) / 32768.0
        elif data.dtype == np.int32:
            data = data.astype(np.float64) / 2147483648.0
        elif data.dtype == np.float32:
            data = data.astype(np.float64)

        if data.ndim == 2:
            data = data.mean(axis=1)

        return data

    def _fft_bands(self, chunk: np.ndarray) -> list[float]:
        """Apply Hanning window, compute FFT, bin into frequency bands."""
        windowed = chunk * np.hanning(len(chunk))
        magnitudes = np.abs(rfft(windowed))
        freqs = rfftfreq(len(chunk), 1.0 / self.sample_rate)

        bands = []
        for i in range(self.BANDS):
            lo = self.FREQ_EDGES[i]
            hi = self.FREQ_EDGES[i + 1]
            mask = (freqs >= lo) & (freqs < hi)
            if mask.any():
                bands.append(float(np.mean(magnitudes[mask])))
            else:
                bands.append(0.0)

        # Normalize bands to 0.0 - 1.0
        peak = max(bands) if bands else 1.0
        if peak > 0:
            bands = [b / peak for b in bands]

        return bands

    async def load_and_run(self, file_path: str):
        """Load a new file and stream SignalFrames at playback rate."""
        self.file_path = file_path
        self._load()

        self.engine.playing = True
        self.engine.current_file = file_path

        window_samples = int(self.sample_rate * self.WINDOW_MS / 1000)
        total_samples = len(self.samples)
        offset = 0
        timestamp = 0.0

        try:
            while offset + window_samples <= total_samples:
                chunk = self.samples[offset : offset + window_samples]
                bins = self._fft_bands(chunk)

                frame = SignalFrame(
                    timestamp=timestamp,
                    peak_amplitude=max(bins),
                    fft_bins=bins,
                    metadata={
                        "file": Path(self.file_path).name,
                        "sample_rate": self.sample_rate,
                        "progress": offset / total_samples,
                    },
                )

                await self.engine.push_frame(frame)

                await asyncio.sleep(self.WINDOW_MS / 1000)
                offset += window_samples
                timestamp += self.WINDOW_MS / 1000
        finally:
            self.engine.playing = False
