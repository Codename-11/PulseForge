import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static, Label
from core.models import SignalFrame
from outputs.visualizers import (
    BarsVisualizer, WaveformVisualizer, SpectrogramVisualizer,
    IsometricVisualizer, RetrowaveVisualizer, WaterfallVisualizer,
)


# ── Shared Constants ──

BAND_LABELS = ["SUB", "BASS", "LOW", "MID", "HMID", "HIGH", "AIR1", "AIR2"]
FREQ_LABELS = ["20Hz", "60Hz", "160Hz", "400Hz", "1kHz", "2.5kHz", "6kHz", "12kHz"]
DECAY_RATE = 0.85
PEAK_HOLD_TIME = 0.6
PEAK_DECAY_RATE = 0.92
RENDER_FPS = 30
MONITOR_HISTORY = 24

SETTINGS_DEFS = [
    ("decay_rate", "Decay Rate", 0.0, 1.0, 0.05, lambda v: f"{v:.2f}"),
    ("peak_hold", "Peak Hold", 0.1, 2.0, 0.1, lambda v: f"{v:.1f}s"),
    ("smoothing", "Smoothing", 0.0, 1.0, 0.05, lambda v: f"{v:.2f}"),
    ("volume", "Volume", 0.0, 1.0, 0.05, lambda v: f"{int(v * 100)}%"),
]

VIZ_MODES = [
    ("1", "Bars", BarsVisualizer),
    ("2", "Waveform", WaveformVisualizer),
    ("3", "Spectrogram", SpectrogramVisualizer),
    ("4", "Isometric", IsometricVisualizer),
    ("5", "Retrowave", RetrowaveVisualizer),
    ("6", "Waterfall", WaterfallVisualizer),
]


# ── Widget Classes ──


class HeaderBar(Static):
    """Custom header: title, view indicator, filename, FPS, clock."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.filename = "No file loaded"
        self.clock_text = ""
        self.view_name = "VISUALIZER"
        self.fps = 0

    def set_filename(self, name: str):
        self.filename = name
        self.refresh()

    def set_view(self, name: str):
        self.view_name = name
        self.refresh()

    def set_fps(self, fps: int):
        self.fps = fps
        self.refresh()

    def update_clock(self):
        tz = datetime.now().strftime("%Z")
        if not tz:
            tz = time.strftime("%Z")
        if not tz:
            tz = time.tzname[0] if time.tzname and time.tzname[0] else "UTC"
        self.clock_text = datetime.now().strftime("%m-%d-%y  %I:%M:%S %p") + f"  {tz}"
        self.refresh()

    def render(self) -> str:
        title = "PULSEFORGE v1.0"
        view = f"[{self.view_name}]"
        fps_text = f"{self.fps} FPS"
        if not self.clock_text:
            tz = datetime.now().strftime("%Z")
            if not tz:
                tz = time.strftime("%Z")
            if not tz:
                tz = time.tzname[0] if time.tzname and time.tzname[0] else "UTC"
            clock = datetime.now().strftime("%m-%d-%y  %I:%M:%S %p") + f"  {tz}"
        else:
            clock = self.clock_text
        return f" {title}  {view}    {self.filename}    {fps_text}    {clock} "


class MonitorLine(Static):
    """Per-channel rolling mini-waveform monitor."""

    def __init__(self, label: str, index: int):
        super().__init__()
        self.label = label
        self.index = index
        self.history: list[float] = [0.0] * MONITOR_HISTORY
        self._dirty = False

    def push(self, val: float):
        self.history.append(val)
        if len(self.history) > MONITOR_HISTORY:
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
        current = self.history[-1] if self.history else 0.0
        return f"{self.label:<4} [{wave}] {current:.2f}"


class ProgressStrip(Static):
    """Full-width track progress bar with elapsed/total time."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.elapsed = 0.0
        self.total_duration = 0.0
        self.progress = 0.0
        self.dominant_freq = "---"
        self.fps = 0
        self.status = "IDLE"
        self._dirty = False

    def set_data(self, elapsed: float = 0.0, total_duration: float = 0.0,
                 progress: float = 0.0, dominant_freq: str = "---",
                 fps: int = 0, status: str = "IDLE"):
        self.elapsed = elapsed
        self.total_duration = total_duration
        self.progress = progress
        self.dominant_freq = dominant_freq
        self.fps = fps
        self.status = status
        self._dirty = True

    def tick(self):
        if not self._dirty:
            return
        self._dirty = False
        self.refresh()

    def _format_time(self, seconds: float) -> str:
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m:02d}:{s:02d}"

    def render(self) -> str:
        elapsed_str = self._format_time(self.elapsed)
        total_str = self._format_time(self.total_duration)

        if self.status == "IDLE":
            return "  ● IDLE    No file loaded"
        elif self.status == "PAUSED":
            icon = "⏸ PAUSED"
        elif self.status == "COMPLETE":
            icon = "■ COMPLETE"
        else:
            icon = "▶ PLAYING"

        # Build progress bar
        bar_width = 26
        filled = int(self.progress * bar_width)
        filled = max(0, min(bar_width, filled))
        empty = bar_width - filled
        bar = "█" * filled + "░" * empty

        return (
            f"  {icon}   {bar}   "
            f"{elapsed_str} / {total_str}   "
            f"FREQ: {self.dominant_freq}   FPS: {self.fps}"
        )


# ── File Browser Screen ──

AUDIO_EXTENSIONS = {".wav", ".mp3"}


class FileEntry(Static):
    """A single file/directory entry in the browser."""

    def __init__(self, path: Path, is_dir: bool, selected: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.path = path
        self.is_dir = is_dir
        self.selected = selected

    def render(self) -> str:
        prefix = "▸ " if self.selected else "  "
        if self.is_dir:
            return f"{prefix}📁 {self.path.name}/"
        else:
            return f"{prefix}♪  {self.path.name}"


class FileBrowserScreen(Screen):
    """In-app file browser for selecting audio files."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
        Binding("up", "nav_up", "Up", show=False),
        Binding("down", "nav_down", "Down", show=False),
        Binding("enter", "select_entry", "Open", show=True),
        Binding("backspace", "go_up", "Parent Dir", show=True),
    ]

    def __init__(self):
        super().__init__()
        self._current_dir = Path.home()
        self._entries: list[tuple[Path, bool]] = []  # (path, is_dir)
        self._selected = 0

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")
        with Vertical(id="browser-container"):
            yield Label("", id="browser-path")
            yield VerticalScroll(Static("", id="browser-list"), id="browser-scroll")
        yield Footer()

    def on_mount(self):
        header = self.query_one("#header-bar", HeaderBar)
        header.set_view("OPEN FILE")
        header.update_clock()
        self._scan_dir()

    def _scan_dir(self):
        """Scan current directory for audio files and subdirectories."""
        self._entries = []
        self._selected = 0

        try:
            items = sorted(self._current_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            items = []

        for item in items:
            if item.name.startswith("."):
                continue
            if item.is_dir():
                self._entries.append((item, True))
            elif item.suffix.lower() in AUDIO_EXTENSIONS:
                self._entries.append((item, False))

        self._refresh_display()

    def _refresh_display(self):
        path_label = self.query_one("#browser-path", Label)
        path_label.update(f"── {self._current_dir} ──")

        lines = []
        for i, (path, is_dir) in enumerate(self._entries):
            prefix = "▸ " if i == self._selected else "  "
            if is_dir:
                lines.append(f"{prefix}📁 {path.name}/")
            else:
                # Show file size
                try:
                    size_mb = path.stat().st_size / (1024 * 1024)
                    size_str = f"{size_mb:.1f}MB"
                except OSError:
                    size_str = ""
                lines.append(f"{prefix}♪  {path.name}  {size_str}")

        if not lines:
            lines.append("  (no audio files or folders)")

        display = self.query_one("#browser-list", Static)
        display.update("\n".join(lines))

    def action_pop_screen(self):
        self.app.pop_screen()

    def action_nav_up(self):
        if self._entries:
            self._selected = max(0, self._selected - 1)
            self._refresh_display()

    def action_nav_down(self):
        if self._entries:
            self._selected = min(len(self._entries) - 1, self._selected + 1)
            self._refresh_display()

    def action_select_entry(self):
        if not self._entries:
            return
        path, is_dir = self._entries[self._selected]
        if is_dir:
            self._current_dir = path
            self._scan_dir()
        else:
            # Selected an audio file — load it and go back
            self.app.pop_screen()
            if self.app.on_file_load:
                asyncio.get_event_loop().create_task(self.app.on_file_load(str(path)))

    def action_go_up(self):
        parent = self._current_dir.parent
        if parent != self._current_dir:
            self._current_dir = parent
            self._scan_dir()


# ── Screens ──


class VisualizerScreen(Screen):
    """Main audio visualizer screen (default)."""

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("o", "open_file", "Open", show=True),
        Binding("space", "toggle_pause", "Pause", show=True),
        Binding("s", "push_settings", "Settings", show=True),
        Binding("h", "push_help", "Help", show=True),
        Binding("r", "restart", "Restart", show=True),
        Binding("1", "viz_1", "Bars", show=False),
        Binding("2", "viz_2", "Wave", show=False),
        Binding("3", "viz_3", "Spec", show=False),
        Binding("4", "viz_4", "Iso", show=False),
        Binding("5", "viz_5", "Retro", show=False),
        Binding("6", "viz_6", "Fall", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.monitors: list[MonitorLine] = []
        self._active_viz = None
        self._viz_index = 0
        self._frame_count = 0
        self._start_time = 0.0
        self._last_frame: Optional[SignalFrame] = None

        # Cached widget references
        self._w_header: Optional[HeaderBar] = None
        self._w_peak: Optional[Label] = None
        self._w_rms: Optional[Label] = None
        self._w_flow: Optional[Label] = None
        self._w_fps_label: Optional[Label] = None
        self._w_file_label: Optional[Label] = None
        self._w_fmt_label: Optional[Label] = None
        self._w_time_label: Optional[Label] = None
        self._w_status: Optional[Label] = None
        self._w_progress: Optional[ProgressStrip] = None
        self._w_message: Optional[Label] = None

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")

        with Horizontal(id="main-container"):
            with Vertical(id="left-panel", classes="side-panel"):
                yield Label("── SIGNAL DATA ──", classes="panel-title")
                yield Label("PEAK:   0.00", id="peak-label")
                yield Label("RMS:    0.00", id="rms-label")
                yield Label("FLOW:   0/20", id="flow-label")
                yield Label("FPS:    0", id="fps-label")
                yield Label("", id="spacer-1")
                yield Label("── TRACK INFO ──", classes="panel-title")
                yield Label("FILE:   ---", id="file-label")
                yield Label("FMT:    ---", id="fmt-label")
                yield Label("TIME:   00:00 / 00:00", id="time-label")
                yield Label("", id="spacer-2")
                yield Label("STATUS: IDLE", id="status-label")

            with Vertical(id="center-panel"):
                yield Label("── 1:BARS  2:WAVE  3:SPEC  4:ISO  5:RETRO  6:FALL ──", id="viz-title", classes="panel-title")
                yield BarsVisualizer(id="active-viz")
                yield Label("No file loaded — press O to open", id="center-message")

            with Vertical(id="right-panel", classes="side-panel"):
                yield Label("── MONITORS ──", classes="panel-title")
                for i, name in enumerate(BAND_LABELS):
                    mon = MonitorLine(name, i)
                    self.monitors.append(mon)
                    yield mon

        yield ProgressStrip(id="progress-strip")
        yield Footer()

    async def on_mount(self):
        self._start_time = time.monotonic()

        # Cache widget references
        self._w_header = self.query_one("#header-bar", HeaderBar)
        self._w_peak = self.query_one("#peak-label", Label)
        self._w_rms = self.query_one("#rms-label", Label)
        self._w_flow = self.query_one("#flow-label", Label)
        self._w_fps_label = self.query_one("#fps-label", Label)
        self._w_file_label = self.query_one("#file-label", Label)
        self._w_fmt_label = self.query_one("#fmt-label", Label)
        self._w_time_label = self.query_one("#time-label", Label)
        self._w_status = self.query_one("#status-label", Label)
        self._w_progress = self.query_one("#progress-strip", ProgressStrip)
        self._w_message = self.query_one("#center-message", Label)

        self._active_viz = self.query_one("#active-viz")
        self._viz_index = 0

        self._w_header.set_view("VISUALIZER — BARS")

        # Register engine subscriber
        if self.app.engine is not None:
            self.app.engine.add_subscriber(self.update_ui)

        # Render timer — single repaint pass at fixed FPS
        self.set_interval(1.0 / RENDER_FPS, self._render_tick)

        # Clock timer — 1Hz
        self.set_interval(1.0, self._tick_clock)

        self._update_header_filename()

    def _render_tick(self):
        if self._active_viz:
            self._active_viz.tick()
        for mon in self.monitors:
            mon.tick()
        if self._w_progress:
            self._w_progress.tick()

    def _tick_clock(self):
        if self._w_header:
            self._w_header.update_clock()
        self._refresh_engine_status()

    def _format_time(self, seconds: float) -> str:
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m:02d}:{s:02d}"

    def _update_header_filename(self):
        if not self._w_header:
            return
        if self.app.engine and self.app.engine.current_file:
            name = Path(self.app.engine.current_file).name
            self._w_header.set_filename(name)
            if self._w_file_label:
                truncated = name if len(name) <= 16 else name[:13] + "..."
                self._w_file_label.update(f"FILE:   {truncated}")
            if self._w_message:
                self._w_message.display = False
        else:
            self._w_header.set_filename("No file loaded")
            if self._w_file_label:
                self._w_file_label.update("FILE:   ---")
            if self._w_message:
                self._w_message.display = True

    def _refresh_engine_status(self):
        if self.app.engine is None or not self._w_status:
            return
        if self.app.engine.playing:
            status = "PAUSED" if self.app._paused else "ACTIVE"
        elif self._last_frame is not None:
            status = "COMPLETE"
        else:
            status = "IDLE"
        self._w_status.update(f"STATUS: {status}")
        self._update_header_filename()

    async def _switch_viz(self, index: int):
        """Switch to visualization mode by index (0-5)."""
        if index == self._viz_index:
            return
        _, name, viz_class = VIZ_MODES[index]
        # Remove old viz — must await since remove() is async in Textual
        old = self.query_one("#active-viz")
        await old.remove()
        # Mount new viz
        center = self.query_one("#center-panel", Vertical)
        new_viz = viz_class(id="active-viz")
        await center.mount(new_viz, before=self.query_one("#center-message", Label))
        self._active_viz = new_viz
        # Update header
        if self._w_header:
            self._w_header.set_view(f"VISUALIZER — {name.upper()}")
        self._viz_index = index

    async def action_viz_1(self): await self._switch_viz(0)
    async def action_viz_2(self): await self._switch_viz(1)
    async def action_viz_3(self): await self._switch_viz(2)
    async def action_viz_4(self): await self._switch_viz(3)
    async def action_viz_5(self): await self._switch_viz(4)
    async def action_viz_6(self): await self._switch_viz(5)

    async def update_ui(self, frame: SignalFrame):
        """Subscriber callback — stores data, actual render happens on timer."""
        if self.app._paused:
            return

        if not self.is_current:
            return

        self._last_frame = frame
        self._frame_count += 1

        # Calculate FPS
        elapsed_wall = time.monotonic() - self._start_time
        fps = int(self._frame_count / elapsed_wall) if elapsed_wall > 0 else 0

        # Push data to active visualizer and monitors
        if self._active_viz:
            self._active_viz.set_frame(frame.fft_bins, frame.peak_amplitude, frame.timestamp)

        for i, val in enumerate(frame.fft_bins):
            if i < len(self.monitors):
                self.monitors[i].push(val)

        # Dominant band
        if frame.fft_bins:
            max_idx = max(range(len(frame.fft_bins)), key=lambda i: frame.fft_bins[i])
            dominant = BAND_LABELS[max_idx] if max_idx < len(BAND_LABELS) else "---"
        else:
            dominant = "---"

        # Calculate elapsed time from frame timestamp
        elapsed_time = frame.timestamp if frame.timestamp else 0.0
        total_duration = 0.0
        if self.app.engine and hasattr(self.app.engine, "total_duration"):
            total_duration = self.app.engine.total_duration or 0.0
        progress = frame.metadata.get("progress", 0)

        # Determine status
        if self.app._paused:
            status = "PAUSED"
        elif self.app.engine and self.app.engine.playing:
            status = "PLAYING"
        else:
            status = "COMPLETE"

        # Update telemetry labels
        if self._w_peak:
            self._w_peak.update(f"PEAK:   {frame.peak_amplitude:.2f}")

        if self._w_rms and frame.fft_bins:
            rms = (sum(v * v for v in frame.fft_bins) / len(frame.fft_bins)) ** 0.5
            self._w_rms.update(f"RMS:    {rms:.2f}")

        if self._w_flow and self.app.engine:
            self._w_flow.update(f"FLOW:   {self.app.engine.queue.qsize()}/20")

        if self._w_fps_label:
            self._w_fps_label.update(f"FPS:    {fps}")

        if self._w_time_label:
            e_str = self._format_time(elapsed_time)
            t_str = self._format_time(total_duration)
            self._w_time_label.update(f"TIME:   {e_str} / {t_str}")

        if self._w_fmt_label:
            fmt_str = frame.metadata.get("format", "---")
            sr = frame.metadata.get("sample_rate", "")
            if sr:
                sr_khz = int(sr) / 1000 if isinstance(sr, (int, float)) else sr
                fmt_str = f"{fmt_str} {sr_khz}kHz"
            self._w_fmt_label.update(f"FMT:    {fmt_str}")

        if self._w_status:
            self._w_status.update(f"STATUS: {status}")

        # Update header FPS
        if self._w_header:
            self._w_header.set_fps(fps)

        # Update progress strip
        if self._w_progress:
            self._w_progress.set_data(
                elapsed=elapsed_time,
                total_duration=total_duration,
                progress=progress,
                dominant_freq=dominant,
                fps=fps,
                status=status,
            )

        # Hide placeholder
        if self._w_message and self._w_message.display:
            self._w_message.display = False

    # ── Actions ──

    def action_open_file(self):
        self.app.push_screen(FileBrowserScreen())

    def action_toggle_pause(self):
        self.app._paused = not self.app._paused
        if self.app.on_pause_toggle:
            self.app.on_pause_toggle(self.app._paused)
        if self._w_status:
            status = "PAUSED" if self.app._paused else "ACTIVE"
            self._w_status.update(f"STATUS: {status}")

    def action_push_settings(self):
        self.app.push_screen("settings")

    def action_push_help(self):
        self.app.push_screen("help")

    def action_restart(self):
        if self.app.on_restart:
            asyncio.get_event_loop().create_task(self.app.on_restart())
        elif self.app.engine and self.app.engine.current_file and self.app.on_file_load:
            asyncio.get_event_loop().create_task(
                self.app.on_file_load(self.app.engine.current_file)
            )


class SettingsScreen(Screen):
    """Full-page settings screen with sliders."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
        Binding("up", "nav_up", "Up", show=False),
        Binding("down", "nav_down", "Down", show=False),
        Binding("left", "adjust_left", "Left", show=False),
        Binding("right", "adjust_right", "Right", show=False),
    ]

    def __init__(self):
        super().__init__()
        self._selected = 0

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")
        with Vertical(id="settings-content"):
            yield Static("", id="settings-display")
        yield Footer()

    def on_mount(self):
        header = self.query_one("#header-bar", HeaderBar)
        header.set_view("SETTINGS")
        header.update_clock()
        self._refresh_display()

    def _refresh_display(self):
        lines = [
            "── ENGINE SETTINGS ──",
            "",
        ]
        slider_width = 10
        for i, (key, label, mn, mx, _step, fmt) in enumerate(SETTINGS_DEFS):
            val = self.app._settings[key]
            norm = (val - mn) / (mx - mn) if mx > mn else 0.0
            filled = int(norm * slider_width)
            filled = max(0, min(slider_width, filled))
            empty = slider_width - filled
            bar = "█" * filled + "░" * empty

            prefix = "▸ " if i == self._selected else "  "
            lines.append(f"{prefix}{label:<12} [{bar}] {fmt(val)}")

        lines.append("")
        lines.append("↑↓ Navigate  ←→ Adjust  Esc Back")

        display = self.query_one("#settings-display", Static)
        display.update("\n".join(lines))

    def action_pop_screen(self):
        self.app.pop_screen()

    def action_nav_up(self):
        self._selected = max(0, self._selected - 1)
        self._refresh_display()

    def action_nav_down(self):
        self._selected = min(len(SETTINGS_DEFS) - 1, self._selected + 1)
        self._refresh_display()

    def action_adjust_left(self):
        self._adjust(-1)

    def action_adjust_right(self):
        self._adjust(1)

    def _adjust(self, direction: int):
        key, _label, mn, mx, step, _fmt = SETTINGS_DEFS[self._selected]
        old = self.app._settings[key]
        new = max(mn, min(mx, old + direction * step))
        new = round(new, 4)
        if new != old:
            self.app._settings[key] = new
            self._refresh_display()
            if self.app.on_settings_change:
                self.app.on_settings_change(key, new)


class HelpScreen(Screen):
    """Full-page keybinding reference screen."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")
        with Vertical(id="help-content"):
            yield Static("", id="help-display")
        yield Footer()

    def on_mount(self):
        header = self.query_one("#header-bar", HeaderBar)
        header.set_view("HELP")
        header.update_clock()

        text = "\n".join([
            "── KEYBINDINGS ──",
            "",
            "O          Open audio file",
            "Space      Pause / Resume",
            "R          Restart track",
            "S          Settings",
            "H          Help (this screen)",
            "Q          Quit",
            "",
            "1-6        Switch visualization mode",
            "           1:Bars  2:Waveform  3:Spectrogram",
            "           4:Isometric  5:Retrowave  6:Waterfall",
            "",
            "── ABOUT ──",
            "",
            "PulseForge Engine v1.0",
            "Async signal processing engine",
            "WAV / MP3 supported",
            "",
            "Press Esc to return",
        ])

        display = self.query_one("#help-display", Static)
        display.update(text)

    def action_pop_screen(self):
        self.app.pop_screen()


# ── App ──


class PulseForgeTUI(App):
    CSS_PATH = "../styles/theme.tcss"
    SCREENS = {"settings": SettingsScreen, "help": HelpScreen}

    def __init__(self, engine=None):
        super().__init__()
        self.engine = engine
        self._settings = {
            "decay_rate": 0.85,
            "peak_hold": 0.6,
            "smoothing": 0.3,
            "volume": 1.0,
        }
        self.on_file_load: Optional[Callable] = None
        self.on_pause_toggle: Optional[Callable] = None
        self.on_settings_change: Optional[Callable] = None
        self.on_restart: Optional[Callable] = None
        self._paused = False

    def on_mount(self):
        self.push_screen(VisualizerScreen())
