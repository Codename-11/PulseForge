# PulseForge

A modular async signal processing engine that translates audio files into real-time TUI visualizations with synchronized playback.

Built with Python and Textual. Accepts WAV and MP3 input, performs real-time FFT analysis, and renders six switchable visualization modes in an amber-on-black industrial terminal interface.

<!-- TODO: Add screenshots -->

## Quick Start

```bash
uv sync
npm start -- path/to/track.mp3
```

## Development

```bash
npm run dev -- track.mp3     # Textual hot-reload CSS
npm test                      # pytest
npm run lint                  # ruff
```

## Keybindings

| Key   | Action                    |
|-------|---------------------------|
| 1-6   | Switch visualization mode |
| O     | Open file browser         |
| Space | Pause / Resume            |
| R     | Restart track             |
| S     | Settings                  |
| H     | Help                      |
| Esc   | Back                      |
| Q     | Quit                      |

## Visualization Modes

1. **Bars** -- 8-band frequency bars with gradient fill, gravity decay, and peak hold.
2. **Waveform** -- Scrolling oscilloscope display with bass-weighted FFT mix.
3. **Spectrogram** -- 2D time-by-frequency heatmap.
4. **Isometric** -- 3D isometric bar chart with shadow faces.
5. **Retrowave** -- Synthwave scene with pulsing sun, FFT mountains, and perspective grid.
6. **Waterfall** -- Downward-scrolling frequency history with age decay.

Modes are switchable at any time with the number keys 1 through 6.

## Architecture

```
Producer (FFT) --> Engine (pub/sub queue) --> [TUI, Audio] subscribers
```

The system follows a producer/subscriber pattern. The WAV producer decodes audio and runs real-time FFT with overlapping 4096-sample windows, producing dB-scale magnitudes with running peak normalization. Each analysis frame is packaged as a **SignalFrame** -- the atomic data unit containing frequency bins, time-domain samples, and metadata. The async broadcast engine pushes SignalFrames through a pub/sub queue to all registered subscribers (TUI display and audio consumer). Rendering runs at 30 FPS via timer-driven updates with dirty-flag optimization.

Live-tunable settings include decay rate, peak hold, smoothing, and volume. The app is persistent -- load new files through the in-app file browser without restarting.

## Project Structure

```
core/engine.py           -- Async pub/sub broadcast engine
core/models.py           -- SignalFrame dataclass
inputs/wav_producer.py   -- Audio decode + FFT (WAV/MP3)
outputs/tui_display.py   -- Textual TUI with screens
outputs/visualizers.py   -- 6 visualization renderers
outputs/audio_consumer.py -- pygame-ce playback
styles/theme.tcss        -- Amber-burn TCSS theme
```

## Tech Stack

- Python 3.11+
- Textual (TUI framework)
- NumPy + SciPy (FFT/DSP)
- pygame-ce (audio playback)
- uv (package manager)
- pytest (testing)

## Roadmap

- **Phase 1: Virtual Foundry** (Complete) -- FFT analysis, TUI visualization, synchronized audio playback.
- **Phase 2: Hardware Bridge** -- pySerial output to ESP32/Arduino for stepper motor control.
- **Phase 3: MIDI + Protocol** -- MIDI input support and custom serial protocol.

## License

MIT
