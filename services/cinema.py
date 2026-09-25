import asyncio
import html
import json
import logging
import os
import secrets
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode, urlparse

from aiohttp import web

logger = logging.getLogger(__name__)


class CinemaStream:
    def __init__(self) -> None:
        self._app = web.Application()
        self._app.add_routes(
            [
                web.get("/", self._handle_index),
                web.get("/healthz", self._handle_health),
                web.get("/stream/{filename}", self._handle_stream_file),
            ]
        )
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._directory: Path | None = None
        self._source_url: str | None = None
        self._title = "Rey Cinema"
        self._token = secrets.token_urlsafe(24)
        self._lock = asyncio.Lock()

    @property
    def public_url(self) -> str | None:
        if self._directory is None:
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
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("La URL debe comenzar con http:// o https://.")
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("No se encontró FFmpeg en el servidor.")
        async with self._lock:
            await self._stop_locked()
            self._directory = Path(tempfile.mkdtemp(prefix="rey-cinema-"))
            self._source_url = source_url
            self._title = source_url
            playlist = self._directory / "stream.m3u8"
            output_pattern = self._directory / "segment-%05d.ts"
            try:
                stream_url, input_headers, title = await self._resolve_media_url(source_url)
                self._title = title or source_url
            except Exception:
                await self._stop_locked()
                raise
            ffmpeg_input_options = []
            if input_headers:
                header_lines = [
                    f"{key}: {value}"
                    for key, value in input_headers.items()
                    if key.lower() not in {"host", "content-length"}
                ]
                if header_lines:
                    ffmpeg_input_options = ["-headers", "\r\n".join(header_lines) + "\r\n"]
            command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-re",
                *ffmpeg_input_options,
                "-i",
                stream_url,
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-tune",
                "zerolatency",
                "-vf",
                "scale=w=1280:h=-2:force_original_aspect_ratio=decrease",
                "-r",
                "30",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-f",
                "hls",
                "-hls_time",
                "2",
                "-hls_list_size",
                "6",
                "-hls_flags",
                "delete_segments+append_list",
                "-hls_segment_filename",
                str(output_pattern),
                str(playlist),
            ]
            self._process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            asyncio.create_task(self._log_process_errors(self._process))
            logger.info("Cine iniciado desde %s", source_url)
            return self.public_url or ""

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()

    async def _stop_locked(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        if self._directory is not None:
            shutil.rmtree(self._directory, ignore_errors=True)
        self._directory = None
        self._source_url = None

    async def _resolve_media_url(self, source_url: str) -> tuple[str, dict[str, str], str]:
        commands = [
            self._yt_dlp_command(source_url),
            self._yt_dlp_command(
                source_url,
                "--extractor-args",
                "youtube:player_client=android_vr",
            ),
        ]
        last_detail = ""
        for command in commands:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                break
            last_detail = stderr.decode(errors="replace").strip()[-500:]
        else:
            raise RuntimeError(
                "No pude obtener el video desde la URL. "
                f"YouTube solicita autenticación o bloqueó este video: {last_detail}"
            )
        try:
            metadata = json.loads(stdout.decode(errors="replace"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("yt-dlp no devolvió información válida del video.") from exc
        media_url = str(metadata.get("url", "")).strip()
        if not media_url:
            raise RuntimeError("La URL no devolvió un flujo de video.")
        headers = {
            str(key): str(value)
            for key, value in (metadata.get("http_headers") or {}).items()
        }
        return media_url, headers, str(metadata.get("title", "")).strip()

    @staticmethod
    def _yt_dlp_command(source_url: str, *extra_args: str) -> list[str]:
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--dump-single-json",
            "--no-warnings",
            "-f",
            "best[height<=720]/best",
        ]
        cookies_file = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
        if cookies_file:
            command.extend(["--cookies", cookies_file])
        command.extend(extra_args)
        command.append(source_url)
        return command

    async def _log_process_errors(self, process: asyncio.subprocess.Process) -> None:
        if process.stderr is None:
            return
        async for line in process.stderr:
            message = line.decode(errors="replace").strip()
            if message:
                logger.warning("FFmpeg cine: %s", message)

    def _is_authorized(self, request: web.Request) -> bool:
        return secrets.compare_digest(
            request.query.get("token", ""),
            self._token,
        )

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.Response(text="ok\n", content_type="text/plain")

    async def _handle_index(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            raise web.HTTPUnauthorized(text="Enlace de cine no autorizado.")
        if self._directory is None:
            raise web.HTTPNotFound(text="No hay una transmisión activa.")
        playlist_url = "/stream/stream.m3u8?" + urlencode({"token": self._token})
        page = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>{html.escape(self._title)}</title>
<style>body{{margin:0;background:#111;color:#eee;font-family:system-ui}}main{{max-width:1100px;margin:2rem auto;padding:1rem}}video{{width:100%;background:#000}}</style>
</head><body><main><h1>{html.escape(self._title)}</h1>
<video id="player" controls autoplay muted playsinline></video>
<p>Transmisión de Rey Cinema. Activa el sonido desde los controles del reproductor.</p></main>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<script>
const video = document.getElementById("player");
const source = "{playlist_url}";
if (video.canPlayType("application/vnd.apple.mpegurl")) {{
  video.src = source;
}} else if (window.Hls && Hls.isSupported()) {{
  const hls = new Hls({{liveSyncDurationCount: 2}});
  hls.loadSource(source);
  hls.attachMedia(video);
}} else {{
  document.querySelector("p").textContent = "Este navegador no soporta reproducción HLS.";
}}
</script></body></html>"""
        return web.Response(text=page, content_type="text/html")

    async def _handle_stream_file(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            raise web.HTTPUnauthorized(text="Enlace de cine no autorizado.")
        if self._directory is None:
            raise web.HTTPNotFound(text="No hay una transmisión activa.")
        filename = request.match_info["filename"]
        if Path(filename).name != filename or Path(filename).suffix not in {".m3u8", ".ts"}:
            raise web.HTTPNotFound()
        path = self._directory / filename
        if not path.is_file():
            raise web.HTTPNotFound()
        if path.suffix == ".m3u8":
            content = path.read_text(encoding="utf-8")
            lines = [
                line if not line or line.startswith("#") else f"{line}?{urlencode({'token': self._token})}"
                for line in content.splitlines()
            ]
            return web.Response(
                text="\n".join(lines) + "\n",
                content_type="application/vnd.apple.mpegurl",
            )
        return web.FileResponse(path)
