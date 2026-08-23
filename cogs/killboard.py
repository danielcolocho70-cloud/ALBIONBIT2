import asyncio
import logging
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

import aiohttp
from io import BytesIO
from PIL import Image
from urllib.parse import quote

from services.albion_service import AlbionService
from database.database import db

LOGGER = logging.getLogger("killboard")


class Killboard(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger("killboard")
        
        # Asegurar que existe la columna 'server' en la BD (migración)
        try:
            cur = db.cursor
            cur.execute("ALTER TABLE killboard_tracked ADD COLUMN server TEXT DEFAULT 'europe'")
            db.conn.commit()
        except Exception:
            pass  # Columna ya existe
        
        self.last_poll_at: datetime | None = None
        self.last_event_count = 0
        self.last_matching_events = 0
        self._task = bot.loop.create_task(self._poll_loop())

    async def _poll_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self.check_all_tracked()
            except Exception:
                LOGGER.exception("Error en poll killboard")
            await asyncio.sleep(30)

    async def check_all_tracked(self):
        cur = db.cursor
        cur.execute("SELECT guild_id, channel_kills, channel_deaths, albion_guild_id, server FROM killboard_tracked")
        rows = cur.fetchall()
        if not rows:
            LOGGER.info("No hay guilds trackeadas en killboard")
            return

        # Agrupar por servidor para hacer menos llamadas a API
        guilds_by_server = {}
        for row in rows:
            guild_id, channel_kills, channel_deaths, albion_guild_id, server = row
            server = server or "europe"  # Default si es None
            if server not in guilds_by_server:
                guilds_by_server[server] = []
            guilds_by_server[server].append((guild_id, channel_kills, channel_deaths, albion_guild_id))
        
        # Procesar eventos por servidor
        for server, guilds in guilds_by_server.items():
            try:
                from services.albion_service import AlbionService
                albion = AlbionService(server=server)
            except Exception as e:
                LOGGER.error(f"Error inicializando AlbionService para servidor {server}: {e}")
                continue
                
            events = await albion.fetch_events(limit=50)
            self.last_poll_at = datetime.now(timezone.utc)
            self.last_event_count = len(events)
            self.last_matching_events = 0
            LOGGER.debug(f"Obtenidos {len(events)} eventos de Albion API ({server})")

            for guild_id, channel_kills, channel_deaths, albion_guild_id in guilds:
                LOGGER.debug(f"Checkeando guild Discord {guild_id} contra Albion guild {albion_guild_id}")

                for ev in events:
                    event_id = ev.get("EventId") or ev.get("Id") or ev.get("Id")
                    if not event_id:
                        continue

                    # skip if already processed
                    cur.execute("SELECT 1 FROM killboard_events WHERE event_id=?", (event_id,))
                    if cur.fetchone():
                        continue

                    killer = ev.get("Killer") or {}
                    victim = ev.get("Victim") or {}

                    sent = False

                killer_gid = str(killer.get("GuildId")) if killer.get("GuildId") else None
                victim_gid = str(victim.get("GuildId")) if victim.get("GuildId") else None
                
                is_kill = bool(killer and killer_gid == str(albion_guild_id))
                is_death = bool(victim and victim_gid == str(albion_guild_id))
                
                if not (is_kill or is_death):
                    LOGGER.debug(f"EventId {event_id}: Killer Guild={killer_gid}, Victim Guild={victim_gid}, Target={albion_guild_id}")
                    continue

                self.last_matching_events += 1
                LOGGER.info(f"Evento coincidente encontrado: Kill={is_kill}, Death={is_death}, EventId={event_id}")

                event = await self.albion.get_event(str(event_id)) or ev

                if is_kill:
                    await self._send_event(channel_kills, event, "kill", guild_id)
                    sent = True

                if is_death:
                    await self._send_event(channel_deaths, event, "death", guild_id)
                    sent = True

                if sent:
                    cur.execute(
                        "INSERT OR IGNORE INTO killboard_events (event_id, guild_id, event_type) VALUES (?,?,?)",
                        (event_id, guild_id, 'kill' if killer.get("GuildId") == albion_guild_id else 'death'),
                    )
                    db.conn.commit()

    async def _send_event(self, channel_id, ev, ev_type: str, guild_id: int):
        if not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                return

        killer = ev.get("Killer") or {}
        victim = ev.get("Victim") or {}

        title = "Kill" if ev_type == "kill" else "Death"
        color = 0xC0392B if ev_type == "death" else 0x27AE60

        # Render a card image that resembles the sample and send it as a file with a minimal embed
        try:
            from services.killboard_renderer import render_kill_event
        except Exception:
            render_kill_event = None

        # helper to extract item ids from event participant
        def extract_item_ids(part):
            items = []
            equipment = part.get("Equipment") or part.get("Items") or []
            if isinstance(equipment, dict):
                equipment = [
                    equipment.get(slot)
                    for slot in ("MainHand", "OffHand", "Head", "Armor", "Shoes", "Bag", "Cape", "Mount", "Potion", "Food")
                ]
            for p in equipment:
                if isinstance(p, dict):
                    item_id = p.get("Type") or p.get("ItemType") or p.get("TypeId") or p.get("Id")
                    if item_id:
                        items.append(item_id)
                elif isinstance(p, str):
                    items.append(p)
            return items[:9]

        k_item_ids = extract_item_ids(killer)
        v_item_ids = extract_item_ids(victim)
        loot_ids = []
        for l in (ev.get("Loot") or victim.get("Inventory") or []):
            if isinstance(l, dict):
                lid = l.get("Type") or l.get("ItemType") or l.get("Id")
                if lid:
                    loot_ids.append(lid)
            elif isinstance(l, str):
                loot_ids.append(l)

        async def fetch_icon(session, item_id: str):
            try:
                # Use Albion render CDN
                url = f"https://render.albiononline.com/v1/item/{quote(item_id)}.png"
                async with session.get(url, timeout=15) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.read()
                    img = Image.open(BytesIO(data)).convert("RGBA")
                    return img
            except Exception:
                return None

        k_icons = []
        v_icons = []
        loot_icons = []

        if render_kill_event is not None:
            async with aiohttp.ClientSession() as session:
                tasks = [fetch_icon(session, iid) for iid in k_item_ids]
                k_icons = await asyncio.gather(*tasks, return_exceptions=True)
                k_icons = [i if isinstance(i, Image.Image) else None for i in k_icons]

                tasks = [fetch_icon(session, iid) for iid in v_item_ids]
                v_icons = await asyncio.gather(*tasks, return_exceptions=True)
                v_icons = [i if isinstance(i, Image.Image) else None for i in v_icons]

                tasks = [fetch_icon(session, iid) for iid in loot_ids[:10]]
                loot_icons = await asyncio.gather(*tasks, return_exceptions=True)
                loot_icons = [i if isinstance(i, Image.Image) else None for i in loot_icons]

            try:
                img_bytes = render_kill_event(ev, ev_type, k_icons=k_icons, v_icons=v_icons, loot_icons=loot_icons)
                file = discord.File(fp=img_bytes, filename="killcard.png")
                embed = discord.Embed(color=color)
                embed.set_image(url="attachment://killcard.png")
                await channel.send(embed=embed, file=file)
                return
            except Exception:
                LOGGER.exception("Error rendering killcard")

        # Fallback if renderer not available or failed
        embed = discord.Embed(title=f"{title}", color=color)
        # Players
        k_name = killer.get("Name") or "Desconocido"
        v_name = victim.get("Name") or "Desconocido"
        embed.add_field(name="Killer", value=k_name, inline=True)
        embed.add_field(name="Victim", value=v_name, inline=True)
        # Fame / silver
        fame = ev.get("KillerFame") or ev.get("VictimFame") or ev.get("Fame") or 0
        silver = ev.get("Silver") or 0
        embed.add_field(name="Fama", value=str(fame), inline=False)
        if silver:
            embed.add_field(name="Silver", value=str(silver), inline=True)
        location = ev.get("Location") or ev.get("Zone") or ev.get("ZoneId") or "-"
        embed.set_footer(text=f"Mapa: {location} ? EventId: {ev.get('EventId') or ev.get('Id')}")
        await channel.send(embed=embed)


class KillboardSetup(commands.GroupCog, group_name="killboard", group_description="Comandos para configurar el killboard"):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="track", description="Trackear kills/deaths de una guild de Albion")
    @app_commands.describe(
        albion_guild_id="ID de la guild en Albion (GuildId)",
        channel_kills="Canal para kills",
        channel_deaths="Canal para deaths (opcional)",
        server="Servidor de Albion: europe, americas, o asia"
    )
    @app_commands.choices(server=[
        app_commands.Choice(name="Europe", value="europe"),
        app_commands.Choice(name="Americas (West)", value="americas"),
        app_commands.Choice(name="Asia (East)", value="asia")
    ])
    async def track(
        self,
        interaction: discord.Interaction,
        albion_guild_id: str,
        channel_kills: discord.TextChannel,
        server: app_commands.Choice[str]=None,
        channel_deaths: discord.TextChannel | None=None
    ):
        server_name = server.value if server else "europe"
        cur = db.cursor
        cur.execute(
            "INSERT OR REPLACE INTO killboard_tracked (guild_id, nombre, channel_kills, channel_deaths, albion_guild_id, server) VALUES (?,?,?,?,?,?)",
            (interaction.guild_id, interaction.guild.name, channel_kills.id, channel_deaths.id if channel_deaths else None, albion_guild_id, server_name),
        )
        db.conn.commit()
        await interaction.response.send_message(f"✅ Killboard configurado para esta guild en servidor **{server_name.upper()}**.", ephemeral=True)

    @app_commands.command(name="deaths", description="Configurar el canal donde se publican las muertes")
    @app_commands.describe(channel="Canal para las muertes de la guild")
    async def deaths(self, interaction: discord.Interaction, channel: discord.TextChannel):
        cur = db.cursor
        cur.execute(
            "UPDATE killboard_tracked SET channel_deaths=? WHERE guild_id=?",
            (channel.id, interaction.guild_id),
        )
        db.conn.commit()

        if cur.rowcount == 0:
            await interaction.response.send_message(
                "Primero configura el killboard con /killboard track.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Las muertes se publicarán en {channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="untrack", description="Dejar de trackear eventos para esta guild")
    async def untrack(self, interaction: discord.Interaction):
        cur = db.cursor
        cur.execute("DELETE FROM killboard_tracked WHERE guild_id=?", (interaction.guild_id,))
        db.conn.commit()
        await interaction.response.send_message("? Killboard desactivado para esta guild.", ephemeral=True)

    @app_commands.command(name="status", description="Mostrar estado del killboard para este servidor")
    async def status(self, interaction: discord.Interaction):
        cur = db.cursor
        cur.execute("SELECT channel_kills, channel_deaths, albion_guild_id, server FROM killboard_tracked WHERE guild_id=?", (interaction.guild_id,))
        row = cur.fetchone()
        if not row:
            await interaction.response.send_message("❌ No hay killboard configurado para este servidor.", ephemeral=True)
            return

        channel_kills, channel_deaths, albion_guild_id = row[0], row[1], row[2]
        server = row[3] if len(row) > 3 else "europe"
        text = f"Guild Albion ID: {albion_guild_id}\nServidor: **{server.upper()}**\nCanal kills: {channel_kills}\nCanal deaths: {channel_deaths}"
        killboard = self.bot.get_cog("Killboard")
        if killboard and killboard.last_poll_at:
            checked_at = killboard.last_poll_at.strftime("%H:%M:%S UTC")
            text += (
                f"\n\nUltima consulta: {checked_at}"
                f"\nEventos recibidos: {killboard.last_event_count}"
                f"\nEventos de esta guild: {killboard.last_matching_events}"
            )
        else:
            text += "\n\nEl killboard aun no ha completado su primera consulta."
        await interaction.response.send_message(text, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Killboard(bot))
    await bot.add_cog(KillboardSetup(bot))
