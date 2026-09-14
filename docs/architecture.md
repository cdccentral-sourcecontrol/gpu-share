# GPU Share — Architecture

## Problem

VMs and containers without GPU access cannot use hardware video encoding.
PCI passthrough is exclusive (host loses the GPU). NVIDIA vGPU requires
enterprise datacenter GPUs. Consumer GeForce cards have no sharing mechanism.

## Solution

Run a lightweight HTTP service on the GPU host that exposes NVENC encoding
sessions via REST API. Consumers (VMs, containers, other machines) call the
API to transcode video streams — no GPU drivers or CUDA needed on the consumer.

## How NVENC Sharing Works

NVIDIA GPUs have a dedicated NVENC encoder ASIC separate from CUDA cores:

```
┌─────────────────────────────────────────┐
│              NVIDIA GPU                 │
│                                         │
│  ┌───────────────┐  ┌───────────────┐   │
│  │  CUDA Cores   │  │  NVENC ASIC   │   │
│  │  (AI, render) │  │  (H.264/H.265)│   │
│  │               │  │  encode only)  │   │
│  └───────────────┘  └───────────────┘   │
│                                         │
│  ┌───────────────┐  ┌───────────────┐   │
│  │  VRAM         │  │  NVDEC ASIC   │   │
│  │  (shared)     │  │  (decode)     │   │
│  └───────────────┘  └───────────────┘   │
└─────────────────────────────────────────┘
```

- AI inference uses CUDA cores + VRAM
- Video encoding uses NVENC + minimal VRAM
- Both run simultaneously without contention
- GeForce: 5 concurrent NVENC sessions max
- Enterprise (A100+): unlimited sessions

## Data Flow

```
Source (RTSP/RTMP camera, file, etc.)
    │
    ▼
gpu-share ffmpeg (software decode → scale/pad → NVENC H.264 encode)
    │
    ▼
HLS MPEG-TS segments (on disk, sliding window)
    │
    ▼
gpu-share HTTP API (:8553)
    │
    ▼
Consumer (VM, container, HA, browser, etc.)
```

## Session Lifecycle

1. Consumer calls `POST /start/<id>` with RTSP source URL
2. Server spawns ffmpeg with NVENC encoder
3. ffmpeg writes HLS segments to disk
4. Consumer polls `GET /hls/<id>/playlist.m3u8` and fetches segments
5. Server tracks last-access time per session
6. After `idle_timeout` seconds with no requests, ffmpeg is killed
7. Consumer calls `POST /stop/<id>` for explicit cleanup

## Security

- Optional API key auth via `X-API-Key` header
- UFW/firewall restricts port to specific consumer IPs
- Session IDs validated (alphanumeric + underscore/hyphen only)
- Segment filenames validated (seg<N>.ts pattern only)
