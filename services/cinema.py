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
                web.post("/control", self._handle_control),
            ]
        )
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._video_id: str | None = None
        self._started_at: float | None = None
        self._token = secrets.token_urlsafe(24)
        self._host_token = secrets.token_urlsafe(24)
        self._position = 0.0
        self._playing = True
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
            base_url = "https://albionbit2-production.up.railway.app"
        return f"{base_url}/?{urlencode({'token': self._token})}"

    @property
    def organizer_url(self) -> str | None:
        if self._video_id is None:
            return None
        viewer_url = self.public_url
        if viewer_url is None:
            return None
        return f"{viewer_url}&{urlencode({'host': self._host_token})}"

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
            self._position = 0.0
            self._playing = True
        logger.info("Cine web iniciado para el video de YouTube %s", video_id)
        return self.public_url or ""

    async def stop(self) -> None:
        async with self._lock:
            self._video_id = None
            self._started_at = None
            self._position = 0.0
            self._playing = True

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
                "position": self._current_position(),
                "playing": self._playing,
                "server_time": time.time(),
            }
        )

    async def _handle_control(self, request: web.Request) -> web.Response:
        if not secrets.compare_digest(
            request.query.get("host", ""),
            self._host_token,
        ):
            raise web.HTTPUnauthorized(text="Control de organizador no autorizado.")
        if self._video_id is None:
            raise web.HTTPNotFound(text="No hay una transmisión activa.")
        try:
            payload = await request.json()
            action = str(payload.get("action", ""))
            position = float(payload.get("position", 0))
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text="Control de cine inválido.")
        if action == "play":
            self._position = max(0.0, position)
            self._started_at = time.time() - self._position
            self._playing = True
        elif action == "pause":
            self._position = self._current_position()
            self._playing = False
        elif action == "seek":
            self._position = max(0.0, position)
            if self._playing:
                self._started_at = time.time() - self._position
        elif action == "restart":
            self._position = 0.0
            self._started_at = time.time()
            self._playing = True
        else:
            raise web.HTTPBadRequest(text="Acción de cine no reconocida.")
        return web.json_response({"ok": True})

    def _current_position(self) -> float:
        if self._playing and self._started_at is not None:
            return max(0.0, time.time() - self._started_at)
        return self._position

    async def _handle_index(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            raise web.HTTPUnauthorized(text="Enlace de cine no autorizado.")
        if self._video_id is None:
            raise web.HTTPNotFound(text="No hay una transmisión activa.")
        state_url = "/state?" + urlencode({"token": self._token})
        control_url = "/control?" + urlencode({"host": self._host_token})
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
const isHost = new URLSearchParams(location.search).has("host");
function onYouTubeIframeAPIReady() {{
  fetch(stateUrl).then(response => response.json()).then(data => {{
    state = data;
    player = new YT.Player("player", {{
      videoId: data.video_id,
      width: "100%",
      height: "100%",
      playerVars: {{autoplay: 1, controls: isHost ? 1 : 0, playsinline: 1, rel: 0}},
      events: {{onReady: syncPlayer, onStateChange: onPlayerStateChange}}
    }});
  }}).catch(() => document.getElementById("status").textContent = "No se pudo cargar la transmisión.");
}}
function syncPlayer() {{
  ready = true;
  player.mute();
  syncToState();
  document.getElementById("status").textContent = isHost ? "Controles de organizador activos." : "Transmisión sincronizada.";
}}
function syncToState() {{
  const elapsed = state.position;
  if (Math.abs(player.getCurrentTime() - elapsed) > 2) player.seekTo(elapsed, true);
  if (state.playing) player.playVideo(); else player.pauseVideo();
}}
function onPlayerStateChange(event) {{
  if (!isHost || !ready) return;
  if (event.data === YT.PlayerState.PLAYING) sendControl("play");
  if (event.data === YT.PlayerState.PAUSED) sendControl("pause");
}}
function sendControl(action, position = player.getCurrentTime()) {{
  fetch("{control_url}", {{
    method: "POST", headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{action: action, position: position}})
  }});
}}
if (isHost) {{
  const controls = document.createElement("p");
  controls.innerHTML = '<button onclick="sendControl(\\'play\\')">Reproducir</button> <button onclick="sendControl(\\'pause\\')">Pausar</button> <button onclick="sendControl(\\'seek\\', player.getCurrentTime() + 10)">Adelantar 10 s</button> <button onclick="sendControl(\\'seek\\', Math.max(0, player.getCurrentTime() - 10))">Retroceder 10 s</button> <button onclick="sendControl(\\'restart\\')">Reiniciar</button>';
  document.querySelector("main").appendChild(controls);
}}
setInterval(() => {{
  fetch(stateUrl).then(response => response.json()).then(data => {{
    state = data;
    if (ready && !isHost) syncToState();
  }});
}}, 10000);
</script></body></html>"""
        return web.Response(text=page, content_type="text/html")
