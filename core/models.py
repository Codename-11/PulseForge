from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class SignalFrame:
    timestamp: float           # Current playback time
    peak_amplitude: float      # Normalized (0.0 - 1.0)
    fft_bins: List[float]      # Frequency magnitudes (Log-scaled)
    motor_pitches: List[int] = field(default_factory=list)  # (Phase 2) Target frequencies in Hz
    metadata: Dict = field(default_factory=dict)  # Track Title, BPM, Engine Status
