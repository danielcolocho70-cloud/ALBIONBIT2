from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = (
    os.environ.get("DISCORD_TOKEN")
    or os.environ.get("TOKEN")
    or ""
).strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "groq2o-mini").strip()
GROQ_MODEL_FALLBACKS = [
    model.strip()
    for model in os.environ.get(
        "GROQ_MODEL_FALLBACKS",
        "groq2o-mini,groq2o-base,groq2o-instruct,gpt-4o-mini,gpt-4o,gpt-3.5-turbo",
    ).split(",")
    if model.strip()
]
GROQ_API_URL = os.environ.get(
    "GROQ_API_URL",
    "https://api.groq.com/openai/v1/chat/completions",
).strip()
REY_VOICE_ENABLED = os.environ.get("REY_VOICE_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
REY_LISTEN_ENABLED = os.environ.get("REY_LISTEN_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
