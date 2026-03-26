# gpu-share — TODO

## Roadmap

### Phase 1: Core Stability (Current)
- [x] NVENC H.264 transcoding via REST API
- [x] Multi-resolution presets (1920x1080 + 1280x720)
- [x] Session management with idle timeout
- [x] Systemd service + Dockerfile deployment
- [x] API key authentication (optional)
- [x] HLS tuning: hls_list_size=12, hls_init_time=2 for smoother playback

### Phase 2: HA Integration
- [ ] **HA custom component (client)** — Full `__init__.py` that bridges HA camera entities to gpu-share service. Currently a placeholder README + manifest.
- [ ] **Direct streaming bypass** — Component returns redirect URL to gpu-share host instead of proxying segments through HAOS. Eliminates VM proxy latency.
- [ ] **Auto-start on camera view** — Trigger transcoding when Alexa/dashboard requests a camera stream, stop on idle.

### Phase 3: Setup & Deployment
- [ ] **UFW setup script** with `--enable-direct` flag — Detects host subnet, adds firewall rule. Only runs when explicitly requested. Not auto-applied.
- [ ] **`gpu-share setup` CLI** — Interactive setup: detect GPU, install systemd service, configure firewall, test health endpoint.
- [ ] **Docker GPU auto-detection** — Dockerfile/compose auto-detects NVIDIA runtime availability.

### Phase 4: Multi-GPU Backend Support
- [ ] **VAAPI presets** — Intel/AMD GPU encoding defaults (h264_vaapi, hevc_vaapi). Config-driven preset selection.
- [ ] **QSV presets** — Intel QuickSync encoding defaults. Useful for Intel iGPU passthrough to VMs.
- [ ] **Backend auto-detection** — Detect available GPU encoders (nvenc/vaapi/qsv) and select best available.
- [ ] **Software fallback** — libx264 preset for hosts with no GPU (CI, testing, low-end machines).

### Phase 5: Advanced Features
- [ ] **Pre-buffer mode** — Proactively fetch and cache segments ahead of client requests. Reduces per-segment latency at the proxy layer.
- [ ] **Multi-stream tiling** — Combine multiple camera feeds into a single tiled output (e.g., 2x2 grid).
- [ ] **Recording** — Option to save HLS segments to persistent storage alongside live streaming.
- [ ] **Prometheus metrics** — Expose session count, GPU utilization, segment sizes, latency.

## HA Core PR (Separate)

These are contributions to the `home-assistant/core` repository, not this repo:

- [ ] **Gzip fix for HLS** — HA's stream component calls `response.enable_compression(web.ContentCoding.gzip)` on all HLS responses. Old GStreamer clients (Echo Show, some smart TVs) can't decompress. Fix: add `stream.disable_compression` config flag or detect client capabilities.
  - File: `homeassistant/components/stream/hls.py` line ~330
  - Currently no open issue or PR for this
- [ ] **MPEG-TS segment type option** — HA hardcodes `SEGMENT_CONTAINER_FORMAT = "mp4"` (fMP4/CMAF). Old clients need MPEG-TS. Add config option.
  - File: `homeassistant/components/stream/const.py`
- [ ] **H.264 profile selection** — HA preserves source profile (often High). Echo Show needs Baseline. Add stream configuration option.

## Lessons Learned

- `hls_list_size=12` with `hls_init_time=2` gives best playback smoothness — first segments are 2s for fast buffer fill, then 1s for low latency
- Echo Show GStreamer (libsoup/2.48.1) requires: Baseline profile, MPEG-TS segments, no gzip
- NVENC encoder ASIC is independent of CUDA cores — video encoding doesn't impact AI inference
- GeForce cards: 5 concurrent NVENC session hard limit
- UFW doesn't support DNS hostnames — use CIDR ranges or static IPs
- PCI passthrough is exclusive — host loses GPU. This service is the alternative.
