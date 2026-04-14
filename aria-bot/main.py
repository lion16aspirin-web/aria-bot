import asyncio
import discord
from discord.ext import commands
import database as db
from config import DISCORD_TOKEN, COMMAND_PREFIX

# ─── Intents ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

# ─── Bot ──────────────────────────────────────────────────────────────────────
bot = commands.Bot(
    command_prefix=COMMAND_PREFIX,
    intents=intents,
    help_command=commands.DefaultHelpCommand(),
)

COGS = [
    "modules.status",
    "modules.inventory",   # inventory перед aria — щоб першим перехоплював складові команди
    "modules.intel",       # intel перед aria — перехоплює ціна/маршрут до Claude
    "modules.aria",
    "modules.missions",
]


@bot.event
async def on_ready():
    print(f"✅ ARIA online — {bot.user} (ID: {bot.user.id})")
    print(f"   Серверів: {len(bot.guilds)}")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(f"⚠️ Відсутній аргумент: `{error.param.name}`\n"
                        f"Використай `!help {ctx.command}` для довідки.", delete_after=15)
    else:
        await ctx.reply(f"⚠️ Помилка: `{error}`", delete_after=15)
        raise error


async def main():
    async with bot:
        # Ініціалізуємо БД
        await db.init_db()
        print("✅ База даних ініціалізована")

        # Завантажуємо модулі
        for cog in COGS:
            await bot.load_extension(cog)
            print(f"   ✓ {cog}")

        if not DISCORD_TOKEN:
            print("❌ DISCORD_TOKEN не встановлено! Перевір .env файл")
            return

        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
