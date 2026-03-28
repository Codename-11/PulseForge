SPEC.md: PulseForge Engine

1. Executive Summary

PulseForge is a modular, asynchronous signal processing engine built in Python. Its primary purpose is to translate audio data (WAV, MP3, or Live MIDI) into a high-fidelity Terminal User Interface (TUI) and real-time hardware control signals for stepper motors.

The project follows a "Single Source of Truth" philosophy: a central engine processes audio into a standardized data frame, which is then broadcast to any number of visual or physical outputs.

2. System Architecture

PulseForge utilizes a Publisher-Subscriber (Pub/Sub) model driven by Python’s asyncio library. This ensures that high-latency tasks (like serial communication with hardware) do not block the high-frequency rendering of the TUI.

2.1 The Data Flow

Producer: Reads audio, performs Fast Fourier Transform (FFT), and generates a SignalFrame.

Engine: Receives the frame, performs optional normalization/smoothing, and pushes it to the Broadcast Queue.

Consumers:

TUI: Renders frequency bars and telemetry.

Audio: Streams the raw buffer to local speakers.

Serial: (Phase 2) Maps frequencies to step-rates for microcontrollers.

3. Technical Stack

Component

Technology

Rationale

Language

Python 3.11+

Rapid prototyping and excellent asyncio support.

TUI Framework

Textual

Modern, CSS-styled, and asynchronously reactive.

Math/DSP

NumPy & SciPy

High-performance FFT and array manipulation.

Audio Playback

Pygame.mixer

Low-latency audio buffer management.

Hardware Link

pySerial

Standardized communication with ESP32/Arduino.

4. Core Data Model

The SignalFrame is the atomic unit of data in PulseForge.

@dataclass
class SignalFrame:
    timestamp: float           # Current playback time
    peak_amplitude: float      # Normalized (0.0 - 1.0)
    fft_bins: List[float]      # Frequency magnitudes (Log-scaled)
    motor_pitches: List[int]   # (Phase 2) Target frequencies in Hz
    metadata: Dict             # Track Title, BPM, Engine Status


5. Module Specifications

5.1 Input Module (WavProducer)

Function: Decodes audio files and chunks them into 20ms-50ms windows.

DSP: Applies a Hanning window and performs an FFT to extract magnitude across 8-12 frequency bands.

Output: Pushes SignalFrame to the Engine at 30-60 FPS.

5.2 UI Module (TuiConsumer)

Layout: Three-column responsive grid (Telemetry | Visualizer | Monitors).

Visualizer: Vertical bars using Unicode block characters (█).

Theme: "Amber-Burn" palette (#FFB000 on #0D0D0D).

Features: Real-time telemetry (buffer health, CPU load) and per-channel signal monitors.

5.3 Hardware Module (PulseConsumer)

Mapping: Maps the dominant frequency in each FFT bin to a specific stepper motor.

Protocol: Minimalist binary packet over Serial (115200 Baud).

Latency Goal: <20ms from audio analysis to motor movement.

6. Development Roadmap

Phase 1: The Virtual Foundry (Current)

[ ] Implement PulseForgeEngine async bus.

[ ] Build WavProducer with basic FFT logic.

[ ] Create Textual dashboard with frequency bars and telemetry.

[ ] Implement local audio playback synced to TUI.

Phase 2: The Physical Foundry

[ ] Integrate pySerial output module.

[ ] Develop ESP32 firmware to receive frequencies and generate step pulses.

[ ] Calibrate motor resonant frequencies (The "Tuning" phase).

[ ] 3D print custom NEMA 17 acoustic mounts.

7. Design Aesthetics

UI Style: High-density, terminal-based dashboard.

Inspiration: Industrial automation displays and "Cyberpunk" command centers.

Motion: Bars should feature "gravity" (smooth decay) and "peak-hold" (ghosting at the top of a signal spike).