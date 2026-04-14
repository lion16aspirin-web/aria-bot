import discord
from discord.ext import commands
import database as db
from utils.formatters import status_embed
from config import STATUS_CHANNEL_NAME

VALID_ACTIVITIES = {
    "торгівля", "mining", "pvp", "patrol", "bounty", "salvage", "explore", "офлайн"
}


class StatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # message_id поточного статус-повідомлення в #org-статус
        self._status_message_id: int | None = None

    # ─── Команда !статус ───────────────────────────────────────────────────

    @commands.command(name="статус")
    async def set_status(self, ctx: commands.Context, activity: str = "", *, location: str = ""):
        """
        !статус <тип> [локація]
        Типи: торгівля, mining, pvp, patrol, bounty, salvage, explore, офлайн
        """
        activity = activity.lower().strip()

        if not activity or activity not in VALID_ACTIVITIES:
            valid = ", ".join(sorted(VALID_ACTIVITIES))
            await ctx.reply(
                f"⚠️ Невірний тип активності.\nДоступні: `{valid}`\n"
                f"Приклад: `!статус торгівля Microtech→ArcCorp`",
                delete_after=15,
            )
            return

        if activity == "офлайн":
            await db.set_player_offline(str(ctx.author.id))
            await ctx.reply("💤 Статус оновлено: офлайн", delete_after=10)
        else:
            await db.upsert_player(
                discord_id=str(ctx.author.id),
                username=ctx.author.display_name,
                status="онлайн",
                location=location.strip(),
                activity=activity,
            )
            loc_str = f" — {location}" if location else ""
            await ctx.reply(f"✅ Статус: **{activity}**{loc_str}", delete_after=10)

        await self._refresh_status_board(ctx.guild)

    # ─── Команда !статуси ──────────────────────────────────────────────────

    @commands.command(name="статуси")
    async def show_statuses(self, ctx: commands.Context):
        """Показати поточний статус всіх онлайн гравців."""
        players = await db.get_all_online_players()
        embed = status_embed(players)
        await ctx.send(embed=embed)

    # ─── Оновлення дошки в #org-статус ────────────────────────────────────

    async def _refresh_status_board(self, guild: discord.Guild | None):
        if not guild:
            return
        channel = discord.utils.get(guild.text_channels, name=STATUS_CHANNEL_NAME)
        if not channel:
            return

        players = await db.get_all_online_players()
        embed = status_embed(players)

        if self._status_message_id:
            try:
                msg = await channel.fetch_message(self._status_message_id)
                await msg.edit(embed=embed)
                return
            except discord.NotFound:
                self._status_message_id = None

        msg = await channel.send(embed=embed)
        self._status_message_id = msg.id

    # ─── Discord events ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Скидаємо статус коли гравець переходить в офлайн."""
        was_online = before.status != discord.Status.offline
        now_offline = after.status == discord.Status.offline
        if was_online and now_offline:
            await db.set_player_offline(str(after.id))
            await self._refresh_status_board(after.guild)

    @commands.Cog.listener()
    async def on_ready(self):
        """Шукаємо попереднє статус-повідомлення при рестарті."""
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=STATUS_CHANNEL_NAME)
            if channel:
                # беремо останнє повідомлення від бота
                async for msg in channel.history(limit=20):
                    if msg.author == self.bot.user and msg.embeds:
                        self._status_message_id = msg.id
                        break


async def setup(bot: commands.Bot):
    await bot.add_cog(StatusCog(bot))
