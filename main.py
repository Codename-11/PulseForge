import asyncio
import sys
from core.engine import PulseForgeEngine
from inputs.wav_producer import WavProducer
from outputs.tui_display import PulseForgeTUI

async def main_loop():
    # 1. Boot the Engine
    engine = PulseForgeEngine()
    
    # 2. Setup Input (The 'Producer')
    producer = WavProducer(engine)
    
    # 3. Setup UI (The 'Consumer')
    tui = PulseForgeTUI(engine)
    
    # 4. Start all concurrent tasks
    # gather allows the engine, producer, and UI to run in parallel
    await asyncio.gather(
        engine.broadcast(),
        producer.run(),
        tui.run_async()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        sys.exit(0)
