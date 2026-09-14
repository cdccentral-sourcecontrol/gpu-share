"""GPU Share — NVENC HLS Transcoding HTTP Service.

Provides on-demand RTSP/RTMP to MPEG-TS HLS transcoding using NVIDIA NVENC.
Originally derived from an internal HLS transcoder deployment.

Configuration loaded from configs/config.yaml or environment variables.
"""
import asyncio
import glob
import json
import logging
import os
import re
import time
from pathlib import Path

import yaml
from aiohttp import web

from gpu_share.presets import load_presets, DEFAULT_PRESETS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("gpu-share")


def load_config():
    """Load config from YAML file or use defaults."""
    config_paths = [
        Path("configs/config.yaml"),
        Path("/etc/gpu-share/config.yaml"),
        Path.home() / ".config/gpu-share/config.yaml",
    ]
    for p in config_paths:
        if p.exists():
            with open(p) as f:
                log.info("Loaded config from %s", p)
                return yaml.safe_load(f)
    log.info("No config file found, using defaults")
    return {}


class GpuShareServer:
    """Main server managing NVENC transcoding sessions."""

    NVENC_MAX_SESSIONS = 5  # GeForce limit; Quadro/Tesla = unlimited

    def __init__(self, config=None):
        self.config = config or {}
        self.hls_dir = self.config.get("hls_dir", "/tmp/gpu_share_hls")
        self.idle_timeout = self.config.get("idle_timeout", 120)
        self.host = self.config.get("host", "0.0.0.0")
        self.port = self.config.get("port", 8553)
        self.presets = load_presets(self.config.get("presets", {}))
        self.default_resolution = self.config.get("default_resolution", "1920x1080")
        self.api_key = self.config.get("api_key")  # None = no auth
        # HLS tuning
        self.hls_time = self.config.get("hls_time", 1)
        self.hls_list_size = self.config.get("hls_list_size", 8)
        # session_id -> SessionInfo
        self.sessions = {}
        # Cached at startup by _probe_encoders()
        self._encoders = []
        self._decoders = []

    async def _query_gpu_stats(self):
        """Query NVIDIA GPU utilization via nvidia-smi."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,utilization.encoder,"
                "memory.used,memory.total,memory.free,temperature.gpu,"
                "driver_version",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
            if proc.returncode != 0:
                return None
            parts = [p.strip() for p in stdout.decode().strip().split(", ")]
            if len(parts) >= 8:
                return {
                    "name": parts[0],
                    "gpu_utilization_pct": int(parts[1]),
                    "encoder_utilization_pct": int(parts[2]),
                    "memory_used_mib": int(parts[3]),
                    "memory_total_mib": int(parts[4]),
                    "memory_free_mib": int(parts[5]),
                    "temperature_c": int(parts[6]),
                    "driver_version": parts[7],
                }
        except Exception:
            pass
        return None

    async def _probe_encoders(self):
        """Probe ffmpeg for available hardware encoders and decoders."""
        for kind, dest, tags in [
            ("-encoders", "_encoders", ("nvenc", "vaapi", "qsv")),
            ("-decoders", "_decoders", ("cuvid", "vaapi", "qsv")),
        ]:
            results = []
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-hide_banner", kind,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                for line in stdout.decode().splitlines():
                    for tag in tags:
                        if tag in line:
                            parts = line.strip().split()
                            if len(parts) >= 2:
                                results.append({"name": parts[1], "description": " ".join(parts[2:])})
                            break
            except Exception:
                pass
            setattr(self, dest, results)

    def _check_auth(self, request):
        """Validate API key if configured."""
        if not self.api_key:
            return True
        auth = request.headers.get("X-API-Key", "")
        return auth == self.api_key

    async def start_ffmpeg(self, session_id, source_url, resolution=None):
        """Start ffmpeg NVENC transcoding for a source."""
        if resolution not in self.presets:
            resolution = self.default_resolution
        preset = self.presets[resolution]

        out_dir = os.path.join(self.hls_dir, session_id)
        os.makedirs(out_dir, exist_ok=True)

        # Clear stale segments from previous sessions
        for old_file in glob.glob(os.path.join(out_dir, "*.ts")) + glob.glob(
            os.path.join(out_dir, "*.m3u8")
        ):
            os.remove(old_file)

        playlist = os.path.join(out_dir, "playlist.m3u8")
        seg_pattern = os.path.join(out_dir, "seg%d.ts")

        # Build input args based on protocol
        input_args = []
        if source_url.startswith("rtmp://"):
            input_args = ["-rtmp_live", "live"]
        elif source_url.startswith("rtsp://"):
            input_args = ["-rtsp_transport", "tcp"]

        fps = preset.get("fps", 25)

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            *input_args,
            "-i", source_url,
            "-r", str(fps),
            "-vf", preset["vf"],
            "-c:v", "h264_nvenc",
            "-profile:v", preset.get("profile", "baseline"),
            "-level", preset["level"],
            "-preset", preset.get("preset", "p5"),
            "-rc", "vbr",
            "-cq", str(preset.get("cq", 18)),
            "-maxrate", preset["maxrate"],
            "-bufsize", preset["bufsize"],
            "-force_key_frames", f"expr:gte(t,n_forced*{self.hls_time})",
            "-g", str(fps * self.hls_time),
            "-forced-idr", "1",
            "-strict_gop", "1",
            "-no-scenecut", "1",
            "-spatial-aq", "1",
            "-temporal-aq", "1",
            "-rc-lookahead", "8",
            "-an",
            "-f", "hls",
            "-hls_time", str(self.hls_time),
            "-hls_list_size", str(self.hls_list_size),
            "-hls_flags", "delete_segments",
            "-hls_segment_type", "mpegts",
            "-hls_segment_filename", seg_pattern,
            playlist,
        ]

        log.info("Starting NVENC transcode [%s] @ %s: %s", session_id, resolution, source_url[:60])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        log.info("ffmpeg pid=%d for [%s] @ %s", proc.pid, session_id, resolution)
        return proc, out_dir, resolution

    async def ensure_session(self, session_id, source_url=None, resolution=None):
        """Get or create a transcoding session."""
        if session_id in self.sessions:
            info = self.sessions[session_id]
            if info["proc"].returncode is None:
                # If resolution changed, restart with new resolution
                if resolution and resolution != info.get("resolution") and resolution in self.presets:
                    log.info("Resolution change [%s]: %s -> %s", session_id, info.get("resolution"), resolution)
                    info["proc"].kill()
                    await info["proc"].wait()
                else:
                    info["last_access"] = time.monotonic()
                    return info
            else:
                try:
                    stderr = await info["proc"].stderr.read(2000)
                    log.warning("ffmpeg died [%s] rc=%s: %s",
                                session_id, info["proc"].returncode,
                                stderr.decode(errors="replace")[:300])
                except Exception:
                    log.warning("ffmpeg died [%s] rc=%s", session_id, info["proc"].returncode)

        if not source_url:
            return None

        proc, out_dir, res = await self.start_ffmpeg(session_id, source_url, resolution)
        info = {
            "source": source_url,
            "dir": out_dir,
            "proc": proc,
            "last_access": time.monotonic(),
            "resolution": res,
        }
        self.sessions[session_id] = info
        return info

    async def cleanup_idle(self):
        """Kill idle sessions periodically."""
        while True:
            await asyncio.sleep(30)
            now = time.monotonic()
            for sid, info in list(self.sessions.items()):
                if now - info["last_access"] > self.idle_timeout and info["proc"].returncode is None:
                    log.info("Killing idle [%s] pid=%d", sid, info["proc"].pid)
                    info["proc"].kill()
                    del self.sessions[sid]

    # --- HTTP Handlers ---

    async def handle_health(self, request):
        active = {k: {
            "pid": v["proc"].pid,
            "alive": v["proc"].returncode is None,
            "resolution": v.get("resolution", "unknown"),
        } for k, v in self.sessions.items()}
        gpu = await self._query_gpu_stats()
        return web.json_response({
            "status": "ok",
            "active_streams": len(active),
            "sessions": active,
            "gpu": gpu,
            "resolutions": list(self.presets.keys()),
            "nvenc_max_sessions": self.NVENC_MAX_SESSIONS,
            "hls_time": self.hls_time,
            "hls_list_size": self.hls_list_size,
        })

    async def handle_capabilities(self, request):
        """Return GPU capabilities: encoders, decoders, GPU info."""
        gpu = await self._query_gpu_stats()
        return web.json_response({
            "gpu": gpu,
            "encoders": self._encoders,
            "decoders": self._decoders,
            "nvenc_max_sessions": self.NVENC_MAX_SESSIONS,
            "resolutions": list(self.presets.keys()),
        })

    async def handle_start(self, request):
        if not self._check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)

        session_id = request.match_info["session_id"]
        if not re.match(r"^[a-zA-Z0-9_-]+$", session_id):
            return web.json_response({"error": "invalid session_id"}, status=400)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        source_url = body.get("source", "")
        if not (source_url.startswith("rtmp://") or source_url.startswith("rtsp://")):
            return web.json_response({"error": "source must be rtmp:// or rtsp://"}, status=400)

        resolution = body.get("resolution", self.default_resolution)

        info = await self.ensure_session(session_id, source_url, resolution)
        if info:
            return web.json_response({
                "status": "started",
                "session_id": session_id,
                "pid": info["proc"].pid,
                "resolution": info.get("resolution"),
            })
        return web.json_response({"error": "failed to start"}, status=500)

    async def handle_stop(self, request):
        if not self._check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)

        session_id = request.match_info["session_id"]
        if session_id in self.sessions:
            info = self.sessions.pop(session_id)
            if info["proc"].returncode is None:
                info["proc"].kill()
                log.info("Stopped [%s]", session_id)
            return web.json_response({"status": "stopped", "session_id": session_id})
        return web.json_response({"error": "no session"}, status=404)

    async def handle_playlist(self, request):
        session_id = request.match_info["session_id"]
        info = self.sessions.get(session_id)
        if not info or info["proc"].returncode is not None:
            return web.Response(status=404, text="no active session")

        info["last_access"] = time.monotonic()
        playlist_path = os.path.join(info["dir"], "playlist.m3u8")

        for _ in range(12):
            if os.path.exists(playlist_path) and os.path.getsize(playlist_path) > 10:
                break
            await asyncio.sleep(0.5)
        else:
            return web.Response(status=503, text="stream starting")

        with open(playlist_path, "r") as f:
            text = f.read()

        lines = []
        for line in text.split("\n"):
            if line.startswith("seg") and line.endswith(".ts"):
                lines.append(f"/hls/{session_id}/{line}")
            else:
                lines.append(line)

        return web.Response(
            text="\n".join(lines),
            content_type="application/x-mpegURL",
            headers={"Cache-Control": "no-cache"},
        )

    async def handle_segment(self, request):
        session_id = request.match_info["session_id"]
        filename = request.match_info["filename"]

        if not re.match(r"^seg\d+\.ts$", filename):
            return web.Response(status=400, text="invalid filename")

        info = self.sessions.get(session_id)
        if not info:
            return web.Response(status=404)

        info["last_access"] = time.monotonic()
        seg_path = os.path.join(info["dir"], filename)

        if not os.path.exists(seg_path):
            return web.Response(status=404)

        with open(seg_path, "rb") as f:
            data = f.read()

        return web.Response(
            body=data,
            content_type="video/mp2t",
            headers={"Cache-Control": "no-cache"},
        )

    async def on_shutdown(self, app):
        for sid, info in self.sessions.items():
            if info["proc"].returncode is None:
                log.info("Shutdown: killing [%s]", sid)
                info["proc"].kill()

    def create_app(self):
        app = web.Application()
        app.router.add_get("/health", self.handle_health)
        app.router.add_get("/capabilities", self.handle_capabilities)
        app.router.add_post("/start/{session_id}", self.handle_start)
        app.router.add_post("/stop/{session_id}", self.handle_stop)
        app.router.add_get("/hls/{session_id}/playlist.m3u8", self.handle_playlist)
        app.router.add_get("/hls/{session_id}/{filename}", self.handle_segment)
        app.on_shutdown.append(self.on_shutdown)

        async def start_bg(app):
            await self._probe_encoders()
            app["cleanup_task"] = asyncio.ensure_future(self.cleanup_idle())

        async def stop_bg(app):
            app["cleanup_task"].cancel()

        app.on_startup.append(start_bg)
        app.on_cleanup.append(stop_bg)
        return app

    def run(self):
        os.makedirs(self.hls_dir, exist_ok=True)
        app = self.create_app()
        log.info("gpu-share starting on %s:%d", self.host, self.port)
        log.info("Resolutions: %s | HLS: %ds segments x %d window",
                 ", ".join(self.presets.keys()), self.hls_time, self.hls_list_size)
        log.info("Endpoints: /health, /capabilities, /start, /stop, /hls")
        web.run_app(app, host=self.host, port=self.port)


def main():
    config = load_config()
    server = GpuShareServer(config)
    server.run()
