import asyncio
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static, Label
from core.models import SignalFrame


BAND_LABELS = ["SUB", "BASS", "LOW", "MID", "HMID", "HIGH", "AIR1", "AIR2"]
FREQ_LABELS = ["20Hz", "60Hz", "160Hz", "400Hz", "1kHz", "2.5kHz", "6kHz", "12kHz"]

DECAY_RATE = 0.85
PEAK_HOLD_TIME = 0.6
PEAK_DECAY_RATE = 0.92
RENDER_FPS = 30


class FrequencyBar(Static):
    """A single vertical frequency bar with gravity decay and peak-hold ghost."""

    def __init__(self, label: str, freq_label: str, index: int):
        super().__init__()
        self.label = label
        self.freq_label = freq_label
        self.index = index
        self.value = 0.0
        self.target = 0.0  # Latest raw value from frame
        self.peak = 0.0
        self.peak_time = 0.0
        self._dirty = False

    def set_target(self, val: float):
        """Set the target value — actual animation happens in tick()."""
        self.target = val
        self._dirty = True

    def tick(self):
        """Called by render timer — applies gravity/peak logic and refreshes."""
        if not self._dirty:
            return
        self._dirty = False
        now = time.monotonic()

        # Gravity
        if self.target >= self.value:
            self.value = self.target
        else:
            self.value = max(self.target, self.value * DECAY_RATE)

        # Peak-hold
        if self.target >= self.peak:
            self.peak = self.target
            self.peak_time = now
        elif now - self.peak_time > PEAK_HOLD_TIME:
            self.peak *= PEAK_DECAY_RATE

        # Always mark dirty if value > 0 (gravity still decaying)
        if self.value > 0.01:
            self._dirty = True

        self.refresh()

    def render(self) -> str:
        max_height = 14
        filled = int(self.value * max_height)
        filled = max(0, min(max_height, filled))
        peak_pos = int(self.peak * max_height)
        peak_pos = max(0, min(max_height, peak_pos))

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
        self._dirty = False

    def push(self, val: float):
        self.history.append(val)
        if len(self.history) > 16:
            self.history.pop(0)
        self._dirty = True

    def tick(self):
        if not self._dirty:
            return
        self._dirty = False
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
        return f" {title}    {self.filename:^30}    {clock} "


class BottomStrip(Static):
    """Horizontal strip showing BPM, dominant freq, max amplitude, progress."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bpm = "---"
        self.dominant_freq = "---"
        self.max_amp = "0.00"
        self.progress = "0%"
        self._dirty = False

    def set_data(self, dominant_freq: str, max_amp: float, progress: float):
        self.dominant_freq = dominant_freq
        self.max_amp = f"{max_amp:.2f}"
        self.progress = f"{int(progress * 100)}%"
        self._dirty = True

    def tick(self):
        if not self._dirty:
            return
        self._dirty = False
        self.refresh()

    def render(self) -> str:
        return (
            f"  BPM: {self.bpm}  │  "
            f"FREQ: {self.dominant_freq}  │  "
            f"MAX: {self.max_amp}  │  "
            f"PROGRESS: {self.progress}"
        )


def _open_file_dialog() -> str:
    """Open a native Windows file picker. Runs in a thread to avoid blocking."""
    from tkinter import Tk, filedialog
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    file_path = filedialog.askopenfilename(
        title="Open Audio File — PulseForge",
        filetypes=[("Audio Files", "*.wav *.mp3"), ("WAV", "*.wav"), ("MP3", "*.mp3")],
    )
    root.destroy()
    return file_path


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

        # Cached widget references — populated on mount
        self._w_header: Optional[HeaderBar] = None
        self._w_peak: Optional[Label] = None
        self._w_rms: Optional[Label] = None
        self._w_flow: Optional[Label] = None
        self._w_status: Optional[Label] = None
        self._w_bottom: Optional[BottomStrip] = None
        self._w_message: Optional[Label] = None

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")

        with Horizontal(id="main-container"):
            with Vertical(id="left-panel", classes="side-panel"):
                yield Label("── SIGNAL DATA ──", classes="panel-title")
                yield Label("PEAK:   0.00", id="peak-label")
                yield Label("RMS:    0.00", id="rms-label")
                yield Label("FLOW:   0/20", id="flow-label")
                yield Label("STATUS: IDLE", id="status-label")

            with Vertical(id="center-panel"):
                yield Label("── VISUALIZER ──", id="viz-title", classes="panel-title")
                with Horizontal(id="visualizer-grid"):
                    for i, name in enumerate(BAND_LABELS):
                        bar = FrequencyBar(name, FREQ_LABELS[i], i)
                        self.bars.append(bar)
                        yield bar
                yield Label("No file loaded — press O to open", id="center-message")

            with Vertical(id="right-panel", classes="side-panel"):
                yield Label("── MONITORS ──", classes="panel-title")
                for i, name in enumerate(BAND_LABELS):
                    mon = MonitorLine(name, i)
                    self.monitors.append(mon)
                    yield mon

        yield BottomStrip(id="bottom-strip")
        yield Footer()

    async def on_mount(self):
        self._start_time = time.monotonic()

        # Cache widget references — no more query_one per frame
        self._w_header = self.query_one("#header-bar", HeaderBar)
        self._w_peak = self.query_one("#peak-label", Label)
        self._w_rms = self.query_one("#rms-label", Label)
        self._w_flow = self.query_one("#flow-label", Label)
        self._w_status = self.query_one("#status-label", Label)
        self._w_bottom = self.query_one("#bottom-strip", BottomStrip)
        self._w_message = self.query_one("#center-message", Label)

        # Register subscriber
        if self.engine is not None:
            self.engine.add_subscriber(self.update_ui)

        # Render timer — single repaint pass at fixed FPS
        self.set_interval(1.0 / RENDER_FPS, self._render_tick)

        # Clock timer — 1Hz
        self.set_interval(1.0, self._tick_clock)

        self._update_header_filename()

    def _render_tick(self):
        """Single render pass — ticks all dirty widgets at once."""
        for bar in self.bars:
            bar.tick()
        for mon in self.monitors:
            mon.tick()
        if self._w_bottom:
            self._w_bottom.tick()

    def _tick_clock(self):
        if self._w_header:
            self._w_header.update_clock()
        self._refresh_engine_status()

    def _update_header_filename(self):
        if not self._w_header:
            return
        if self.engine and self.engine.current_file:
            self._w_header.set_filename(Path(self.engine.current_file).name)
            if self._w_message:
                self._w_message.display = False
        else:
            self._w_header.set_filename("No file loaded")
            if self._w_message:
                self._w_message.display = True

    def _refresh_engine_status(self):
        if self.engine is None or not self._w_status:
            return
        if self.engine.playing:
            status = "PAUSED" if self._paused else "ACTIVE"
        elif self._last_frame is not None:
            status = "COMPLETE"
        else:
            status = "IDLE"
        self._w_status.update(f"STATUS: {status}")
        self._update_header_filename()

    async def update_ui(self, frame: SignalFrame):
        """Subscriber callback — stores data, actual render happens on timer."""
        if self._paused:
            return

        self._last_frame = frame
        self._frame_count += 1

        # Push data to widgets (no refresh yet — timer handles that)
        for i, val in enumerate(frame.fft_bins):
            if i < len(self.bars):
                self.bars[i].set_target(val)
            if i < len(self.monitors):
                self.monitors[i].push(val)

        # Find dominant band
        if frame.fft_bins:
            max_idx = max(range(len(frame.fft_bins)), key=lambda i: frame.fft_bins[i])
            dominant = BAND_LABELS[max_idx] if max_idx < len(BAND_LABELS) else "---"
        else:
            dominant = "---"

        # Update telemetry (direct update — these are simple text, cheap)
        if self._w_peak:
            self._w_peak.update(f"PEAK:   {frame.peak_amplitude:.2f}")

        if self._w_rms and frame.fft_bins:
            rms = (sum(v * v for v in frame.fft_bins) / len(frame.fft_bins)) ** 0.5
            self._w_rms.update(f"RMS:    {rms:.2f}")

        if self._w_flow and self.engine:
            self._w_flow.update(f"FLOW:   {self.engine.queue.qsize()}/20")

        if self._w_status:
            status = "ACTIVE" if self.engine and self.engine.playing else "COMPLETE"
            self._w_status.update(f"STATUS: {status}")

        # Bottom strip — batched via dirty flag
        if self._w_bottom:
            progress = frame.metadata.get("progress", 0)
            self._w_bottom.set_data(dominant, frame.peak_amplitude, progress)

        # Hide placeholder
        if self._w_message and self._w_message.display:
            self._w_message.display = False

    def action_open_file(self):
        """Open native file picker in a background thread."""
        def _pick():
            file_path = _open_file_dialog()
            if file_path:
                self.call_from_thread(self._handle_file_picked, file_path)
        threading.Thread(target=_pick, daemon=True).start()

    def _handle_file_picked(self, file_path: str):
        if file_path and self.on_file_load:
            asyncio.get_event_loop().create_task(self._do_file_load(file_path))

    async def _do_file_load(self, file_path: str):
        if self.on_file_load:
            await self.on_file_load(file_path)
            self._update_header_filename()

    def action_toggle_pause(self):
        self._paused = not self._paused
        if self.on_pause_toggle:
            self.on_pause_toggle(self._paused)
        if self._w_status:
            status = "PAUSED" if self._paused else "ACTIVE"
            self._w_status.update(f"STATUS: {status}")
