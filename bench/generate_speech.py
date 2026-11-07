"""Génération offline Piper ; télécharger la voix séparément, jamais à l'exécution STT."""

import argparse
import io
import json
import subprocess
import wave
from pathlib import Path

from piper import PiperVoice

from bench.common import ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", type=Path, required=True)
    args = parser.parse_args()
    voice = PiperVoice.load(args.voice)
    data = ROOT / "bench/data"
    for row in json.loads((data / "gladia_references.json").read_text()):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            voice.synthesize_wav(row["text"], wav)
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                "pipe:0",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(data / f"gladia-{row['id']}.wav"),
            ],
            input=buffer.getvalue(),
            check=True,
        )


if __name__ == "__main__":
    main()
