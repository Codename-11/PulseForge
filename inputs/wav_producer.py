import asyncio
import numpy as np
from core.models import SignalFrame

class WavProducer:
    """
    Mock Producer that simulates FFT data. 
    Phase 1 will replace this with real WAV/MP3 parsing.
    """
    def __init__(self, engine):
        self.engine = engine

    async def run(self):
        t = 0
        while True:
            # Generate dummy FFT bins (8 bands)
            # We use sin waves with different offsets to simulate movement
            bins = [abs(np.sin(t + i*0.8)) * np.random.uniform(0.6, 1.0) for i in range(8)]
            
            frame = SignalFrame(
                timestamp=t,
                peak_amplitude=max(bins),
                fft_bins=bins
            )
            
            await self.engine.push_frame(frame)
            
            # Simulate 30 FPS update rate
            await asyncio.sleep(1/30)
            t += 0.033
