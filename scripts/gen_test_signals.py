"""Generate synthetic WAV files with a known delay between them, for manual
testing of the GCC-PHAT engine without needing real audio hardware.

Usage:
    python scripts/gen_test_signals.py --out-dir /tmp/sync_test --delays 0 0.037 -0.12
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.io import wavfile

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from obs_audio_sync.testing.synthetic import generate_base_signal, generate_delayed_signal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--fs", type=int, default=48000)
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument(
        "--delays",
        type=float,
        nargs="+",
        default=[0.0, 0.037, -0.12],
        help="Delay in seconds of each track relative to the base signal (the first is usually 0)",
    )
    parser.add_argument("--leakage-ratio", type=float, default=0.6)
    parser.add_argument("--noise-std", type=float, default=0.05)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    base = generate_base_signal(args.duration, args.fs, seed=0)

    for i, delay in enumerate(args.delays):
        track = generate_delayed_signal(
            base,
            args.fs,
            delay_sec=delay,
            noise_std=args.noise_std,
            leakage_ratio=args.leakage_ratio,
            seed=100 + i,
        )
        out_path = args.out_dir / f"track_{i}_delay_{delay:+.3f}s.wav"
        wavfile.write(out_path, args.fs, track.astype(np.float32))
        print(f"Wrote {out_path} (true delay = {delay:+.3f}s)")


if __name__ == "__main__":
    main()
