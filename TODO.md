# gpu-share — TODO

## Roadmap

### Phase 1: Core Service (Complete)
- [x] NVENC H.264 transcoding via REST API
- [x] Multi-resolution presets (1920x1080 + 1280x720)
- [x] Session management with idle timeout
- [x] Systemd service + Dockerfile deployment
- [x] API key authentication (optional)
- [x] HLS tuning: hls_list_size=4, hls_init_time=2 for smoother playback
- [x] UFW rule for internal LAN streaming (configure your LAN CIDR)
- [x] CQ 18 for sharper motion (up from CQ 22) — ~970 kbps actual, well under 6000k cap

### Phase 2: Multi-Backend Encoding

#### Phase 2.0: Install a second discrete GPU (Hardware Prerequisite)

Install a discrete Intel Arc (or similar) GPU to enable VAAPI/QSV encoding backends alongside NVENC.

**Typical dual-GPU PCIe layout** (example workstation board with dual x16 slots):
- Slot 1: primary NVIDIA GPU (NVENC)
- Slot 2: secondary Intel Arc GPU (VAAPI/QSV) — often empty initially

**Recommended card class**: Intel Arc A380-class (or newer Battlemage equivalent)
- PCIe x8, ~75W TDP, often no external power connector
- Dedicated media engine: AV1/H.264/H.265 hardware encode + decode
- VAAPI + QSV support on Linux via `intel-media-va-driver` + `libva`
- Low power/heat — suitable for encode-only workloads alongside a primary GPU

**Where to buy** (prices fluctuate — verify before purchasing):

| Card class | Approx. price | Form Factor | Power | Notes |
|------------|---------------|-------------|-------|-------|
| Arc A380 ITX / single-slot | ~$100–150 | Single-slot ITX | ~75W (often bus-powered) | Best fit for encode-only |
| Arc A380 dual-slot | ~$100–140 | Dual-slot | ~75W | Budget option |
| Arc B570 / B580 class | ~$200–250 | Dual-slot | ~150W (8-pin) | Newer media engine; overkill for encode-only |

**Recommendation**: Prefer a single-slot, low-TDP Arc A380-class card with no power cable when space/PSU headroom is limited.

**Install steps** (on your GPU host):
- [ ] Verify PSU headroom for primary GPU + Arc card
- [ ] Power down, insert Arc card into the second PCIe slot
- [ ] Boot and verify both GPUs: `lspci | grep -iE 'vga|3d|display'`
- [ ] Install Intel GPU drivers: `sudo apt install intel-media-va-driver-non-free intel-gpu-tools`
- [ ] Verify VAAPI: `vainfo` — should show H.264/H.265/AV1 encode profiles
- [ ] Verify QSV: `ffmpeg -hide_banner -encoders | grep qsv`
- [ ] Verify `/dev/dri/renderD128` (Intel) and `/dev/dri/renderD129` (NVIDIA) both present (device numbers may vary)
- [ ] Test encode: `ffmpeg -vaapi_device /dev/dri/renderD128 -i test.mp4 -c:v h264_vaapi -qp 18 out.mp4`
- [ ] Confirm NVIDIA NVENC still works after adding Intel card

#### Phase 2.1: Software Backend Support

- [ ] **Backend abstraction** — Config-driven encoder selection: `backend: auto|nvenc|vaapi|qsv|cpu`
- [ ] **NVENC backend** (current) — NVIDIA GPU, `h264_nvenc`, p5 preset, CQ 18
- [ ] **VAAPI backend** — Intel Arc GPU, `h264_vaapi`, QP 18. Needs a `/dev/dri/renderD*` node
- [ ] **QSV backend** — Intel QuickSync, `h264_qsv`, global_quality 18
- [ ] **Software fallback** — `libx264`, veryfast preset, CRF 18. Works on any CPU, no GPU needed.
- [ ] **Auto-detection** — Probe available encoders (`ffmpeg -encoders`), select best: nvenc > vaapi > qsv > cpu
- [ ] **Shared settings** — Profile (baseline), level, GOP, keyframes, HLS params are backend-agnostic

#### Phase 2.2: Hardware Decode (NVDEC)

NVIDIA NVDEC can offload video decode from CPU to GPU. Available decoders:
- `h264_cuvid`, `hevc_cuvid`, `av1_cuvid`, `vp9_cuvid`, `mjpeg_cuvid`, etc.

Zero-copy pipeline: `-hwaccel cuda -hwaccel_output_format cuda -c:v h264_cuvid ... -c:v h264_nvenc`

**Current assessment**: CPU software decode is often only a few percent even for high-res HEVC. NVDEC adds pipeline complexity with marginal benefit. **Defer until CPU decode becomes a bottleneck.**

- [ ] Test zero-copy pipeline
- [ ] Benchmark CPU vs NVDEC decode at various stream counts (1, 5, 10)
- [ ] Add `hwdecode: auto|cuda|none` config option
- [ ] Handle fallback when cuvid decoder not available

#### Phase 2.3: H.265/HEVC NVENC Encoding

HEVC (`hevc_nvenc`) provides ~40% bitrate savings over H.264 at equivalent quality.

**Illustrative performance** (modern RTX-class GPU, 1920×1080, CQ 22):
- H.264 `h264_nvenc`: ~750 kbps
- H.265 `hevc_nvenc`: ~450 kbps (40% savings)

**Device compatibility**:
| Device | H.265 HEVC | Notes |
|--------|-----------|-------|
| Google Nest Hub / Hub Max | ✅ | Native Cast decode |
| Android phones/tablets | ✅ | Android 5.0+ |
| iOS/Safari | ✅ | iOS 11+ |
| Echo Show (all models) | ❌ | H.264 only |
| Modern browsers | ✅ | MSE + fMP4 or MPEG-TS |

**Strategy**: Use `hevc_nvenc` for Cast/Hub/TV targets, fall back to `h264_nvenc` for Echo Show.

- [ ] Add `codec: auto|h264|hevc` config option
- [ ] Test `hevc_nvenc` with `-tag:v hvc1` for Apple compatibility
- [ ] Per-device codec selection
- [ ] A/B bandwidth comparison in production

#### Phase 2.4: AV1 NVENC Encoding

AV1 (`av1_nvenc`) provides ~50% bitrate savings over H.264. Many recent RTX GPUs have a dedicated AV1 encode block.

**Container requirement**: AV1 in HLS requires **fMP4** (not MPEG-TS): `-hls_segment_type fmp4`

- [ ] Test `av1_nvenc` with fMP4 HLS output
- [ ] Add `codec: av1` config option
- [ ] Handle init segment serving
- [ ] Consider AV1 only for modern-device-only presets

#### Phase 2.5: GPU Feature Discovery & Exposure

- [ ] Probe encoders/decoders at startup
- [ ] Add `/capabilities` endpoint returning structured JSON
- [ ] Extend `/health` with GPU stats (temp, power, utilization, VRAM)
- [ ] Auto-select best codec based on discovered capabilities

### Phase 3: HACS Integration (HA Client)
- [ ] **Custom HACS integration** — Installable via HACS as `gpu_share` integration
- [ ] **Configuration flow** — UI-based setup: gpu-share host URL, API key, camera mapping
- [ ] **Camera proxy entity** — Creates camera entities that stream through gpu-share service. Serves ALL display targets (Echo Show, Google Hub, dashboard, phones) from same NVENC session.
- [ ] **Unified display target** — Same transcoded 1920x1080 Baseline H.264 MPEG-TS output works everywhere. No more ultrawide sub-stream for Google Hubs.
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
- [x] **Multi-stream tiling** — Combine multiple feeds into a tiled output (2x2, 2x1, 1x2, 3x3, 1x3, 3x1 grids) — done in production `hls_server.py`, pending absorption into gpu-share
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

- `hls_list_size=4` with `hls_init_time=2` — init fills buffer fast (2s first segment), then 1s segments keep latency low with minimal playlist window
- CQ 18 is optimal for motion clarity on security cameras — ~970 kbps actual, well under 6000k maxrate cap
- Echo Show GStreamer (libsoup/2.48.1) requires: Baseline profile, MPEG-TS segments, no gzip
- NVENC encoder ASIC is independent of CUDA cores — video encoding doesn't impact AI inference
- GeForce cards: 5 concurrent NVENC session hard limit
- VAAPI/QSV backends are viable on systems with Intel Arc or AMD GPUs (older iGPUs on some boards may not be viable)
- Software libx264 fallback: ~15-30% CPU per 1080p stream at veryfast, viable for 1-2 streams on modern CPUs
- UFW doesn't support DNS hostnames — use CIDR ranges or static IPs
- **Unified display target**: Same transcoded output (1920x1080 Baseline MPEG-TS) works for Echo Show, Google Hub, dashboard, and phones. No need for separate per-target encoding.
- **Google Hub casting improves**: Without transcoder, Google Hubs often get a raw ultrawide sub-stream (letterboxed). With transcoder, they get 1920x1080 padded 16:9 — fills the screen properly.
- **Google/Nest camera API limits**: Google limits concurrent stream connections per camera (~2-5). Transcoder acts as single consumer, re-serving to unlimited viewers via HLS. Eliminates connection exhaustion.
- **Google voice intercepts camera commands**: "Hey Google, show me X camera" is handled natively by Google, never reaches HA. Only `camera.play_stream` service call (Cast) works from HA side.
- **Frame generation (DLSS FG, minterpolate) doesn't apply**: Source is typically 25fps security camera, not rendered frames. Motion jerks are transport-layer (HLS segment delivery), not framerate.
- PCI passthrough is exclusive — host loses GPU. gpu-share is the network alternative.
- HA core stream component does NO transcoding — only re-segments via PyAV. Cannot fix Echo Show compatibility upstream.
