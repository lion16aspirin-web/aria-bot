import discord
from discord.ext import commands, tasks
import json
from datetime import datetime, timezone
import database as db
from utils.formatters import mission_embed
from config import MISSIONS_CHANNEL_NAME


# ─── UI Views ─────────────────────────────────────────────────────────────────

class RoleButton(discord.ui.Button):
    def __init__(self, mission_id: int, role_name: str, slots_filled: int, slots_total: int):
        filled = slots_filled >= slots_total
        super().__init__(
            label=f"{role_name} ({slots_filled}/{slots_total})",
            style=discord.ButtonStyle.danger if filled else discord.ButtonStyle.primary,
            custom_id=f"role_{mission_id}_{role_name}",
            disabled=filled,
        )
        self.mission_id = mission_id
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):
        ok, msg = await db.join_mission_role(
            self.mission_id, self.role_name,
            str(interaction.user.id), interaction.user.display_name
        )
        if not ok:
            await interaction.response.send_message(f"⚠️ {msg}", ephemeral=True)
            return
        mission = await db.get_mission(self.mission_id)
        embed = mission_embed(mission)
        view = MissionView(mission)
        await interaction.response.edit_message(embed=embed, view=view)


class LeaveButton(discord.ui.Button):
    def __init__(self, mission_id: int):
        super().__init__(
            label="Покинути місію",
            style=discord.ButtonStyle.secondary,
            custom_id=f"leave_{mission_id}",
        )
        self.mission_id = mission_id

    async def callback(self, interaction: discord.Interaction):
        mission = await db.get_mission(self.mission_id)
        if not mission:
            await interaction.response.send_message("Місія не знайдена", ephemeral=True)
            return
        removed = False
        for role in mission.get("roles", []):
            ok, _ = await db.leave_mission_role(
                self.mission_id, role["role_name"], str(interaction.user.id)
            )
            if ok:
                removed = True
                break
        if not removed:
            await interaction.response.send_message("⚠️ Тебе немає ні в одній ролі.", ephemeral=True)
            return
        mission = await db.get_mission(self.mission_id)
        embed = mission_embed(mission)
        view = MissionView(mission)
        await interaction.response.edit_message(embed=embed, view=view)


class MissionView(discord.ui.View):
    def __init__(self, mission: dict):
        super().__init__(timeout=None)
        for role in mission.get("roles", []):
            self.add_item(RoleButton(
                mission["id"],
                role["role_name"],
                role["slots_filled"],
                role["slots_total"],
            ))
        self.add_item(LeaveButton(mission["id"]))


# ─── Cog ──────────────────────────────────────────────────────────────────────

class MissionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    # ─── !місія створити ──────────────────────────────────────────────────

    @commands.group(name="місія", invoke_without_command=True)
    async def mission_group(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @mission_group.command(name="створити")
    async def create_mission(self, ctx: commands.Context, *, name: str):
        """
        !місія створити <назва>
        Після цього бот запитає локацію, час та ролі.
        """
        mission_id = await db.create_mission(name, str(ctx.author.id))

        # дефолтні ролі (можна розширити через !місія роль додати)
        default_roles = [
            ("Пілот", 2),
            ("Стрілець", 3),
            ("Медик", 1),
        ]
        for role_name, slots in default_roles:
            await db.add_mission_role(mission_id, role_name, slots)

        mission = await db.get_mission(mission_id)
        embed = mission_embed(mission)
        view = MissionView(mission)

        # надсилаємо в канал місій або поточний
        channel = discord.utils.get(ctx.guild.text_channels, name=MISSIONS_CHANNEL_NAME) or ctx.channel
        msg = await channel.send(embed=embed, view=view)
        await db.update_mission_message(mission_id, str(msg.id), str(channel.id))
        await ctx.reply(f"✅ Місію **{name}** створено (ID: `{mission_id}`)", delete_after=10)

    @mission_group.command(name="роль")
    async def add_role(self, ctx: commands.Context, mission_id: int, role_name: str, slots: int = 1):
        """
        !місія роль <id> <назва> [кількість слотів]
        Додає нову роль до місії.
        """
        await db.add_mission_role(mission_id, role_name, slots)
        await self._refresh_mission_message(mission_id)
        await ctx.reply(f"✅ Роль **{role_name}** ({slots} слотів) додана до місії `{mission_id}`",
                        delete_after=10)

    @mission_group.command(name="час")
    async def set_time(self, ctx: commands.Context, mission_id: int, *, time_str: str):
        """
        !місія час <id> <час>
        Встановлює час старту місії (довільний рядок, напр. "2024-12-01 20:00 UTC").
        """
        async with __import__("aiosqlite").connect(__import__("config").DATABASE_PATH) as dbc:
            await dbc.execute(
                "UPDATE missions SET start_time=? WHERE id=?", (time_str, mission_id)
            )
            await dbc.commit()
        await self._refresh_mission_message(mission_id)
        await ctx.reply(f"⏰ Час старту місії `{mission_id}` встановлено: **{time_str}**",
                        delete_after=10)

    @mission_group.command(name="старт")
    async def start_mission(self, ctx: commands.Context, mission_id: int):
        """!місія старт <id> — розпочати місію."""
        await db.set_mission_status(mission_id, "active")
        mission = await db.get_mission(mission_id)
        if not mission:
            await ctx.reply("Місія не знайдена", delete_after=10)
            return
        # оновлюємо статуси учасників
        for role in mission.get("roles", []):
            for p in role.get("participants", []):
                await db.upsert_player(
                    discord_id=p["id"],
                    username=p["name"],
                    status="онлайн",
                    activity="місія",
                    location=mission.get("location", ""),
                )
        await self._refresh_mission_message(mission_id)
        await ctx.reply(f"🚀 Місія **{mission['name']}** розпочата!", delete_after=10)

    @mission_group.command(name="завершити")
    async def finish_mission(self, ctx: commands.Context, mission_id: int):
        """!місія завершити <id>"""
        await db.set_mission_status(mission_id, "done")
        await self._refresh_mission_message(mission_id)
        await ctx.reply(f"✅ Місія `{mission_id}` завершена.", delete_after=10)

    @mission_group.command(name="список")
    async def list_missions(self, ctx: commands.Context):
        """!місія список — активні місії."""
        missions = await db.get_active_missions()
        if not missions:
            await ctx.reply("Немає активних місій.", delete_after=15)
            return
        lines = []
        for m in missions:
            lines.append(f"**#{m['id']}** — {m['name']} `[{m['status']}]`"
                         + (f" | ⏰ {m['start_time']}" if m.get("start_time") else ""))
        await ctx.reply("\n".join(lines), delete_after=30)

    # ─── Refresh embed ────────────────────────────────────────────────────

    async def _refresh_mission_message(self, mission_id: int):
        mission = await db.get_mission(mission_id)
        if not mission or not mission.get("message_id"):
            return
        try:
            channel = self.bot.get_channel(int(mission["channel_id"]))
            if not channel:
                return
            msg = await channel.fetch_message(int(mission["message_id"]))
            embed = mission_embed(mission)
            view = MissionView(mission)
            await msg.edit(embed=embed, view=view)
        except discord.NotFound:
            pass

    # ─── Нагадування за 1 год до старту ──────────────────────────────────

    @tasks.loop(minutes=5)
    async def reminder_loop(self):
        missions = await db.get_active_missions()
        now = datetime.now(timezone.utc)
        for m in missions:
            if m["status"] != "planning" or not m.get("start_time"):
                continue
            try:
                start = datetime.fromisoformat(m["start_time"])
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                delta = (start - now).total_seconds()
                # нагадування між 55 і 65 хвилинами до старту
                if 55 * 60 <= delta <= 65 * 60:
                    channel = self.bot.get_channel(int(m["channel_id"])) if m.get("channel_id") else None
                    if channel:
                        await channel.send(
                            f"⏰ **Нагадування!** Місія **{m['name']}** розпочнеться через ~1 годину.",
                            reference=await channel.fetch_message(int(m["message_id"]))
                            if m.get("message_id") else None,
                        )
            except (ValueError, TypeError):
                pass

    @reminder_loop.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(MissionsCog(bot))
