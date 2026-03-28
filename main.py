import asyncio
import sys
from core.engine import PulseForgeEngine
from inputs.wav_producer import AudioProducer
from outputs.tui_display import PulseForgeTUI
from outputs.audio_consumer import AudioConsumer


async def main_loop(file_path: str):
    # 1. Boot the Engine
    engine = PulseForgeEngine()

    # 2. Setup Input (real FFT producer)
    producer = AudioProducer(engine, file_path)

    # 3. Setup Audio Playback
    audio = AudioConsumer(file_path)

    # 4. Setup TUI
    tui = PulseForgeTUI(engine)

    # 5. Register audio consumer as subscriber
    engine.add_subscriber(audio.on_frame)

    # 6. Start playback and run all tasks concurrently
    audio.start_playback()
    try:
        await asyncio.gather(
            engine.broadcast(),
            producer.run(),
            tui.run_async(),
        )
    finally:
        audio.stop()


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <audio_file.wav>")
        print("  Plays the audio file and visualizes its frequency spectrum.")
        sys.exit(1)

    file_path = sys.argv[1]
    try:
        asyncio.run(main_loop(file_path))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
