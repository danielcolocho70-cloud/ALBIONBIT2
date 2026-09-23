# Albion Party Manager

## Modo de voz de Rey

1. Entra al canal de voz y escribe `rey escucha`.
2. Habla cuando quieras, por ejemplo: “¿Qué build me recomiendas para healer?”; ya no necesitas decir “Rey”.
3. Rey espera una pausa, transcribe el turno en español, genera la respuesta y la reproduce en el canal.
4. Escribe `rey deja de escuchar` para apagar la captura sin sacar al bot del canal.

El modo actual es por turnos, no responde continuamente a todo el audio: espera una pausa, transcribe cada turno audible y responde sin exigir una palabra de activación. Necesita `GROQ_API_KEY`, permisos de **Conectar**, **Hablar** y **Escuchar**, FFmpeg en el contenedor y el modelo `whisper-large-v3-turbo` disponible en Groq.