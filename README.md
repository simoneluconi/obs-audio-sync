# OBS Audio Sync

A Windows desktop tool that automatically synchronizes multiple audio tracks in [OBS Studio](https://obsproject.com/) — designed for live productions (e.g. a sports venue broadcast) with several independent audio sources arriving with different delays: a PA feed over a wireless transmitter, ambient/wireless microphones, a camera's audio over a wireless HDMI link, and so on.

It listens to each track's audio, estimates the relative delay between them, and writes the correct [Sync Offset](https://obsproject.com/wiki/Sync-Offset) to each corresponding OBS input — automatically, in seconds, instead of nudging offsets by ear.

## Features

- **Automatic delay detection** across an arbitrary number of tracks, using onset-based audio alignment (correlating the timing of audio *attacks/transients* rather than raw waveform phase) — robust to sustained tones, music, and reverberant/noisy venues, where naive cross-correlation tends to lock onto the wrong peak.
- **Manual preview-then-confirm workflow**: "Analyze now" computes and shows the result — delay, confidence, and a waveform/correlation visualization — without touching OBS; a separate "Apply changes" step writes the offsets only once you confirm.
- **Auto mode**: periodically re-checks and re-applies only the tracks that have actually drifted beyond a configurable threshold, so a live show stays in sync without manual intervention and without needless OBS writes from measurement noise alone.
- **Confidence-gated**: a track whose estimate isn't reliable in a given cycle is skipped rather than applying a guess — the previous, working offset is left untouched.
- **Modern PySide6 GUI** with live waveform/correlation plots, per-track status badges, and a settings panel for tuning capture duration, thresholds, and sample rate.
- **Headless CLI** (`scripts/cli_analyze.py`) for scripting, testing without a GUI, or validating against synthetic signals with a known delay.

## How it works

1. **Capture**: for each configured track, audio is captured directly from its underlying hardware input device (e.g. a USB receiver, an audio interface channel) in parallel — independently of OBS's own audio pipeline.
2. **Analysis**: each track's onset-strength envelope is correlated against a chosen reference track to estimate their relative delay, with a confidence score reflecting how reliable that estimate is.
3. **Resolution**: the slowest (most delayed) track becomes the alignment target; every other track's OBS Sync Offset is set so it "waits" to match it — the only physically valid direction, since OBS can delay audio but not meaningfully rewind it.
4. **Apply**: the computed offsets are written to OBS via [obs-websocket](https://github.com/obsproject/obs-websocket) (v5, OBS 28+).

## Requirements

- Windows 10/11
- OBS Studio 28+ with the WebSocket server enabled (**Tools → WebSocket Server Settings**)
- Python 3.10+

## Installation

```powershell
git clone https://github.com/simoneluconi/obs-audio-sync.git
cd obs-audio-sync
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## Usage

### GUI

```powershell
python -m obs_audio_sync
```

1. Enter your OBS WebSocket host/port/password and connect.
2. Add a track for each audio source: give it a name, pick its OBS input and its physical capture device, and mark exactly one track as the reference.
3. Click **Analyze now** to preview the computed delays, then **Apply changes** to write them to OBS.
4. Optionally enable **Auto mode** to keep re-checking and correcting drift automatically during a live show.

### CLI

```powershell
# List available capture devices
python scripts/cli_analyze.py --list-devices

# Analyze live audio from mapped devices (dry run, no OBS needed)
python scripts/cli_analyze.py --live pa="Line In (USB Audio)" ambient="RODE Wireless" --reference pa

# Compute offsets and write them to OBS
python scripts/cli_analyze.py --live pa="Line In (USB Audio)" ambient="RODE Wireless" --reference pa ^
    --apply --obs-host localhost --obs-port 4455 --obs-password <password>

# Validate the algorithm against synthetic signals with a known delay
python scripts/gen_test_signals.py --out-dir test_wavs --delays 0 0.037 -0.12
python scripts/cli_analyze.py --wav-dir test_wavs --reference track_0_delay_+0.000s
```

## Configuration

The GUI persists its settings (OBS connection, track mappings, thresholds) to `~/.obs-audio-sync/config.json`. This file is **not** committed to the repository and contains your OBS WebSocket password in plain text — keep it local, and use a dedicated, non-sensitive password for the WebSocket server if possible.

## Known limitations

- **Windows/WASAPI only.** Audio capture relies on WASAPI-specific behavior and hasn't been tested on macOS/Linux.
- **Capture happens in a child process.** On this platform, opening a WASAPI input stream only works reliably from a process's actual main thread — not from a background thread, Qt or otherwise. Capture is therefore run in a short-lived child process (`audio/capture_process.py`) rather than a thread, so the GUI stays responsive.
- **A source's audio must be reachable as a standalone system audio device.** Devices that only expose audio embedded in a video stream (e.g. some capture cards' DirectShow/video-capture audio, with no separate WASAPI audio endpoint) can't be analyzed directly — there's no way to tap into OBS's internal handling of that source from outside OBS. If your capture card *also* exposes a standalone audio device (many do, including the Elgato Cam Link used during development), map that device instead, and mute the video source's own embedded audio in OBS to avoid double-capturing it.
- **OBS's Audio Monitoring does not reflect the Sync Offset** — monitoring sits earlier in OBS's internal audio pipeline than where the offset is applied. Listening via headphone monitoring will never sound corrected, even when the offset is applied correctly; verify with an actual recording/stream output instead.
- **Continuous, tightly looped/rhythmic music is a hard case** for any correlation-based delay estimator, this one included: a strong, repeating beat can produce a secondary correlation peak that's occasionally as strong as the true one. A short, sharp transient (a clap, a whistle, an announcer's voice) gives a much more reliable read than a music bed alone.

## Development

```powershell
pip install -e ".[dev]"
pytest
```

The core DSP, audio capture, and sync-resolution logic (`core/`, `audio/`, `dsp/`, `obs/`, `sync_engine/`, `config/`) has no Qt dependency and is fully testable with plain `pytest`; only `gui/` imports PySide6.

## License

MIT — see [LICENSE](LICENSE).
