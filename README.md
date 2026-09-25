# Albion Party Manager

## Modo de voz de Rey

1. Entra al canal de voz y escribe `rey escucha`.
2. Habla cuando quieras, por ejemplo: “¿Qué build me recomiendas para healer?”; ya no necesitas decir “Rey”.
3. Rey espera una pausa, transcribe el turno en español, genera la respuesta y la reproduce en el canal.
4. Escribe `rey deja de escuchar` para apagar la captura sin sacar al bot del canal.

El modo actual es por turnos, no responde continuamente a todo el audio: espera una pausa, transcribe cada turno audible y responde sin exigir una palabra de activación. Necesita `GROQ_API_KEY`, permisos de **Conectar**, **Hablar** y **Escuchar**, FFmpeg en el contenedor y el modelo `whisper-large-v3-turbo` disponible en Groq.

## Modo cine externo

El comando `/cine` crea una transmisión HLS privada en el mismo servicio de Railway:

- `/cine iniciar <url>` obtiene el video con `yt-dlp`, lo convierte con FFmpeg y devuelve un enlace privado.
- `/cine parar` detiene la transmisión y elimina los segmentos temporales.

Configura `RAILWAY_PUBLIC_DOMAIN` automáticamente en Railway o define `PUBLIC_BASE_URL` con la URL pública del servicio. El enlace incluye un token temporal generado al arrancar el bot; no compartas ese enlace públicamente. Este modo entrega video real en un reproductor web externo, no un stream Go Live dentro de Discord.