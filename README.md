# gpu-share — Network GPU Encoding Proxy

Share NVIDIA NVENC hardware video encoding from any GPU host to any VM, container, or machine on the network — no PCI passthrough, no vGPU license, no GPU drivers needed on the consumer side.

## What This Does

Runs a lightweight HTTP service on a machine with an NVIDIA GPU. Other machines (VMs, containers, bare-metal) call the API to transcode video streams using the host's NVENC hardware encoder. The GPU stays available on the host for other workloads (AI inference, rendering, etc.).

```
┌──────────────┐     HTTP API      ┌──────────────────────────┐
│ Consumer VM  │ ──────────────►   │  GPU Host                │
│ (no GPU)     │   POST /start     │  ┌────────────────────┐  │
│              │   GET /hls/...    │  │ gpu-share service   │  │
│              │ ◄──────────────   │  │ (NVENC transcode)   │  │
│ HLS segments │   MPEG-TS HLS    │  └────────┬───────────┘  │
└──────────────┘                   │           │              │
                                   │  ┌────────▼───────────┐  │
                                   │  │  RTX 5060 Ti GPU   │  │
                                   │  │  NVENC encoder     │  │
                                   │  │  (separate from    │  │
                                   │  │   CUDA cores)      │  │
                                   │  └────────────────────┘  │
                                   └──────────────────────────┘
```

## Quick Start

```bash
# On the GPU host
cd gpu-share
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure
cp configs/config.example.yaml configs/config.yaml
# Edit config.yaml with your resolution presets, auth, etc.

# Run
python -m gpu_share.server
# or install as systemd service
sudo cp configs/gpu-share.service /etc/systemd/system/
sudo systemctl enable --now gpu-share
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health + active sessions + available resolutions |
| POST | `/start/<session_id>` | Start transcoding (JSON: `{"source": "rtsp://...", "resolution": "1920x1080"}`) |
| POST | `/stop/<session_id>` | Stop transcoding session |
| GET | `/hls/<session_id>/playlist.m3u8` | HLS playlist |
| GET | `/hls/<session_id>/<segment>.ts` | HLS segment |

## Resolution Presets

| Resolution | H.264 Level | Max Bitrate | Use Case |
|-----------|-------------|-------------|----------|
| 1920x1080 | 4.0 | 6000k | Full HD displays (Echo Show 15) |
| 1280x720 | 3.1 | 3000k | Smaller displays (Echo Show 5/8) |

Custom presets can be added via `configs/config.yaml`.

## Why Not PCI Passthrough?

PCI passthrough is **exclusive** — the host loses GPU access entirely. This service keeps the GPU on the host where it serves multiple consumers simultaneously:
- **AI inference** (Ollama, Whisper) uses CUDA cores
- **Video encoding** uses NVENC hardware encoder (separate ASIC)
- Both run simultaneously without contention
- GeForce cards support up to 5 concurrent NVENC sessions

## Requirements

- NVIDIA GPU with NVENC support (GeForce GTX 1050+, RTX series)
- NVIDIA driver 525+ installed on host
- Python 3.10+
- ffmpeg with NVENC support (`h264_nvenc`)
- No GPU drivers needed on consumer machines

## Origin

Extracted from the [hls-transcoder](https://github.com/cdccentral-ops/general/tree/main/applications/homeassistant/config/hls-transcoder) service built for Echo Show camera streaming via Home Assistant on servergen1.cdclocal.

## License

Apache-2.0 — see [LICENSE](LICENSE).
