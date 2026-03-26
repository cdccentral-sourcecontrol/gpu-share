# gpu-share — TODO

## Roadmap

### Phase 1: Core Service (Complete)
- [x] NVENC H.264 transcoding via REST API
- [x] Multi-resolution presets (1920x1080 + 1280x720)
- [x] Session management with idle timeout
- [x] Systemd service + Dockerfile deployment
- [x] API key authentication (optional)
- [x] HLS tuning: hls_list_size=12, hls_init_time=2 for smoother playback
- [x] UFW rule for internal LAN streaming (192.168.80.0/20)
- [x] CQ 18 for sharper motion (up from CQ 22) — ~970 kbps actual, well under 6000k cap

### Phase 2: Multi-Backend Encoding
- [ ] **Backend abstraction** — Config-driven encoder selection: `backend: auto|nvenc|vaapi|qsv|cpu`
- [ ] **NVENC backend** (current) — NVIDIA GPU, `h264_nvenc`, p5 preset, CQ 22
- [ ] **VAAPI backend** — Intel/AMD iGPU, `h264_vaapi`, QP 22. Needs `/dev/dri/renderD128`
- [ ] **QSV backend** — Intel QuickSync, `h264_qsv`, global_quality 22
- [ ] **Software fallback** — `libx264`, veryfast preset, CRF 22. Works on any CPU, no GPU needed.
- [ ] **Auto-detection** — Probe available encoders (`ffmpeg -encoders`), select best: nvenc > vaapi > qsv > cpu
- [ ] **Shared settings** — Profile (baseline), level, GOP, keyframes, HLS params are backend-agnostic

### Phase 3: HACS Integration (HA Client)
- [ ] **Custom HACS integration** — Installable via HACS as `gpu_share` integration
- [ ] **Configuration flow** — UI-based setup: gpu-share host URL, API key, camera mapping
- [ ] **Camera proxy entity** — Creates camera entities that stream through gpu-share service. Serves ALL display targets (Echo Show, Google Hub, dashboard, phones) from same NVENC session.
- [ ] **Unified display target** — Same transcoded 1920x1080 Baseline H.264 MPEG-TS output works everywhere. No more ultrawide 1536x432 sub-stream for Google Hubs.
- [ ] **Direct streaming mode** — Option to return redirect URL to gpu-share host (bypass HAOS proxy)
- [ ] **Auto-start on camera view** — Trigger transcoding when Alexa/dashboard/Cast requests a stream
- [ ] **Google/Nest camera support** — Configure Google/Nest cameras as transcoder sources. Google API limits concurrent stream connections (~2-5 per camera) so transcoder acts as a single consumer that serves all viewers from one session.
- [ ] **Health monitoring** — Sensor entity showing gpu-share service status, active sessions, GPU utilization
- [ ] **HACS repository manifest** — `hacs.json` with proper metadata for HACS default store submission

### Phase 4: Setup & Deployment Tools
- [ ] **`gpu-share setup` CLI** — Interactive: detect GPU, install systemd service, test health endpoint
- [ ] **`gpu-share setup --enable-direct`** — Detects host subnet, adds UFW rule. Only on explicit flag.
- [ ] **Docker GPU auto-detection** — Dockerfile/compose auto-detects NVIDIA runtime availability
- [ ] **Health check endpoint** — Report backend type, GPU model, active sessions, encoder capabilities

### Phase 5: Advanced Features
- [ ] **Pre-buffer mode** — Proactively cache segments ahead of client requests. Reduces per-segment proxy latency.
- [ ] **Multi-stream tiling** — Combine multiple camera feeds into a single tiled output (2x2 grid)
- [ ] **Recording** — Save HLS segments to persistent storage alongside live streaming
- [ ] **Prometheus metrics** — Session count, GPU utilization, segment sizes, latency, encoder backend
- [ ] **WebRTC output** — Alternative to HLS for lower-latency clients (browser, modern smart displays)

## Why Not a HA Core PR?

HA core's `stream` component does **no transcoding** — it only re-segments source streams into fMP4/HLS using PyAV. This means:

1. HEVC source cameras → HA passes HEVC through → Echo Show can't play it (no H.264 transcode)
2. fMP4 output only → old GStreamer clients need MPEG-TS (no container format option)
3. Source profile preserved → Echo Show needs Baseline but source is High (no profile re-encode)
4. Gzip always enabled → old GStreamer can't decompress (no disable option)

Fixing items 2-4 in HA core would help some edge cases but **does NOT solve the fundamental problem**: cameras outputting HEVC/high-profile H.264 need a real transcode. HA core has no plans to add GPU encoding.

**The right approach**: A standalone HACS integration (`gpu_share`) that:
- Pairs with the gpu-share service running on any GPU host
- Works with any backend (NVENC, VAAPI, QSV, or pure CPU)
- Doesn't require HA core changes
- Users install via HACS, configure host URL, and it just works

## Lessons Learned

- `hls_list_size=12` with `hls_init_time=2` gives best playback smoothness — first segments are 2s for fast buffer fill, then 1s for low latency
- CQ 18 is optimal for motion clarity on security cameras — ~970 kbps actual, well under 6000k maxrate cap
- Echo Show GStreamer (libsoup/2.48.1) requires: Baseline profile, MPEG-TS segments, no gzip
- NVENC encoder ASIC is independent of CUDA cores — video encoding doesn't impact AI inference
- GeForce cards: 5 concurrent NVENC session hard limit
- Intel HD 530 (i7-6700K iGPU) supports VAAPI/QSV H.264 encode — viable for 2 camera streams without discrete GPU
- Software libx264 fallback: ~15-30% CPU per 1080p stream at veryfast, viable for 1-2 streams on modern CPUs
- UFW doesn't support DNS hostnames — use CIDR ranges or static IPs
- **Unified display target**: Same transcoded output (1920x1080 Baseline MPEG-TS) works for Echo Show, Google Hub, dashboard, and phones. No need for separate per-target encoding.
- **Google Hub casting improves**: Without transcoder, Google Hubs get raw 1536x432 ultrawide sub-stream (letterboxed). With transcoder, they get 1920x1080 padded 16:9 — fills the screen properly.
- **Google/Nest camera API limits**: Google limits concurrent stream connections per camera (~2-5). Transcoder acts as single consumer, re-serving to unlimited viewers via HLS. Eliminates connection exhaustion.
- **Google voice intercepts camera commands**: "Hey Google, show me X camera" is handled natively by Google, never reaches HA. Only `camera.play_stream` service call (Cast) works from HA side.
- **Frame generation (DLSS FG, minterpolate) doesn't apply**: Source is 25fps security camera, not rendered frames. Motion jerks are transport-layer (HLS segment delivery), not framerate.
- PCI passthrough is exclusive — host loses GPU. gpu-share is the network alternative.
- HA core stream component does NO transcoding — only re-segments via PyAV. Cannot fix Echo Show compatibility upstream.
