# Home Assistant Custom Component — gpu-share proxy

This is a template for a Home Assistant custom component that proxies
HLS camera streams through a gpu-share server for NVENC hardware transcoding.

Based on the `hls_no_gzip` v9 component from the homeassistant-config repo.

## Setup

1. Copy this directory to `/config/custom_components/gpu_share_proxy/`
2. Add to `configuration.yaml`:
   ```yaml
   gpu_share_proxy:
   ```
3. Configure `TRANSCODER_HOST` and `_CAMERA_MAP` in `__init__.py`
4. Restart Home Assistant

## How It Works

1. Echo Show requests camera stream via Alexa → HA
2. HA generates HLS master_playlist
3. This component intercepts the master_playlist request
4. Calls gpu-share server `/start/<camera_id>` with RTSP source
5. Returns modified playlist pointing to proxy endpoints
6. Proxies HLS segments from gpu-share server to Echo Show
