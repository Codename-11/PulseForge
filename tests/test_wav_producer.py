import pytest

from core.engine import PulseForgeEngine
from inputs.wav_producer import AudioProducer


@pytest.fixture
def wav_producer(test_wav):
    """Return a AudioProducer wired to a fresh engine and the test WAV file."""
    engine = PulseForgeEngine()
    return AudioProducer(engine, test_wav)


def test_load_wav(wav_producer):
    """After _load(), samples should be populated and sample_rate should be 44100."""
    wav_producer._load()
    assert wav_producer.sample_rate == 44100
    assert len(wav_producer.samples) > 0


def test_fft_bands_returns_8_bands(wav_producer):
    """_fft_bands() should return exactly 8 float values between 0.0 and 1.0."""
    wav_producer._load()
    window_size = int(wav_producer.sample_rate * wav_producer.WINDOW_MS / 1000)
    chunk = wav_producer.samples[:window_size]
    bands = wav_producer._fft_bands(chunk)

    assert len(bands) == 8
    for b in bands:
        assert isinstance(b, float)
        assert 0.0 <= b <= 1.0


def test_fft_bands_values_normalized(wav_producer):
    """All band values must be normalized to at most 1.0."""
    wav_producer._load()
    window_size = int(wav_producer.sample_rate * wav_producer.WINDOW_MS / 1000)
    chunk = wav_producer.samples[:window_size]
    bands = wav_producer._fft_bands(chunk)

    assert all(b <= 1.0 for b in bands)
