"""Python client for gpu-share NVENC encoding proxy."""
import aiohttp
import asyncio


class GpuShareClient:
    """Async client for the gpu-share HTTP API."""

    def __init__(self, base_url="http://localhost:8553", api_key=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._session = None

    def _headers(self):
        h = {}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def health(self):
        """Get service health and active sessions."""
        session = await self._get_session()
        async with session.get(f"{self.base_url}/health") as resp:
            return await resp.json()

    async def start(self, session_id, source_url, resolution=None):
        """Start a transcoding session."""
        session = await self._get_session()
        body = {"source": source_url}
        if resolution:
            body["resolution"] = resolution
        async with session.post(
            f"{self.base_url}/start/{session_id}",
            json=body,
            headers=self._headers(),
        ) as resp:
            return await resp.json()

    async def stop(self, session_id):
        """Stop a transcoding session."""
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/stop/{session_id}",
            headers=self._headers(),
        ) as resp:
            return await resp.json()

    async def get_playlist(self, session_id):
        """Get HLS playlist text."""
        session = await self._get_session()
        async with session.get(f"{self.base_url}/hls/{session_id}/playlist.m3u8") as resp:
            if resp.status == 503:
                return None  # Stream still starting
            return await resp.text()

    async def get_segment(self, session_id, filename):
        """Get an HLS segment (binary)."""
        session = await self._get_session()
        async with session.get(f"{self.base_url}/hls/{session_id}/{filename}") as resp:
            if resp.status != 200:
                return None
            return await resp.read()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# Quick CLI usage
if __name__ == "__main__":
    import sys
    import json

    async def main():
        url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8553"
        client = GpuShareClient(url)
        health = await client.health()
        print(json.dumps(health, indent=2))
        await client.close()

    asyncio.run(main())
