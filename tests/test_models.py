from core.models import SignalFrame


def test_signal_frame_defaults():
    """motor_pitches should default to [] and metadata to {}."""
    frame = SignalFrame(
        timestamp=0.0,
        peak_amplitude=0.5,
        fft_bins=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    )
    assert frame.motor_pitches == []
    assert frame.metadata == {}


def test_signal_frame_fields():
    """All fields should store the values they were created with."""
    frame = SignalFrame(
        timestamp=1.5,
        peak_amplitude=0.9,
        fft_bins=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
        motor_pitches=[220, 440, 880],
        metadata={"bpm": 120, "title": "Test Track"},
    )
    assert frame.timestamp == 1.5
    assert frame.peak_amplitude == 0.9
    assert len(frame.fft_bins) == 8
    assert frame.motor_pitches == [220, 440, 880]
    assert frame.metadata["bpm"] == 120
    assert frame.metadata["title"] == "Test Track"
