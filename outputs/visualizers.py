"""Visualization renderer widgets for PulseForge FFT display.

Each visualizer is a self-contained Textual Static widget that receives
FFT data via set_frame() and renders a unique visualization style.
"""

from __future__ import annotations

import time
from collections import deque

from textual.widgets import Static

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

BAND_LABELS = ["SUB", "BASS", "LOW", "MID", "HMID", "HIGH", "AIR1", "AIR2"]
RENDER_CHARS = " ▁▂▃▄▅▆▇█"
HEAT_CHARS = " ░▒▓█"

HZ_LABELS = ["20Hz", "60Hz", "160Hz", "400Hz", "1kHz", "2.5k", "6kHz", "12k"]

DECAY_RATE = 0.85
PEAK_HOLD_TIME = 0.6
PEAK_DECAY = 0.92

NUM_BANDS = 8


# ===================================================================
# 1. BarsVisualizer
# ===================================================================

class BarsVisualizer(Static):
    """8-band frequency bar display rendered as a single widget."""

    ROWS = 14
    BAR_WIDTH = 4
    GAP = 2

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._values: list[float] = [0.0] * NUM_BANDS
        self._targets: list[float] = [0.0] * NUM_BANDS
        self._peaks: list[float] = [0.0] * NUM_BANDS
        self._peak_times: list[float] = [0.0] * NUM_BANDS
        self._dirty = False

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        for i in range(NUM_BANDS):
            val = fft_bins[i] if i < len(fft_bins) else 0.0
            self._targets[i] = max(0.0, min(1.0, val))
            if self._targets[i] > self._peaks[i]:
                self._peaks[i] = self._targets[i]
                self._peak_times[i] = timestamp
        self._dirty = True

    def tick(self) -> None:
        now = time.monotonic()
        for i in range(NUM_BANDS):
            # Gravity decay toward target
            if self._targets[i] > self._values[i]:
                self._values[i] = self._targets[i]
            else:
                self._values[i] *= DECAY_RATE
                if self._values[i] < 0.01:
                    self._values[i] = 0.0

            # Peak hold then decay
            if now - self._peak_times[i] > PEAK_HOLD_TIME:
                self._peaks[i] *= PEAK_DECAY
                if self._peaks[i] < 0.01:
                    self._peaks[i] = 0.0

        if self._dirty:
            self._dirty = False
            self.refresh()

    def render(self) -> str:
        rows = self.ROWS
        col_width = self.BAR_WIDTH + self.GAP
        total_width = col_width * NUM_BANDS

        grid: list[list[str]] = [[" "] * total_width for _ in range(rows)]

        for band in range(NUM_BANDS):
            bar_h = int(self._values[band] * rows)
            peak_row = int(self._peaks[band] * rows)
            x_start = band * col_width + 1  # 1-char left margin

            third = rows // 3
            for row in range(rows):
                draw_row = rows - 1 - row  # row 0 = top
                if row < bar_h:
                    ch = "▓" if row < third else "█"
                    for dx in range(self.BAR_WIDTH):
                        if x_start + dx < total_width:
                            grid[draw_row][x_start + dx] = ch

            # Peak hold marker
            if peak_row > 0 and peak_row <= rows:
                pr = rows - peak_row
                if 0 <= pr < rows:
                    for dx in range(self.BAR_WIDTH):
                        if x_start + dx < total_width:
                            grid[pr][x_start + dx] = "━"

        lines = ["".join(row) for row in grid]

        # Hz labels row
        hz_line = ""
        for i, label in enumerate(HZ_LABELS):
            segment = label.center(col_width)
            hz_line += segment
        lines.append(hz_line)

        # Band name row
        band_line = ""
        for label in BAND_LABELS:
            segment = label.center(col_width)
            band_line += segment
        lines.append(band_line)

        return "\n".join(lines)


# ===================================================================
# 2. WaveformVisualizer
# ===================================================================

class WaveformVisualizer(Static):
    """Scrolling oscilloscope-style waveform display."""

    WIDTH = 80
    HEIGHT = 12

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._buffer: deque[float] = deque([0.0] * self.WIDTH, maxlen=self.WIDTH)
        self._dirty = False

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        amplitude = max(0.0, min(1.0, peak))
        self._buffer.append(amplitude)
        self._dirty = True

    def tick(self) -> None:
        if self._dirty:
            self._dirty = False
            self.refresh()

    def render(self) -> str:
        height = self.HEIGHT
        mid = height // 2
        block_chars = RENDER_CHARS  # " ▁▂▃▄▅▆▇█"

        grid: list[list[str]] = [[" "] * self.WIDTH for _ in range(height)]

        for col, amp in enumerate(self._buffer):
            # Half-height in rows (centered waveform extends mid rows up and down)
            extent = amp * mid
            full_rows = int(extent)
            frac = extent - full_rows

            # Draw upward from center
            for r in range(full_rows):
                row = mid - 1 - r
                if 0 <= row < height:
                    grid[row][col] = "█"
            # Fractional top
            if frac > 0.05:
                char_idx = int(frac * (len(block_chars) - 1))
                row = mid - 1 - full_rows
                if 0 <= row < height:
                    grid[row][col] = block_chars[char_idx]

            # Draw downward from center (mirror)
            for r in range(full_rows):
                row = mid + r
                if 0 <= row < height:
                    grid[row][col] = "█"
            if frac > 0.05:
                char_idx = int(frac * (len(block_chars) - 1))
                row = mid + full_rows
                if 0 <= row < height:
                    grid[row][col] = block_chars[char_idx]

        return "\n".join("".join(row) for row in grid)


# ===================================================================
# 3. SpectrogramVisualizer
# ===================================================================

class SpectrogramVisualizer(Static):
    """2D time x frequency heatmap scrolling left."""

    WIDTH = 60

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # History: each entry is a list of 8 band intensities
        self._history: deque[list[float]] = deque(
            [[0.0] * NUM_BANDS for _ in range(self.WIDTH)],
            maxlen=self.WIDTH,
        )
        self._dirty = False

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        frame = [
            max(0.0, min(1.0, fft_bins[i] if i < len(fft_bins) else 0.0))
            for i in range(NUM_BANDS)
        ]
        self._history.append(frame)
        self._dirty = True

    def tick(self) -> None:
        if self._dirty:
            self._dirty = False
            self.refresh()

    def render(self) -> str:
        lines: list[str] = []
        # Rows top to bottom: AIR2 (band 7) .. SUB (band 0)
        for band_idx in range(NUM_BANDS - 1, -1, -1):
            label = BAND_LABELS[band_idx].rjust(4)
            row_chars: list[str] = []
            for col in range(self.WIDTH):
                val = self._history[col][band_idx] if col < len(self._history) else 0.0
                ci = int(val * (len(HEAT_CHARS) - 1))
                ci = max(0, min(len(HEAT_CHARS) - 1, ci))
                row_chars.append(HEAT_CHARS[ci])
            lines.append(f"{label} │{''.join(row_chars)}│")
        return "\n".join(lines)


# ===================================================================
# 4. IsometricVisualizer
# ===================================================================

class IsometricVisualizer(Static):
    """3D isometric bar chart with front, shadow, and top faces."""

    MAX_HEIGHT = 12
    BAR_W = 3  # front face width
    SHADOW_W = 1
    SPACING = 2  # gap between bars

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._values: list[float] = [0.0] * NUM_BANDS
        self._targets: list[float] = [0.0] * NUM_BANDS
        self._dirty = False

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        for i in range(NUM_BANDS):
            val = fft_bins[i] if i < len(fft_bins) else 0.0
            self._targets[i] = max(0.0, min(1.0, val))
        self._dirty = True

    def tick(self) -> None:
        for i in range(NUM_BANDS):
            if self._targets[i] > self._values[i]:
                self._values[i] = self._targets[i]
            else:
                self._values[i] *= DECAY_RATE
                if self._values[i] < 0.01:
                    self._values[i] = 0.0

        if self._dirty:
            self._dirty = False
            self.refresh()

    def render(self) -> str:
        mh = self.MAX_HEIGHT
        col_w = self.BAR_W + self.SHADOW_W + self.SPACING
        total_w = col_w * NUM_BANDS + 1
        rows = mh + 1  # +1 for top cap row

        grid: list[list[str]] = [[" "] * total_w for _ in range(rows)]

        for band in range(NUM_BANDS):
            bar_h = max(0, int(self._values[band] * mh))
            x = band * col_w + 1

            # Top cap row
            if bar_h > 0:
                cap_row = rows - 1 - bar_h
                if 0 <= cap_row < rows:
                    for dx in range(self.BAR_W):
                        if x + dx < total_w:
                            grid[cap_row][x + dx] = "▄"

                # Body rows
                for h in range(bar_h):
                    row = rows - 1 - h
                    if 0 <= row < rows:
                        for dx in range(self.BAR_W):
                            if x + dx < total_w:
                                grid[row][x + dx] = "█"
                        # Right shadow
                        sx = x + self.BAR_W
                        if sx < total_w:
                            grid[row][sx] = "▓"

                # Bottom row — replace bottom of front with floor marker
                bottom_row = rows - 1
                if 0 <= bottom_row < rows:
                    for dx in range(self.BAR_W):
                        if x + dx < total_w:
                            grid[bottom_row][x + dx] = "█"
                    sx = x + self.BAR_W
                    if sx < total_w:
                        grid[bottom_row][sx] = "▓"

        lines = ["".join(row) for row in grid]

        # Band labels
        label_line = " "
        short_labels = ["SUB", "BAS", "LOW", "MID", "HMD", "HGH", "AR1", "AR2"]
        for i, lbl in enumerate(short_labels):
            segment = lbl.center(col_w)
            label_line += segment
        lines.append(label_line)

        return "\n".join(lines)


# ===================================================================
# 5. RetrowaveVisualizer
# ===================================================================

class RetrowaveVisualizer(Static):
    """Synthwave / retrowave horizon scene with sun, mountains, and grid."""

    SUN_ROWS = 4
    MOUNTAIN_ROWS = 3
    GRID_ROWS = 13
    TOTAL_HEIGHT = 20  # SUN + MOUNTAIN + GRID
    SCENE_WIDTH = 60

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._fft: list[float] = [0.0] * NUM_BANDS
        self._peak: float = 0.0
        self._grid_offset: int = 0
        self._dirty = False

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        self._fft = [
            max(0.0, min(1.0, fft_bins[i] if i < len(fft_bins) else 0.0))
            for i in range(NUM_BANDS)
        ]
        self._peak = max(0.0, min(1.0, peak))
        self._dirty = True

    def tick(self) -> None:
        self._grid_offset += 1
        if self._dirty:
            self._dirty = False
            self.refresh()

    def _render_sun(self) -> list[str]:
        """Render a pulsing half-circle sun."""
        w = self.SCENE_WIDTH
        # Bass intensity controls sun radius
        bass = max(self._fft[0] if self._fft else 0.0, self._peak * 0.5)
        radius = int(3 + bass * 5)
        lines: list[str] = []

        for row in range(self.SUN_ROWS):
            # Distance from bottom of sun (horizon)
            dy = self.SUN_ROWS - row
            if dy <= radius:
                # Half-circle width at this height
                import math
                half_w = int(math.sqrt(max(0, radius * radius - dy * dy)) * 1.8)
                cx = w // 2
                line = list(" " * w)
                for x in range(max(0, cx - half_w), min(w, cx + half_w + 1)):
                    dist = abs(x - cx)
                    if dist < half_w - 1:
                        line[x] = "█"
                    else:
                        line[x] = "▓"
                lines.append("".join(line))
            else:
                lines.append(" " * w)
        return lines

    def _render_mountains(self) -> list[str]:
        """Render FFT data as a mountain silhouette at the horizon."""
        w = self.SCENE_WIDTH
        # Interpolate 8 bands to full width
        heights: list[float] = []
        for col in range(w):
            # Map column to band (with interpolation)
            band_f = col / w * (NUM_BANDS - 1)
            band_lo = int(band_f)
            band_hi = min(band_lo + 1, NUM_BANDS - 1)
            frac = band_f - band_lo
            val = self._fft[band_lo] * (1 - frac) + self._fft[band_hi] * frac
            heights.append(val)

        rows = self.MOUNTAIN_ROWS
        lines: list[str] = []

        # Horizon separator line with mountains
        for row in range(rows):
            threshold = (rows - row) / rows
            line = list(" " * w)
            for col in range(w):
                if heights[col] >= threshold:
                    line[col] = "█"
                elif heights[col] >= threshold - 0.15:
                    line[col] = "▄"
            # Overlay horizon line chars on empty spots at the last mountain row
            if row == rows - 1:
                for col in range(w):
                    if line[col] == " ":
                        line[col] = "═"
            lines.append("".join(line))

        return lines

    def _render_grid(self) -> list[str]:
        """Render perspective grid scrolling toward viewer."""
        w = self.SCENE_WIDTH
        cx = w // 2
        lines: list[str] = []

        for row in range(self.GRID_ROWS):
            line = list(" " * w)
            # Perspective factor: wider at bottom
            t = (row + 1) / self.GRID_ROWS
            spread = int(t * (w // 2 - 2))

            # Left diagonal
            lx = cx - spread
            if 0 <= lx < w:
                line[lx] = "╲"

            # Right diagonal
            rx = cx + spread
            if 0 <= rx < w:
                line[rx] = "╱"

            # Center vertical
            line[cx] = "│"

            # Horizontal lines at intervals (shifted by grid_offset)
            if (row + self._grid_offset) % 3 == 0:
                for col in range(max(0, lx + 1), min(w, rx)):
                    if col != cx:
                        line[col] = "─"

            lines.append("".join(line))

        return lines

    def render(self) -> str:
        sun = self._render_sun()
        mountains = self._render_mountains()
        grid = self._render_grid()
        return "\n".join(sun + mountains + grid)


# ===================================================================
# 6. WaterfallVisualizer
# ===================================================================

class WaterfallVisualizer(Static):
    """Frequency bars scrolling downward over time with age-based fading."""

    HEIGHT = 20
    COL_WIDTH = 6  # chars per band column
    AGE_DECAY = 0.92

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # History: newest first (index 0 = newest)
        self._history: deque[list[float]] = deque(maxlen=self.HEIGHT)
        # Pre-fill with empty rows
        for _ in range(self.HEIGHT):
            self._history.append([0.0] * NUM_BANDS)
        self._dirty = False

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        frame = [
            max(0.0, min(1.0, fft_bins[i] if i < len(fft_bins) else 0.0))
            for i in range(NUM_BANDS)
        ]
        self._history.appendleft(frame)
        self._dirty = True

    def tick(self) -> None:
        if self._dirty:
            self._dirty = False
            self.refresh()

    def render(self) -> str:
        lines: list[str] = []

        for row_idx, frame in enumerate(self._history):
            # Age decay: older rows fade
            age_factor = self.AGE_DECAY ** row_idx
            row_parts: list[str] = []

            for band in range(NUM_BANDS):
                val = frame[band] * age_factor
                ci = int(val * (len(HEAT_CHARS) - 1))
                ci = max(0, min(len(HEAT_CHARS) - 1, ci))
                ch = HEAT_CHARS[ci]
                row_parts.append(ch * self.COL_WIDTH)

            suffix = ""
            if row_idx == 0:
                suffix = " ← newest"
            elif row_idx == len(self._history) - 1:
                suffix = " ← oldest"

            lines.append(" ".join(row_parts) + suffix)

        # Band labels at the bottom
        label_parts = [lbl.center(self.COL_WIDTH) for lbl in BAND_LABELS]
        lines.append(" ".join(label_parts))

        return "\n".join(lines)
