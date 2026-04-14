import re
import discord
from discord.ext import commands
import anthropic
import database as db
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, ARIA_HISTORY_LIMIT

# Ключові слова, що перехоплює inventory.py — ARIA не відповідає на них
INVENTORY_KEYWORDS = [
    "додай до мого складу",
    "додай до корп",
    "додай до корпоратив",
    "покажи мій склад",
    "мій склад",
    "корп склад",
    "корпоративний склад",
]

ARIA_SYSTEM_PROMPT = """Ти — ARIA (Automated Response & Intelligence Assistant), бортовий AI корпорації в всесвіті Star Citizen.

Твій стиль:
- Професійний, лаконічний, як бортовий комп'ютер зоряного корабля
- Говориш українською
- Іноді додаєш атмосферні фрази зі всесвіту SC ("Канали зв'язку відкриті", "Дані отримано", "Навігаційний розрахунок завершено")
- Ніколи не кажеш "я не можу" — знаходиш рішення або запитуєш уточнення
- Коротко та по суті, без зайвих слів

Твоя роль:
- Допомагати організації SC з плануванням місій, логістикою та управлінням ресурсами
- Знати поточні статуси гравців, склади, активні місії
- Пропонувати оптимальні склади команди для місій
- Відповідати на питання про гру та організацію

Формат відповідей в Discord:
- Використовуй **bold** для важливих даних
- Використовуй `code` для назв локацій, кораблів, товарів
- Списки через • або нумеровані

{context}"""


async def build_context(guild: discord.Guild | None = None) -> str:
    """Збираємо актуальний контекст організації для system prompt."""
    lines = ["═══ КОНТЕКСТ ОРГАНІЗАЦІЇ ═══"]

    # Онлайн гравці
    players = await db.get_all_online_players()
    if players:
        lines.append(f"\n🟢 ОНЛАЙН ({len(players)} пілотів):")
        for p in players:
            loc = f" @ {p['location']}" if p.get("location") else ""
            lines.append(f"  • {p['username']} — {p['activity']}{loc}")
    else:
        lines.append("\n💤 Всі пілоти офлайн")

    # Активні місії
    missions = await db.get_active_missions()
    if missions:
        lines.append(f"\n🎯 АКТИВНІ МІСІЇ ({len(missions)}):")
        for m in missions:
            lines.append(f"  • #{m['id']} {m['name']} [{m['status']}]"
                         + (f" — старт: {m['start_time']}" if m.get("start_time") else ""))
            for role in m.get("roles", []):
                parts = [p["name"] for p in role.get("participants", [])]
                lines.append(f"    └ {role['role_name']}: {role['slots_filled']}/{role['slots_total']}"
                             + (f" ({', '.join(parts)})" if parts else ""))

    # Корп склад (перші 20 позицій)
    corp_items = await db.get_corp_inventory()
    if corp_items:
        lines.append(f"\n📦 КОРП СКЛАД ({len(corp_items)} позицій):")
        for item in corp_items[:20]:
            qty = int(item["quantity"]) if item["quantity"] == int(item["quantity"]) else item["quantity"]
            lines.append(f"  • {qty}x {item['item_name']} @ {item['location']}")
        if len(corp_items) > 20:
            lines.append(f"  ... і ще {len(corp_items) - 20} позицій")

    lines.append("\n═══════════════════════════")
    return "\n".join(lines)


class ARIACog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if self.bot.user not in message.mentions:
            return

        content = message.content.replace(f"<@{self.bot.user.id}>", "").replace(
            f"<@!{self.bot.user.id}>", ""
        ).strip()

        if not content:
            return

        # Пропускаємо якщо inventory.py вже обробить
        lower = content.lower()
        for kw in INVENTORY_KEYWORDS:
            if kw in lower:
                return

        async with message.channel.typing():
            discord_id = str(message.author.id)
            username = message.author.display_name

            # Зберігаємо повідомлення користувача
            await db.append_aria_history(discord_id, "user", content, ARIA_HISTORY_LIMIT)

            # Отримуємо history
            history = await db.get_aria_history(discord_id, ARIA_HISTORY_LIMIT)

            # Будуємо контекст
            context = await build_context(message.guild)
            system = ARIA_SYSTEM_PROMPT.format(context=context)

            # Виклик Claude API
            try:
                response = self.client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=1024,
                    system=system,
                    messages=[
                        {"role": h["role"], "content": h["content"]}
                        for h in history
                    ],
                )
                reply_text = response.content[0].text
            except anthropic.APIError as e:
                reply_text = f"⚠️ Помилка зв'язку з ARIA: `{e}`"

            # Зберігаємо відповідь
            await db.append_aria_history(discord_id, "assistant", reply_text, ARIA_HISTORY_LIMIT)

            # Відповідаємо в Discord (обрізаємо якщо >2000 символів)
            if len(reply_text) > 2000:
                # розбиваємо на частини
                chunks = [reply_text[i:i+1990] for i in range(0, len(reply_text), 1990)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await message.reply(chunk)
                    else:
                        await message.channel.send(chunk)
            else:
                await message.reply(reply_text)

    # ─── !aria reset — скинути history ────────────────────────────────────

    @commands.command(name="aria")
    async def aria_cmd(self, ctx: commands.Context, subcommand: str = ""):
        if subcommand.lower() == "reset":
            async with __import__("aiosqlite").connect(__import__("config").DATABASE_PATH) as dbc:
                await dbc.execute(
                    "DELETE FROM aria_history WHERE discord_id=?", (str(ctx.author.id),)
                )
                await dbc.commit()
            await ctx.reply("🔄 Пам'ять ARIA для тебе очищена.", delete_after=10)
        else:
            await ctx.reply(
                "**ARIA команди:**\n"
                "`!aria reset` — очистити мою пам'ять\n"
                "`@ARIA <питання>` — вільний чат",
                delete_after=15,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ARIACog(bot))
