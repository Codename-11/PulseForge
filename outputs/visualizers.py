"""Visualization renderer widgets for PulseForge FFT display.

Each visualizer is a self-contained Textual Static widget that receives
FFT data via set_frame() and renders a unique visualization style.
"""

from __future__ import annotations

import math
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
SMOOTHING = 0.4  # EMA for visualizer smoothing (higher = more responsive)

NUM_BANDS = 8


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


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

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        for i in range(NUM_BANDS):
            val = fft_bins[i] if i < len(fft_bins) else 0.0
            self._targets[i] = max(0.0, min(1.0, val))

    def tick(self) -> None:
        now = time.monotonic()
        any_active = False

        for i in range(NUM_BANDS):
            # Gravity decay toward target
            if self._targets[i] >= self._values[i]:
                self._values[i] = self._targets[i]
            else:
                self._values[i] = max(self._targets[i], self._values[i] * DECAY_RATE)

            # Peak hold — use monotonic time consistently
            if self._targets[i] > self._peaks[i]:
                self._peaks[i] = self._targets[i]
                self._peak_times[i] = now
            elif now - self._peak_times[i] > PEAK_HOLD_TIME:
                self._peaks[i] *= PEAK_DECAY
                if self._peaks[i] < 0.01:
                    self._peaks[i] = 0.0

            if self._values[i] > 0.01 or self._peaks[i] > 0.01:
                any_active = True

        # Always refresh while animating (gravity/peak decay)
        if any_active or any(t > 0.01 for t in self._targets):
            self.refresh()

    def render(self) -> str:
        rows = self.ROWS
        col_width = self.BAR_WIDTH + self.GAP
        total_width = col_width * NUM_BANDS

        grid: list[list[str]] = [[" "] * total_width for _ in range(rows)]

        third = rows // 3
        for band in range(NUM_BANDS):
            bar_h = int(self._values[band] * rows)
            bar_h = max(0, min(rows, bar_h))
            peak_h = int(self._peaks[band] * rows)
            peak_h = max(0, min(rows, peak_h))
            x_start = band * col_width + 1

            for row_from_bottom in range(bar_h):
                draw_row = rows - 1 - row_from_bottom
                ch = "▓" if row_from_bottom < third else "█"
                for dx in range(self.BAR_WIDTH):
                    if x_start + dx < total_width:
                        grid[draw_row][x_start + dx] = ch

            # Peak marker — only draw above bar, not on it
            if peak_h > bar_h and peak_h > 0:
                pr = rows - peak_h
                if 0 <= pr < rows:
                    for dx in range(self.BAR_WIDTH):
                        if x_start + dx < total_width:
                            grid[pr][x_start + dx] = "━"

        lines = ["".join(row) for row in grid]

        hz_line = ""
        for label in HZ_LABELS:
            hz_line += label.center(col_width)
        lines.append(hz_line)

        band_line = ""
        for label in BAND_LABELS:
            band_line += label.center(col_width)
        lines.append(band_line)

        return "\n".join(lines)


# ===================================================================
# 2. WaveformVisualizer
# ===================================================================

class WaveformVisualizer(Static):
    """Scrolling oscilloscope showing per-band amplitude mix."""

    WIDTH = 80
    HEIGHT = 12

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Store full FFT mix as amplitude per column
        self._buffer: deque[float] = deque([0.0] * self.WIDTH, maxlen=self.WIDTH)
        self._smooth_val: float = 0.0

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        # Weighted mix: bass-heavy for visible waveform movement
        if fft_bins:
            weights = [0.25, 0.20, 0.15, 0.12, 0.10, 0.08, 0.05, 0.05]
            val = sum(fft_bins[i] * weights[i] for i in range(min(len(fft_bins), len(weights))))
        else:
            val = 0.0
        # Smooth to reduce jitter
        self._smooth_val = SMOOTHING * val + (1 - SMOOTHING) * self._smooth_val
        self._buffer.append(max(0.0, min(1.0, self._smooth_val)))

    def tick(self) -> None:
        self.refresh()

    def render(self) -> str:
        height = self.HEIGHT
        mid = height // 2

        grid: list[list[str]] = [[" "] * self.WIDTH for _ in range(height)]

        for col, amp in enumerate(self._buffer):
            extent = amp * mid
            full_rows = int(extent)
            frac = extent - full_rows

            # Draw upward from center
            for r in range(full_rows):
                row = mid - 1 - r
                if 0 <= row < height:
                    grid[row][col] = "█"
            if frac > 0.1:
                char_idx = max(1, int(frac * (len(RENDER_CHARS) - 1)))
                row = mid - 1 - full_rows
                if 0 <= row < height:
                    grid[row][col] = RENDER_CHARS[char_idx]

            # Mirror downward from center
            for r in range(full_rows):
                row = mid + r
                if 0 <= row < height:
                    grid[row][col] = "█"
            if frac > 0.1:
                char_idx = max(1, int(frac * (len(RENDER_CHARS) - 1)))
                row = mid + full_rows
                if 0 <= row < height:
                    grid[row][col] = RENDER_CHARS[char_idx]

        # Center baseline
        for col in range(self.WIDTH):
            if grid[mid][col] == " " and grid[mid - 1][col] == " ":
                grid[mid][col] = "─"

        return "\n".join("".join(row) for row in grid)


# ===================================================================
# 3. SpectrogramVisualizer
# ===================================================================

class SpectrogramVisualizer(Static):
    """2D time x frequency heatmap scrolling left."""

    WIDTH = 60

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._history: deque[list[float]] = deque(
            [[0.0] * NUM_BANDS for _ in range(self.WIDTH)],
            maxlen=self.WIDTH,
        )

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        frame = [
            max(0.0, min(1.0, fft_bins[i] if i < len(fft_bins) else 0.0))
            for i in range(NUM_BANDS)
        ]
        self._history.append(frame)

    def tick(self) -> None:
        self.refresh()

    def render(self) -> str:
        lines: list[str] = []
        for band_idx in range(NUM_BANDS - 1, -1, -1):
            label = BAND_LABELS[band_idx].rjust(4)
            row_chars: list[str] = []
            for col in range(len(self._history)):
                val = self._history[col][band_idx]
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
    BAR_W = 3
    SHADOW_W = 1
    SPACING = 2

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._values: list[float] = [0.0] * NUM_BANDS
        self._targets: list[float] = [0.0] * NUM_BANDS

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        for i in range(NUM_BANDS):
            val = fft_bins[i] if i < len(fft_bins) else 0.0
            self._targets[i] = max(0.0, min(1.0, val))

    def tick(self) -> None:
        any_active = False
        for i in range(NUM_BANDS):
            if self._targets[i] >= self._values[i]:
                self._values[i] = self._targets[i]
            else:
                self._values[i] = max(self._targets[i], self._values[i] * DECAY_RATE)

            if self._values[i] > 0.01:
                any_active = True

        if any_active or any(t > 0.01 for t in self._targets):
            self.refresh()

    def render(self) -> str:
        mh = self.MAX_HEIGHT
        col_w = self.BAR_W + self.SHADOW_W + self.SPACING
        total_w = col_w * NUM_BANDS + 1
        rows = mh + 2  # +1 cap, +1 floor

        grid: list[list[str]] = [[" "] * total_w for _ in range(rows)]

        for band in range(NUM_BANDS):
            bar_h = max(0, int(self._values[band] * mh))
            if bar_h == 0:
                continue  # Don't draw empty bars

            x = band * col_w + 1

            # Top cap
            cap_row = rows - 1 - bar_h - 1
            if 0 <= cap_row < rows:
                for dx in range(self.BAR_W):
                    if x + dx < total_w:
                        grid[cap_row][x + dx] = "▄"

            # Front face + shadow
            for h in range(bar_h):
                row = rows - 2 - h  # -2 to leave floor row
                if 0 <= row < rows:
                    for dx in range(self.BAR_W):
                        if x + dx < total_w:
                            grid[row][x + dx] = "█"
                    sx = x + self.BAR_W
                    if sx < total_w:
                        grid[row][sx] = "▓"

        lines = ["".join(row) for row in grid]

        # Floor + labels
        short_labels = ["SUB", "BAS", "LOW", "MID", "HMD", "HGH", "AR1", "AR2"]
        label_line = " "
        for lbl in short_labels:
            label_line += lbl.center(col_w)
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
    SCENE_WIDTH = 60

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._fft: list[float] = [0.0] * NUM_BANDS
        self._smooth_fft: list[float] = [0.0] * NUM_BANDS
        self._peak: float = 0.0
        self._smooth_peak: float = 0.0
        self._grid_offset: int = 0
        self._tick_count: int = 0

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        self._fft = [
            max(0.0, min(1.0, fft_bins[i] if i < len(fft_bins) else 0.0))
            for i in range(NUM_BANDS)
        ]
        self._peak = max(0.0, min(1.0, peak))

    def tick(self) -> None:
        self._tick_count += 1

        # Smooth FFT and peak for stable visuals
        for i in range(NUM_BANDS):
            self._smooth_fft[i] = SMOOTHING * self._fft[i] + (1 - SMOOTHING) * self._smooth_fft[i]
        self._smooth_peak = SMOOTHING * self._peak + (1 - SMOOTHING) * self._smooth_peak

        # Grid scrolls at ~10 FPS (every 3rd tick at 30 FPS render)
        if self._tick_count % 3 == 0:
            self._grid_offset += 1

        self.refresh()

    def _render_sun(self) -> list[str]:
        w = self.SCENE_WIDTH
        bass = max(self._smooth_fft[0], self._smooth_peak * 0.4)
        radius = int(3 + bass * 4)
        lines: list[str] = []

        for row in range(self.SUN_ROWS):
            dy = self.SUN_ROWS - row
            if dy <= radius:
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
        w = self.SCENE_WIDTH
        heights: list[float] = []
        for col in range(w):
            band_f = col / w * (NUM_BANDS - 1)
            band_lo = int(band_f)
            band_hi = min(band_lo + 1, NUM_BANDS - 1)
            frac = band_f - band_lo
            val = self._smooth_fft[band_lo] * (1 - frac) + self._smooth_fft[band_hi] * frac
            heights.append(val)

        rows = self.MOUNTAIN_ROWS
        lines: list[str] = []

        for row in range(rows):
            threshold = (rows - row) / rows
            line = list(" " * w)
            for col in range(w):
                if heights[col] >= threshold:
                    line[col] = "█"
                elif heights[col] >= threshold - 0.15:
                    line[col] = "▄"
            if row == rows - 1:
                for col in range(w):
                    if line[col] == " ":
                        line[col] = "═"
            lines.append("".join(line))

        return lines

    def _render_grid(self) -> list[str]:
        w = self.SCENE_WIDTH
        cx = w // 2
        lines: list[str] = []

        for row in range(self.GRID_ROWS):
            line = list(" " * w)
            t = (row + 1) / self.GRID_ROWS
            spread = int(t * (w // 2 - 2))

            lx = cx - spread
            rx = cx + spread

            if 0 <= lx < w:
                line[lx] = "╲"
            if 0 <= rx < w:
                line[rx] = "╱"
            line[cx] = "│"

            # Horizontal lines at intervals (shifted by grid_offset for scroll)
            if (row + self._grid_offset) % 4 == 0:
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
    COL_WIDTH = 6
    AGE_DECAY = 0.93

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._history: deque[list[float]] = deque(maxlen=self.HEIGHT)
        for _ in range(self.HEIGHT):
            self._history.append([0.0] * NUM_BANDS)

    def set_frame(self, fft_bins: list[float], peak: float, timestamp: float) -> None:
        frame = [
            max(0.0, min(1.0, fft_bins[i] if i < len(fft_bins) else 0.0))
            for i in range(NUM_BANDS)
        ]
        self._history.appendleft(frame)

    def tick(self) -> None:
        self.refresh()

    def render(self) -> str:
        lines: list[str] = []

        for row_idx, frame in enumerate(self._history):
            age_factor = self.AGE_DECAY ** row_idx
            row_parts: list[str] = []

            for band in range(NUM_BANDS):
                val = frame[band] * age_factor
                ci = int(val * (len(HEAT_CHARS) - 1))
                ci = max(0, min(len(HEAT_CHARS) - 1, ci))
                ch = HEAT_CHARS[ci]
                row_parts.append(ch * self.COL_WIDTH)

            lines.append(" ".join(row_parts))

        label_parts = [lbl.center(self.COL_WIDTH) for lbl in BAND_LABELS]
        lines.append(" ".join(label_parts))

        return "\n".join(lines)
