import asyncio
import logging
import os
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp

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
                web.post("/presence", self._handle_presence),
                web.get("/login", self._handle_login),
                web.get("/oauth/callback", self._handle_oauth_callback),
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
        self._viewers: dict[str, dict[str, str | float]] = {}
        self._oauth_states: dict[str, bool] = {}
        self._sessions: dict[str, dict[str, str]] = {}
        self._lock = asyncio.Lock()

    @property
    def public_url(self) -> str | None:
        if self._video_id is None:
            return None
        return f"{self._base_url()}/?{urlencode({'token': self._token})}"

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

    def _base_url(self) -> str:
        base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
            base_url = f"https://{domain}" if domain else ""
        return base_url or "https://albionbit2-production.up.railway.app"

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
            self._viewers.clear()
        logger.info("Cine web iniciado para el video de YouTube %s", video_id)
        return self.public_url or ""

    async def stop(self) -> None:
        async with self._lock:
            self._video_id = None
            self._started_at = None
            self._position = 0.0
            self._playing = True
            self._viewers.clear()

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
        self._prune_viewers()
        current_user = self._sessions.get(request.cookies.get("cine_session", ""))
        return web.json_response(
            {
                "video_id": self._video_id,
                "position": self._current_position(),
                "playing": self._playing,
                "server_time": time.time(),
                "viewers": [
                    {
                        "name": viewer["name"],
                        "avatar": viewer["avatar"],
                        "user_id": viewer["user_id"],
                        "role": viewer["role"],
                        "session": session,
                    }
                    for session, viewer in self._viewers.items()
                ],
                "current_user": current_user,
            }
        )

    async def _handle_login(self, request: web.Request) -> web.Response:
        client_id = os.environ.get("DISCORD_CLIENT_ID", "").strip()
        if not client_id:
            raise web.HTTPServiceUnavailable(
                text="El inicio con Discord no está configurado."
            )
        token = request.query.get("token", "")
        if not self._is_authorized_token(token):
            raise web.HTTPUnauthorized(text="Enlace de cine no autorizado.")
        state = secrets.token_urlsafe(24)
        self._oauth_states[state] = request.query.get("host", "") == self._host_token
        redirect_uri = self._oauth_redirect_uri()
        params = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "identify",
                "state": state,
            }
        )
        return web.HTTPFound(f"https://discord.com/oauth2/authorize?{params}")

    async def _handle_oauth_callback(self, request: web.Request) -> web.Response:
        state = request.query.get("state", "")
        is_host = self._oauth_states.pop(state, None)
        if is_host is None:
            raise web.HTTPBadRequest(text="Sesión OAuth inválida o expirada.")
        code = request.query.get("code", "")
        client_id = os.environ.get("DISCORD_CLIENT_ID", "").strip()
        client_secret = os.environ.get("DISCORD_CLIENT_SECRET", "").strip()
        if not code or not client_id or not client_secret:
            raise web.HTTPServiceUnavailable(text="OAuth de Discord incompleto.")
        redirect_uri = self._oauth_redirect_uri()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            ) as response:
                if response.status != 200:
                    raise web.HTTPBadGateway(text="Discord rechazó la autenticación.")
                token_data = await response.json()
            async with session.get(
                "https://discord.com/api/users/@me",
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            ) as response:
                if response.status != 200:
                    raise web.HTTPBadGateway(text="No pude obtener tu perfil de Discord.")
                profile = await response.json()
        session_id = secrets.token_urlsafe(24)
        self._sessions[session_id] = {
            "user_id": str(profile.get("id", "")),
            "name": str(profile.get("global_name") or profile.get("username") or "Discord"),
            "avatar": str(profile.get("avatar") or ""),
            "role": "Organizador" if is_host else "Espectador",
        }
        target = f"/?{urlencode({'token': self._token})}"
        response = web.HTTPFound(f"{target}&host={self._host_token}" if is_host else target)
        response.set_cookie("cine_session", session_id, max_age=86400, httponly=True, samesite="Lax", secure=True)
        return response

    def _oauth_redirect_uri(self) -> str:
        return f"{self._base_url()}/oauth/callback"

    def _is_authorized_token(self, token: str) -> bool:
        return secrets.compare_digest(token, self._token)

    async def _handle_presence(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            raise web.HTTPUnauthorized(text="Enlace de cine no autorizado.")
        if self._video_id is None:
            raise web.HTTPNotFound(text="No hay una transmisión activa.")
        try:
            payload = await request.json()
            session = str(payload.get("session", "")).strip()
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="Presencia de espectador inválida.")
        if not re.fullmatch(r"[\w-]{8,64}", session):
            raise web.HTTPBadRequest(text="Sesión inválida.")
        discord_session = self._sessions.get(request.cookies.get("cine_session", ""))
        if discord_session is None:
            raise web.HTTPUnauthorized(text="Inicia sesión con Discord primero.")
        self._viewers[session] = {
            "name": discord_session["name"],
            "avatar": discord_session["avatar"],
            "user_id": discord_session["user_id"],
            "role": discord_session["role"],
            "last_seen": time.time(),
        }
        self._prune_viewers()
        return web.json_response({"ok": True})

    def _prune_viewers(self) -> None:
        cutoff = time.time() - 30
        self._viewers = {
            session: viewer
            for session, viewer in self._viewers.items()
            if float(viewer["last_seen"]) >= cutoff
        }

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
        login_url = "/login?" + urlencode(
            {"token": self._token, "host": self._host_token}
            if "host" in request.query
            else {"token": self._token}
        )
        page = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Rey Cinema</title>
<style>body{{margin:0;background:#111;color:#eee;font-family:system-ui}}main{{max-width:1100px;margin:2rem auto;padding:1rem}}#player{{aspect-ratio:16/9;width:100%;background:#000}}p{{color:#bbb}}#auth{{margin:.8rem 0}}#auth a{{display:inline-block;padding:.6rem 1rem;border-radius:8px;background:#5865f2;color:#fff;text-decoration:none;font-weight:700}}#viewers{{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;margin:.8rem 0}}.viewer{{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;color:#fff;font-weight:700;border:2px solid #111;box-shadow:0 0 0 1px #777;background-size:cover;background-position:center}}</style>
</head><body><main><h1>Rey Cinema</h1><div id="player"></div>
<div id="auth"><a id="login" href="{login_url}">Entrar con Discord</a></div>
<div id="viewers"><span id="viewer-count">0 espectadores</span></div>
<p id="status">Sincronizando la transmisión...</p></main>
<script src="https://www.youtube.com/iframe_api"></script>
<script>
const stateUrl = "{state_url}";
const presenceUrl = "{"/presence?" + urlencode({"token": self._token})}";
let player;
let state;
let ready = false;
const isHost = new URLSearchParams(location.search).has("host");
const sessionKey = "rey-cinema-session";
const session = localStorage.getItem(sessionKey) || crypto.randomUUID().replaceAll("-", "");
localStorage.setItem(sessionKey, session);
function updatePresence() {{
  fetch(presenceUrl, {{method: "POST", headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{session: session}})}});
}}
function renderViewers(viewers) {{
  const container = document.getElementById("viewers");
  container.querySelectorAll(".viewer").forEach(element => element.remove());
  document.getElementById("viewer-count").textContent = `${{viewers.length}} espectador${{viewers.length === 1 ? "" : "es"}}`;
  viewers.forEach(viewer => {{
    const bubble = document.createElement("span");
    bubble.className = "viewer";
    bubble.title = `${{viewer.name}} · ${{viewer.role}}`;
    bubble.textContent = viewer.name.slice(0, 2).toUpperCase();
    if (viewer.avatar) bubble.style.backgroundImage = `url(https://cdn.discordapp.com/avatars/${{viewer.user_id}}/${{viewer.avatar}}.png?size=64)`;
    bubble.style.backgroundColor = `hsl(${{Math.abs([...viewer.name].reduce((sum, char) => sum + char.charCodeAt(0), 0)) % 360}} 65% 45%)`;
    container.appendChild(bubble);
  }});
}}
function onYouTubeIframeAPIReady() {{
  fetch(stateUrl).then(response => response.json()).then(data => {{
    state = data;
    if (!data.current_user) {{
      document.getElementById("status").textContent = "Inicia sesión con Discord para entrar al cine.";
      return;
    }}
    document.getElementById("auth").innerHTML = `<strong>${{data.current_user.name}}</strong> · ${{data.current_user.role}}`;
    updatePresence();
    renderViewers(data.viewers || []);
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
  updatePresence();
  fetch(stateUrl).then(response => response.json()).then(data => {{
    state = data;
    renderViewers(data.viewers || []);
    if (ready && !isHost) syncToState();
  }});
}}, 10000);
</script></body></html>"""
        return web.Response(text=page, content_type="text/html")
