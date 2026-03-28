import asyncio
import time
from datetime import datetime
from typing import Optional, Callable, List

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static, Label, Input
from core.models import SignalFrame


BAND_LABELS = ["SUB", "BASS", "LOW", "MID", "HMID", "HIGH", "AIR1", "AIR2"]
FREQ_LABELS = ["20Hz", "60Hz", "160Hz", "400Hz", "1kHz", "2.5kHz", "6kHz", "12kHz"]

DECAY_RATE = 0.85
PEAK_HOLD_TIME = 0.6
PEAK_DECAY_RATE = 0.92


class FrequencyBar(Static):
    """A single vertical frequency bar with gravity decay and peak-hold ghost."""

    def __init__(self, label: str, freq_label: str, index: int):
        super().__init__()
        self.label = label
        self.freq_label = freq_label
        self.index = index
        self.value = 0.0
        self.peak = 0.0
        self.peak_time = 0.0

    def update_value(self, val: float):
        now = time.monotonic()

        # Gravity: smooth decay if new value is lower
        if val >= self.value:
            self.value = val
        else:
            self.value = max(val, self.value * DECAY_RATE)

        # Peak-hold: track highest point with timed decay
        if val >= self.peak:
            self.peak = val
            self.peak_time = now
        elif now - self.peak_time > PEAK_HOLD_TIME:
            self.peak *= PEAK_DECAY_RATE

        self.refresh()

    def render(self) -> str:
        max_height = 14
        filled = int(self.value * max_height)
        filled = max(0, min(max_height, filled))
        peak_pos = int(self.peak * max_height)
        peak_pos = max(0, min(max_height, peak_pos))

        # Thick bars: 4 block chars wide per row
        bar_width = 4
        lines = []
        for row in range(max_height, 0, -1):
            if row <= filled:
                lines.append("█" * bar_width)
            elif row == peak_pos and peak_pos > filled:
                lines.append("▔" * bar_width)
            else:
                lines.append(" " * bar_width)

        lines.append(f" {self.freq_label:^{bar_width}} ")
        lines.append(f" {self.label:^{bar_width}} ")
        return "\n".join(lines)


class MonitorLine(Static):
    """Per-channel rolling mini-waveform monitor."""

    def __init__(self, label: str, index: int):
        super().__init__()
        self.label = label
        self.index = index
        self.history: list[float] = [0.0] * 16

    def push(self, val: float):
        self.history.append(val)
        if len(self.history) > 16:
            self.history.pop(0)
        self.refresh()

    def render(self) -> str:
        chars = " ▁▂▃▄▅▆▇█"
        wave = ""
        for v in self.history:
            idx = int(v * (len(chars) - 1))
            idx = max(0, min(len(chars) - 1, idx))
            wave += chars[idx]
        return f"{self.label:<4} [{wave}]"


class HeaderBar(Static):
    """Custom header: title left, filename center, clock right."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.filename = "No file loaded"
        self.clock_text = ""

    def set_filename(self, name: str):
        self.filename = name
        self.refresh()

    def update_clock(self):
        self.clock_text = datetime.now().strftime("%H:%M:%S")
        self.refresh()

    def render(self) -> str:
        title = "PULSEFORGE ENGINE v1.0"
        clock = self.clock_text or datetime.now().strftime("%H:%M:%S")
        # Build a fixed-width line — pad to fill terminal width
        # We'll use a rough 80-char width; Textual will handle overflow
        left = title
        center = self.filename
        right = clock
        # Simple three-column layout
        return f" {left}    {center:^30}    {right} "


class BottomStrip(Static):
    """Horizontal strip showing BPM, dominant freq, max amplitude, progress."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bpm = "---"
        self.dominant_freq = "---"
        self.max_amp = "0.00"
        self.progress = "0%"

    def set_data(self, dominant_freq: str, max_amp: float, progress: float):
        self.dominant_freq = dominant_freq
        self.max_amp = f"{max_amp:.2f}"
        self.progress = f"{int(progress * 100)}%"
        self.refresh()

    def render(self) -> str:
        return (
            f"  BPM: {self.bpm}  │  "
            f"FREQ: {self.dominant_freq}  │  "
            f"MAX: {self.max_amp}  │  "
            f"PROGRESS: {self.progress}"
        )


class FilePrompt(Static):
    """Overlay prompt for entering a file path."""

    def __init__(self):
        super().__init__()
        self.visible = False

    def render(self) -> str:
        if self.visible:
            return "  Enter file path below and press Enter:"
        return ""


class PulseForgeTUI(App):
    CSS_PATH = "../styles/theme.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("o", "open_file", "Open File", show=True),
        Binding("space", "toggle_pause", "Pause", show=True),
    ]

    def __init__(self, engine=None):
        super().__init__()
        self.engine = engine
        self.bars: list[FrequencyBar] = []
        self.monitors: list[MonitorLine] = []
        self._frame_count = 0
        self._start_time = 0.0
        self._last_frame: Optional[SignalFrame] = None
        self._paused = False
        self.on_file_load: Optional[Callable] = None
        self.on_pause_toggle: Optional[Callable] = None
        self._file_input_visible = False

    def compose(self) -> ComposeResult:
        # Header bar
        yield HeaderBar(id="header-bar")

        with Horizontal(id="main-container"):
            # LEFT: SIGNAL DATA
            with Vertical(id="left-panel", classes="side-panel"):
                yield Label("── SIGNAL DATA ──", classes="panel-title")
                yield Label("PEAK:   0.00", id="peak-label")
                yield Label("RMS:    0.00", id="rms-label")
                yield Label("FLOW:   0/20", id="flow-label")
                yield Label("STATUS: IDLE", id="status-label")

            # CENTER: VISUALIZER
            with Vertical(id="center-panel"):
                yield Label("── VISUALIZER ──", id="viz-title", classes="panel-title")
                with Horizontal(id="visualizer-grid"):
                    for i, name in enumerate(BAND_LABELS):
                        bar = FrequencyBar(name, FREQ_LABELS[i], i)
                        self.bars.append(bar)
                        yield bar
                yield Label("No file loaded — press O to open", id="center-message")

            # RIGHT: MONITORS
            with Vertical(id="right-panel", classes="side-panel"):
                yield Label("── MONITORS ──", classes="panel-title")
                for i, name in enumerate(BAND_LABELS):
                    mon = MonitorLine(name, i)
                    self.monitors.append(mon)
                    yield mon

        # Bottom strip
        yield BottomStrip(id="bottom-strip")

        # File input (hidden by default)
        yield Input(
            placeholder="Enter file path and press Enter...",
            id="file-input",
        )

        yield Footer()

    async def on_mount(self):
        self._start_time = time.monotonic()

        # Register subscriber if engine exists
        if self.engine is not None:
            self.engine.add_subscriber(self.update_ui)

        # Start clock timer — update every second
        self.set_interval(1.0, self._tick_clock)

        # Hide file input initially
        file_input = self.query_one("#file-input", Input)
        file_input.display = False

        # Update header with engine info
        self._update_header_filename()

    def _tick_clock(self):
        """Update the clock in the header every second."""
        try:
            header = self.query_one("#header-bar", HeaderBar)
            header.update_clock()
        except Exception:
            pass

        # Also refresh status based on engine state
        self._refresh_engine_status()

    def _update_header_filename(self):
        """Update header with current filename from engine."""
        try:
            header = self.query_one("#header-bar", HeaderBar)
            if self.engine and hasattr(self.engine, "current_file") and self.engine.current_file:
                header.set_filename(self.engine.current_file)
                # Hide the "no file" message
                msg = self.query_one("#center-message", Label)
                msg.display = False
            else:
                header.set_filename("No file loaded")
                msg = self.query_one("#center-message", Label)
                msg.display = True
        except Exception:
            pass

    def _refresh_engine_status(self):
        """Periodic status refresh from engine state."""
        if self.engine is None:
            return
        try:
            playing = getattr(self.engine, "playing", False)
            if playing:
                status = "PAUSED" if self._paused else "ACTIVE"
            else:
                # Check if we ever had a frame (track completed)
                if self._last_frame is not None:
                    status = "COMPLETE"
                else:
                    status = "IDLE"

            self.query_one("#status-label", Label).update(f"STATUS: {status}")
            self._update_header_filename()
        except Exception:
            pass

    async def update_ui(self, frame: SignalFrame):
        """Subscriber callback — fed by the engine broadcast loop."""
        if self._paused:
            return

        self._last_frame = frame
        self._frame_count += 1

        # Update frequency bars and monitors
        for i, val in enumerate(frame.fft_bins):
            if i < len(self.bars):
                self.bars[i].update_value(val)
            if i < len(self.monitors):
                self.monitors[i].push(val)

        # Find dominant frequency band
        if frame.fft_bins:
            max_idx = 0
            max_val = 0.0
            for i, v in enumerate(frame.fft_bins):
                if v > max_val:
                    max_val = v
                    max_idx = i
            dominant = BAND_LABELS[max_idx] if max_idx < len(BAND_LABELS) else "---"
        else:
            dominant = "---"
            max_val = 0.0

        # Update telemetry labels
        try:
            self.query_one("#peak-label", Label).update(
                f"PEAK:   {frame.peak_amplitude:.2f}"
            )

            # RMS approximation from fft_bins average
            if frame.fft_bins:
                rms = (sum(v * v for v in frame.fft_bins) / len(frame.fft_bins)) ** 0.5
            else:
                rms = 0.0
            self.query_one("#rms-label", Label).update(f"RMS:    {rms:.2f}")

            buf_size = 0
            if self.engine and hasattr(self.engine, "queue"):
                buf_size = self.engine.queue.qsize()
            self.query_one("#flow-label", Label).update(f"FLOW:   {buf_size}/20")

            playing = getattr(self.engine, "playing", False) if self.engine else False
            status = "ACTIVE" if playing else "COMPLETE"
            self.query_one("#status-label", Label).update(f"STATUS: {status}")

            # Bottom strip
            progress = frame.metadata.get("progress", 0)
            bottom = self.query_one("#bottom-strip", BottomStrip)
            bottom.set_data(dominant, frame.peak_amplitude, progress)

            # Hide "no file" message when we receive frames
            msg = self.query_one("#center-message", Label)
            msg.display = False

        except Exception:
            pass

    def action_open_file(self):
        """Show file input prompt."""
        try:
            file_input = self.query_one("#file-input", Input)
            file_input.display = not file_input.display
            if file_input.display:
                file_input.focus()
                file_input.value = ""
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted):
        """Handle file path submission."""
        file_path = event.value.strip()
        # Hide the input
        file_input = self.query_one("#file-input", Input)
        file_input.display = False

        if file_path and self.on_file_load:
            await self.on_file_load(file_path)
            self._update_header_filename()

    def action_toggle_pause(self):
        """Pause or resume playback."""
        self._paused = not self._paused
        if self.on_pause_toggle:
            self.on_pause_toggle(self._paused)
        try:
            status = "PAUSED" if self._paused else "ACTIVE"
            self.query_one("#status-label", Label).update(f"STATUS: {status}")
        except Exception:
            pass
