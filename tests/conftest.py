import os
import tempfile

import numpy as np
import pytest
from scipy.io import wavfile

from core.engine import PulseForgeEngine
from core.models import SignalFrame


@pytest.fixture
def engine():
    """Return a fresh PulseForgeEngine instance."""
    return PulseForgeEngine()


@pytest.fixture
def sample_frame():
    """Return a SignalFrame populated with realistic test data."""
    return SignalFrame(
        timestamp=0.033,
        peak_amplitude=0.85,
        fft_bins=[0.1, 0.4, 0.85, 0.6, 0.3, 0.15, 0.05, 0.02],
        motor_pitches=[220, 440],
        metadata={"file": "test.wav", "sample_rate": 44100, "progress": 0.5},
    )


@pytest.fixture
def test_wav(tmp_path):
    """Generate a temporary 1-second 440 Hz sine WAV file, yield its path, then clean up."""
    sample_rate = 44100
    duration = 1.0
    t = np.linspace(0.0, duration, int(sample_rate * duration), endpoint=False)
    samples = np.sin(2 * np.pi * 440 * t)
    # Convert to 16-bit PCM
    pcm = np.int16(samples * 32767)

    wav_path = str(tmp_path / "test_tone.wav")
    wavfile.write(wav_path, sample_rate, pcm)

    yield wav_path

    if os.path.exists(wav_path):
        os.remove(wav_path)
