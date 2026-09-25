# Albion Party Manager

## Modo de voz de Rey

1. Entra al canal de voz y escribe `rey escucha`.
2. Habla cuando quieras, por ejemplo: “¿Qué build me recomiendas para healer?”; ya no necesitas decir “Rey”.
3. Rey espera una pausa, transcribe el turno en español, genera la respuesta y la reproduce en el canal.
4. Escribe `rey deja de escuchar` para apagar la captura sin sacar al bot del canal.

El modo actual es por turnos, no responde continuamente a todo el audio: espera una pausa, transcribe cada turno audible y responde sin exigir una palabra de activación. Necesita `GROQ_API_KEY`, permisos de **Conectar**, **Hablar** y **Escuchar**, FFmpeg en el contenedor y el modelo `whisper-large-v3-turbo` disponible en Groq.

## Modo cine externo

El comando `/cine` crea una sala web privada en el mismo servicio de Railway:

- `/cine iniciar <url>` carga el reproductor oficial de YouTube y devuelve un enlace.
- `/cine parar` cierra la sala.
- Cualquier persona que tenga el enlace puede entrar; no se requiere una cuenta de Discord.
- Los navegadores nuevos saltan automáticamente a la posición actual para mantener la reproducción sincronizada.
- Cada espectador elige un nombre y aparece como una burbuja activa; las burbujas se retiran tras 30 segundos sin actividad.

Configura `RAILWAY_PUBLIC_DOMAIN` automáticamente en Railway o define `PUBLIC_BASE_URL` con la URL pública del servicio. El enlace incluye un token temporal generado al arrancar el bot; compártelo solo con quienes deban ver el cine. Este modo usa el reproductor oficial de YouTube y no es un stream Go Live dentro de Discord. El video debe permitir reproducción incrustada; algunos videos pueden bloquearla.

La escucha de voz en tiempo real está desactivada temporalmente (`REY_LISTEN_ENABLED=false`). Rey sigue entrando al canal y hablando cuando respondes desde el chat. Para reactivar la escucha, configura `REY_LISTEN_ENABLED=true` en Railway y redeploya.
