import asyncio
import time
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Grid
from textual.widgets import Header, Footer, Static, ProgressBar, Label
from core.models import SignalFrame


BAND_LABELS = ["SUB", "BASS", "LOW", "MID", "HMID", "HIGH", "AIR1", "AIR2"]
DECAY_RATE = 0.85       # Gravity: multiply current value each frame when no signal
PEAK_HOLD_TIME = 0.6    # Seconds before peak marker starts falling
PEAK_DECAY_RATE = 0.92  # How fast the peak ghost falls


class FrequencyBar(Static):
    def __init__(self, label: str, index: int):
        super().__init__()
        self.label = label
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
        max_height = 15
        filled = int(self.value * max_height)
        filled = max(0, min(max_height, filled))
        peak_pos = int(self.peak * max_height)
        peak_pos = max(0, min(max_height, peak_pos))

        lines = []
        for row in range(max_height, 0, -1):
            if row <= filled:
                lines.append("█")
            elif row == peak_pos and peak_pos > filled:
                lines.append("▔")
            else:
                lines.append(" ")

        return "\n".join(lines) + f"\n[{self.label}]"


class MonitorLine(Static):
    """Per-channel mini waveform monitor."""

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
        return f"{self.label} [{wave}]"


class PulseForgeTUI(App):
    CSS_PATH = "../styles/theme.tcss"

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.bars: list[FrequencyBar] = []
        self.monitors: list[MonitorLine] = []
        self._frame_count = 0
        self._start_time = 0.0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            # LEFT: TELEMETRY
            with Vertical(classes="side-panel"):
                yield Label("SIGNAL DATA", classes="panel-title")
                yield Label("PEAK: 0.00", id="peak-label")
                yield Label("FPS:  0", id="fps-label")
                yield Label("BUF:  0/20", id="buffer-label")
                yield Label("TIME: 0.0s", id="time-label")
                yield ProgressBar(total=100, id="buffer-bar")
                yield Label("STATUS: IDLE", id="status-label")

            # CENTER: VISUALIZER
            with Grid(id="visualizer-grid"):
                for i, name in enumerate(BAND_LABELS):
                    bar = FrequencyBar(name, i)
                    self.bars.append(bar)
                    yield bar

            # RIGHT: CHANNEL MONITORS
            with Vertical(classes="side-panel"):
                yield Label("MONITORS", classes="panel-title")
                for i, name in enumerate(BAND_LABELS):
                    mon = MonitorLine(name, i)
                    self.monitors.append(mon)
                    yield mon

        yield Footer()

    async def update_ui(self, frame: SignalFrame):
        """Subscriber callback — fed by the engine broadcast loop."""
        self._frame_count += 1
        elapsed = time.monotonic() - self._start_time if self._start_time else 1.0
        fps = self._frame_count / max(elapsed, 0.001)

        # Update frequency bars and monitors
        for i, val in enumerate(frame.fft_bins):
            if i < len(self.bars):
                self.bars[i].update_value(val)
            if i < len(self.monitors):
                self.monitors[i].push(val)

        # Update telemetry labels
        try:
            self.query_one("#peak-label", Label).update(
                f"PEAK: {frame.peak_amplitude:.2f}"
            )
            self.query_one("#fps-label", Label).update(f"FPS:  {int(fps)}")
            self.query_one("#buffer-label", Label).update(
                f"BUF:  {self.engine.queue.qsize()}/20"
            )
            self.query_one("#time-label", Label).update(
                f"TIME: {frame.timestamp:.1f}s"
            )

            progress = frame.metadata.get("progress", 0)
            self.query_one("#buffer-bar", ProgressBar).update(
                progress=int(progress * 100)
            )

            status = "COMPLETE" if not self.engine.running else "ACTIVE"
            self.query_one("#status-label", Label).update(f"STATUS: {status}")
        except Exception:
            pass

    async def on_mount(self):
        self.engine.add_subscriber(self.update_ui)
        self._start_time = time.monotonic()
        self.title = "PULSEFORGE ENGINE v1.0"
        self.sub_title = "Press Q to quit"
