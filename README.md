# Albion Party Manager

## Modo de voz de Rey

1. Entra al canal de voz y escribe `rey escucha`.
2. Habla comenzando la frase con “Rey”, por ejemplo: “Rey, ¿qué build me recomiendas para healer?”.
3. Rey espera una pausa, transcribe el turno en español, genera la respuesta y la reproduce en el canal.
4. Escribe `rey deja de escuchar` para apagar la captura sin sacar al bot del canal.

El modo actual es por turnos, no escucha continuamente la conversación: solo procesa audio que contiene “Rey”. Necesita `GROQ_API_KEY`, permisos de **Conectar** y **Hablar**, FFmpeg en el contenedor y el modelo `whisper-large-v3-turbo` disponible en Groq.