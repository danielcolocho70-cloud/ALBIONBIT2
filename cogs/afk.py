import discord
from discord import app_commands
from discord.ext import commands

from services.afk_service import AfkService


AFK_GUILD_ID = 1548935954495053854
AUTHORIZED_ROLE_NAMES = frozenset({"moderador", "staff", "reclutador"})


@app_commands.guilds(discord.Object(id=AFK_GUILD_ID))
class Afk(commands.GroupCog, group_name="afk", group_description="Registro privado de jugadores AFK"):
    """Comandos AFK limitados al canal y personal autorizados."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = AfkService()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != AFK_GUILD_ID:
            await interaction.response.send_message(
                "❌ Este comando solo se puede usar en el servidor configurado.",
                ephemeral=True,
            )
            return False

        member = interaction.user
        role_names = {
            role.name.strip().casefold()
            for role in getattr(member, "roles", [])
        }
        is_administrator = getattr(member, "guild_permissions", None) and member.guild_permissions.administrator
        if not is_administrator and not role_names.intersection(AUTHORIZED_ROLE_NAMES):
            await interaction.response.send_message(
                "❌ Solo Moderador, Staff, Reclutador o un administrador pueden usar el registro AFK.",
                ephemeral=True,
            )
            return False
        return True

    @app_commands.command(name="añadir", description="Registrar que un miembro estará AFK.")
    @app_commands.describe(usuario="Miembro que estará desconectado", motivo="Motivo o nota del AFK")
    async def anadir(self, interaction: discord.Interaction, usuario: discord.Member, motivo: str):
        motivo = motivo.strip()
        if not motivo:
            await interaction.response.send_message("❌ Indica un motivo o una nota para el AFK.", ephemeral=True)
            return

        self.service.establecer_afk(
            interaction.guild_id,
            usuario.id,
            usuario.display_name,
            motivo,
            interaction.user.id,
        )
        await interaction.response.send_message(
            f"✅ Se registró a {usuario.mention} como **AFK**.\n**Nota:** {motivo}",
            ephemeral=True,
        )

    @app_commands.command(name="mirar", description="Ver los miembros que siguen registrados como AFK.")
    async def mirar(self, interaction: discord.Interaction):
        records = self.service.obtener_afk_activos(interaction.guild_id)
        if not records:
            await interaction.response.send_message("✅ No hay miembros registrados como AFK.")
            return

        lines = [f"• <@{record['user_id']}> — {record['reason']}" for record in records]
        embed = discord.Embed(
            title="📴 Miembros AFK",
            description="\n".join(lines),
            color=0xF39C12,
        )
        embed.set_footer(text=f"Total: {len(records)}")
        # La lista es pública para que el servidor conozca las ausencias.
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="editar", description="Cambiar el estado AFK o la nota de un miembro.")
    @app_commands.describe(
        usuario="Miembro cuyo registro se editará",
        estado="AFK para marcarlo ausente; activo para retirarlo de la lista",
        motivo="Nueva nota opcional",
    )
    @app_commands.choices(estado=[
        app_commands.Choice(name="AFK", value="afk"),
        app_commands.Choice(name="Activo / ya no AFK", value="activo"),
    ])
    async def editar(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        estado: app_commands.Choice[str],
        motivo: str | None = None,
    ):
        is_afk = estado.value == "afk"
        updated = self.service.editar_estado(
            interaction.guild_id,
            usuario.id,
            usuario.display_name,
            is_afk,
            interaction.user.id,
            motivo,
        )
        if not updated:
            await interaction.response.send_message(
                f"❌ {usuario.mention} no tiene un registro AFK que editar.",
                ephemeral=True,
            )
            return

        label = "AFK" if is_afk else "activo / ya no AFK"
        await interaction.response.send_message(
            f"✅ Estado de {usuario.mention} actualizado a **{label}**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Afk(bot))
