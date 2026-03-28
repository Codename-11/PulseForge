import asyncio
import time
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
    WINDOW_MS = 33  # ~30 FPS (advance rate)
    ANALYSIS_SAMPLES = 4096  # ~93ms at 44100 Hz for better bass resolution
    FREQ_EDGES = [20, 60, 160, 400, 1000, 2500, 6000, 12000, 20000]  # 8 bands

    # dB normalization range
    _DB_FLOOR = -60.0
    _DB_CEILING = 0.0

    def __init__(self, engine):
        self.engine = engine
        self.file_path: str = ""
        self.sample_rate = 0
        self.samples = np.array([])
        self._running_max = 0.0

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
        """Load MP3 via pygame-ce's SDL_mixer decoder.

        Uses a separate temporary mixer init to decode the MP3 into a numpy
        array without interfering with the AudioConsumer's playback mixer.
        """
        import pygame
        # Only init a temporary mixer if one isn't already running
        mixer_was_init = pygame.mixer.get_init() is not None
        if not mixer_was_init:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        sound = pygame.mixer.Sound(self.file_path)
        data = pygame.sndarray.array(sound)
        self.sample_rate = 44100
        self.samples = self._to_mono_float(data)
        # Only quit if we were the ones who initialized it
        if not mixer_was_init:
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
        """Apply Hanning window, compute FFT with dB magnitudes, bin into
        frequency bands, and normalize using running peak tracking."""
        windowed = chunk * np.hanning(len(chunk))
        magnitudes = np.abs(rfft(windowed))
        freqs = rfftfreq(len(chunk), 1.0 / self.sample_rate)

        # Convert to dB scale: 20 * log10(mag + eps)
        magnitudes_db = 20.0 * np.log10(magnitudes + 1e-10)

        # Clamp to [floor, ceiling] and normalize to 0.0-1.0
        magnitudes_db = np.clip(magnitudes_db, self._DB_FLOOR, self._DB_CEILING)
        magnitudes_norm = (magnitudes_db - self._DB_FLOOR) / (self._DB_CEILING - self._DB_FLOOR)

        bands = []
        for i in range(self.BANDS):
            lo = self.FREQ_EDGES[i]
            hi = self.FREQ_EDGES[i + 1]
            mask = (freqs >= lo) & (freqs < hi)
            if mask.any():
                bands.append(float(np.mean(magnitudes_norm[mask])))
            else:
                bands.append(0.0)

        # Running peak normalization with exponential decay
        current_max = max(bands) if bands else 0.0
        self._running_max = max(current_max, self._running_max * 0.995)

        if self._running_max > 0:
            bands = [b / self._running_max for b in bands]

        return bands

    async def load_and_run(self, file_path: str):
        """Load a new file and stream SignalFrames at playback rate."""
        self.file_path = file_path
        self._load()
        await self._run_frames(file_path)

    async def _run_frames(self, file_path: str):
        """Stream SignalFrames from already-loaded samples with drift-corrected timing.

        Uses overlapping windows: reads ANALYSIS_SAMPLES (4096) for FFT but
        advances by window_samples (33ms worth) each frame for 30 FPS output.
        """
        self.engine.playing = True
        self.engine.current_file = file_path
        self._running_max = 0.0

        window_samples = int(self.sample_rate * self.WINDOW_MS / 1000)
        analysis_samples = self.ANALYSIS_SAMPLES
        total_samples = len(self.samples)
        window_sec = self.WINDOW_MS / 1000
        offset = 0
        timestamp = 0.0
        start_time = time.monotonic()
        frame_idx = 0

        try:
            while offset + window_samples <= total_samples:
                # Grab the larger analysis window for better frequency resolution.
                # If not enough samples remain for a full analysis window,
                # use whatever is available (zero-padded via smaller FFT).
                end = min(offset + analysis_samples, total_samples)
                chunk = self.samples[offset:end]

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

                # Drift-corrected sleep: target next frame time from start
                frame_idx += 1
                target_time = start_time + frame_idx * window_sec
                sleep_time = target_time - time.monotonic()
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                # Advance by window_samples (33ms) — not analysis_samples
                offset += window_samples
                timestamp += window_sec
        finally:
            self.engine.playing = False
