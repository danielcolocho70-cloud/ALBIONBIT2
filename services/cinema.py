import asyncio
import logging
import os
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlparse

from aiohttp import web

logger = logging.getLogger(__name__)


class CinemaStream:
    def __init__(self) -> None:
        self._app = web.Application()
        self._app.add_routes(
            [
                web.get("/", self._handle_index),
                web.get("/healthz", self._handle_health),
                web.get("/state", self._handle_state),
            ]
        )
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._video_id: str | None = None
        self._started_at: float | None = None
        self._token = secrets.token_urlsafe(24)
        self._lock = asyncio.Lock()

    @property
    def public_url(self) -> str | None:
        if self._video_id is None:
            return None
        base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
            base_url = f"https://{domain}" if domain else ""
        if not base_url:
            base_url = "https://albion2-production.up.railway.app"
        return f"{base_url}/?{urlencode({'token': self._token})}"

    async def start_server(self) -> None:
        if self._runner is not None:
            return
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        port = int(os.environ.get("PORT", "8080"))
        self._site = web.TCPSite(self._runner, "0.0.0.0", port)
        await self._site.start()
        logger.info("Servidor de cine iniciado en el puerto %s", port)

    async def stop_server(self) -> None:
        await self.stop()
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def start(self, source_url: str) -> str:
        video_id = self._youtube_video_id(source_url)
        if video_id is None:
            raise ValueError(
                "El cine web necesita una URL de YouTube válida y con inserción permitida."
            )
        async with self._lock:
            self._video_id = video_id
            self._started_at = time.time()
        logger.info("Cine web iniciado para el video de YouTube %s", video_id)
        return self.public_url or ""

    async def stop(self) -> None:
        async with self._lock:
            self._video_id = None
            self._started_at = None

    @staticmethod
    def _youtube_video_id(source_url: str) -> str | None:
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"}:
            return None
        hostname = (parsed.hostname or "").lower()
        if hostname in {"youtu.be", "www.youtu.be"}:
            video_id = parsed.path.strip("/").split("/")[0]
        elif hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [""])[0]
            elif parsed.path.startswith(("/embed/", "/shorts/")):
                video_id = parsed.path.split("/")[2]
            else:
                video_id = ""
        else:
            return None
        return video_id if re.fullmatch(r"[\w-]{11}", video_id) else None

    def _is_authorized(self, request: web.Request) -> bool:
        return secrets.compare_digest(request.query.get("token", ""), self._token)

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.Response(text="ok\n", content_type="text/plain")

    async def _handle_state(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            raise web.HTTPUnauthorized(text="Enlace de cine no autorizado.")
        if self._video_id is None or self._started_at is None:
            raise web.HTTPNotFound(text="No hay una transmisión activa.")
        return web.json_response(
            {
                "video_id": self._video_id,
                "started_at": self._started_at,
                "server_time": time.time(),
            }
        )

    async def _handle_index(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            raise web.HTTPUnauthorized(text="Enlace de cine no autorizado.")
        if self._video_id is None:
            raise web.HTTPNotFound(text="No hay una transmisión activa.")
        state_url = "/state?" + urlencode({"token": self._token})
        page = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Rey Cinema</title>
<style>body{{margin:0;background:#111;color:#eee;font-family:system-ui}}main{{max-width:1100px;margin:2rem auto;padding:1rem}}#player{{aspect-ratio:16/9;width:100%;background:#000}}p{{color:#bbb}}</style>
</head><body><main><h1>Rey Cinema</h1><div id="player"></div>
<p id="status">Sincronizando la transmisión...</p></main>
<script src="https://www.youtube.com/iframe_api"></script>
<script>
const stateUrl = "{state_url}";
let player;
let state;
let ready = false;
function onYouTubeIframeAPIReady() {{
  fetch(stateUrl).then(response => response.json()).then(data => {{
    state = data;
    player = new YT.Player("player", {{
      videoId: data.video_id,
      width: "100%",
      height: "100%",
      playerVars: {{autoplay: 1, controls: 1, playsinline: 1, rel: 0}},
      events: {{onReady: syncPlayer}}
    }});
  }}).catch(() => document.getElementById("status").textContent = "No se pudo cargar la transmisión.");
}}
function syncPlayer() {{
  ready = true;
  player.mute();
  const elapsed = Math.max(0, state.server_time - state.started_at + (Date.now() / 1000 - state.server_time));
  player.seekTo(elapsed, true);
  player.playVideo();
  document.getElementById("status").textContent = "Transmisión sincronizada.";
}}
setInterval(() => {{
  if (!ready || !state) return;
  const elapsed = Math.max(0, state.server_time - state.started_at + (Date.now() / 1000 - state.server_time));
  if (Math.abs(player.getCurrentTime() - elapsed) > 3) player.seekTo(elapsed, true);
}}, 10000);
</script></body></html>"""
        return web.Response(text=page, content_type="text/html")
