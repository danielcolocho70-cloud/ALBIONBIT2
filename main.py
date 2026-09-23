import asyncio
import logging
import discord
from discord.ext import commands
from config import TOKEN
from database.database import db
from cogs.afk import AFK_GUILD_ID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

if not TOKEN:
    raise RuntimeError("Falta el token de Discord. Define DISCORD_TOKEN o TOKEN en el entorno o .env")

intents = discord.Intents.all()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print("=" * 40)
    print(f"Bot conectado como {bot.user}")
    print("=" * 40)

    synced = await bot.tree.sync()
    try:
        afk_synced = await bot.tree.sync(guild=discord.Object(id=AFK_GUILD_ID))
    except discord.Forbidden:
        logging.getLogger(__name__).warning(
            "No se pudieron sincronizar comandos en la guild AFK %s: acceso denegado",
            AFK_GUILD_ID,
        )
        afk_synced = []

    print(f"Slash Commands globales: {len(synced)} | AFK: {len(afk_synced)}")


async def main():
    async with bot:

        db.crear_tablas()

        # Cargar los módulos (Cogs)
        await bot.load_extension("cogs.aventura")
        await bot.load_extension("cogs.afk")
        await bot.load_extension("cogs.redsec_chat")
        await bot.load_extension("cogs.killboard")

        await bot.start(TOKEN)


asyncio.run(main())
