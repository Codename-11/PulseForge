import asyncio
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Grid
from textual.widgets import Header, Footer, Static, ProgressBar, Label
from core.models import SignalFrame

class FrequencyBar(Static):
    def __init__(self, label: str):
        super().__init__()
        self.label = label
        self.value = 0.0

    def update_value(self, val: float):
        self.value = val
        self.refresh()

    def render(self) -> str:
        # Drawing a vertical bar with blocks
        max_height = 15
        filled_height = int(self.value * max_height)
        # Handle 0 case
        filled_height = max(0, min(max_height, filled_height))
        
        blocks = "█" * filled_height
        # Pad with newlines to push the blocks to the bottom
        padding = "\n" * (max_height - filled_height)
        return f"{padding}{blocks}\n[ {self.label} ]"

class PulseForgeTUI(App):
    CSS_PATH = "../styles/theme.tcss"

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.bars = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            # LEFT: TELEMETRY
            with Vertical(classes="side-panel"):
                yield Label("SIGNAL DATA")
                yield ProgressBar(total=100, id="buffer-bar")
                yield Label("PEAK: 0.00", id="peak-label")
                yield Label("FLOW: ACTIVE")
            
            # CENTER: VISUALIZER (The main 8-bar grid)
            with Grid(id="visualizer-grid"):
                for i in range(8):
                    bar = FrequencyBar(f"M{i}")
                    self.bars.append(bar)
                    yield bar
            
            # RIGHT: CHANNEL MONITORS
            with Vertical(classes="side-panel"):
                yield Label("MONITORS")
                for i in range(6):
                    yield Static(f"M{i} WAVEFORM [----]", classes="monitor-line")
        yield Footer()

    async def update_ui(self, frame: SignalFrame):
        """Subscriber callback updated by the Engine."""
        # Update vertical bars
        for i, val in enumerate(frame.fft_bins):
            if i < len(self.bars):
                self.bars[i].update_value(val)
        
        # Update telemetry
        # self.query_one("#peak-label").update(f"PEAK: {frame.peak_amplitude:.2f}")

    async def on_mount(self):
        # Register this UI instance as a subscriber to the engine
        self.engine.add_subscriber(self.update_ui)
        self.title = "PULSEFORGE ENGINE v1.0"
