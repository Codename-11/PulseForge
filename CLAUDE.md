# CLAUDE.md — PulseForge

## Overview
PulseForge is a modular async signal processing engine (Python/Textual) that translates audio (WAV/MP3/MIDI) into a TUI visualizer and real-time stepper motor control signals. Pub/Sub architecture via asyncio.

## Quick Start
```
uv sync
uv run pulseforge <audio_file.wav>
uv run pytest
```

## Architecture
- `core/engine.py` — Async pub/sub broadcast engine (queue-based)
- `core/models.py` — `SignalFrame` dataclass (the atomic data unit)
- `inputs/` — Producers (WavProducer: FFT from audio files)
- `outputs/` — Consumers (TUI display, audio playback, future: serial hardware)
- `styles/theme.tcss` — Textual CSS theme (Amber-Burn palette)
- `main.py` — Entry point, wires engine + producer + consumers

## Data Flow
Producer -> Engine Queue -> Broadcast -> [TUI, Audio, Serial] subscribers

## Conventions
- Conventional Commits: feat, fix, docs, refactor, test, chore
- Branches: feature/<name>, fix/<name>, docs/<name>
- SemVer versioning (VERSION file at root)
- Package management: uv
- Linting: ruff
- Tests: pytest + pytest-asyncio

## Key Design Decisions
- SignalFrame is the single source of truth — keep it spec-accurate with SPEC.md
- All consumers are async subscribers registered with the engine
- 8 frequency bands: SUB, BASS, LOW, MID, HMID, HIGH, AIR1, AIR2
- TUI uses Textual with CSS theming, not inline styles
- Audio playback uses `pygame-ce` (community edition) — drop-in for `pygame`, better Python 3.14 support
- Phase 2 (hardware/serial) is planned but not yet implemented

## Testing
```
uv run pytest              # all tests
uv run pytest tests/ -v    # verbose
```
