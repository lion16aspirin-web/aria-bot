import re
import discord
from discord.ext import commands
import database as db
from utils.formatters import inventory_embed


# ─── Парсер позицій ───────────────────────────────────────────────────────────

def parse_items(text: str) -> list[dict]:
    """
    Парсить рядок з позиціями:
      "50 медпаків, 2 Rifle AR-55, 1000 hydrogen fuel"
    Повертає список {"name": str, "quantity": float}
    """
    items = []
    # розбиваємо по комах або крапці з комою
    parts = re.split(r"[,;]+", text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # кількість на початку: "50 медпаків", "2.5 gold"
        m = re.match(r"^(\d+(?:[.,]\d+)?)\s+(.+)$", part)
        if m:
            qty_str = m.group(1).replace(",", ".")
            name = m.group(2).strip()
            try:
                qty = float(qty_str)
            except ValueError:
                qty = 1.0
        else:
            # без кількості — вважаємо 1
            name = part
            qty = 1.0
        if name:
            items.append({"name": name, "quantity": qty})
    return items


# ─── Cog ──────────────────────────────────────────────────────────────────────

class InventoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Обробляємо mention @ARIA + ключові слова
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if self.bot.user not in message.mentions:
            return

        content = message.content
        # видаляємо mention
        content = content.replace(f"<@{self.bot.user.id}>", "").replace(
            f"<@!{self.bot.user.id}>", ""
        ).strip()

        lower = content.lower()

        # ─ додай до мого складу ─
        if "додай до мого складу" in lower or "добавь в мой склад" in lower:
            await self._handle_add(message, content, owner_type="personal",
                                   owner_id=str(message.author.id))
            return

        # ─ додай до корп складу ─
        if "додай до корп" in lower or "додай до корпоратив" in lower:
            await self._handle_add(message, content, owner_type="corp",
                                   owner_id="corp")
            return

        # ─ покажи мій склад ─
        if "покажи мій склад" in lower or "мій склад" in lower:
            items = await db.get_inventory(str(message.author.id), "personal")
            embed = inventory_embed(items, f"Склад {message.author.display_name}")
            await message.reply(embed=embed)
            return

        # ─ корп склад ─
        if "корп склад" in lower or "корпоративний склад" in lower:
            items = await db.get_corp_inventory()
            embed = inventory_embed(items, "Корпоративний склад")
            await message.reply(embed=embed)
            return

    async def _handle_add(self, message: discord.Message, content: str,
                           owner_type: str, owner_id: str):
        """Парсить команду додавання і зберігає в БД."""
        # шукаємо ": <позиції>" і "локація: <назва>"
        # формат: "додай до мого складу: 50 медпаків, 2 Rifle\nлокація: Lorville"
        location = ""
        loc_match = re.search(r"(?:локація|location)\s*:\s*(.+?)(?:\n|$)", content, re.IGNORECASE)
        if loc_match:
            location = loc_match.group(1).strip()
            content = content[:loc_match.start()].strip()

        # витягуємо частину після двокрапки
        items_text = ""
        colon_idx = content.find(":")
        if colon_idx != -1:
            items_text = content[colon_idx + 1:].strip()

        if not items_text:
            await message.reply(
                "⚠️ Вкажи позиції після двокрапки.\n"
                "Приклад: `@ARIA додай до мого складу: 50 медпаків, 2 Rifle AR-55\nлокація: Lorville`",
                ephemeral=False,
            )
            return

        items = parse_items(items_text)
        if not items:
            await message.reply("⚠️ Не вдалося розпізнати позиції.", ephemeral=False)
            return

        await db.add_inventory_items(owner_id, owner_type, items, location)

        lines = [f"• `{i['quantity']:.0f}x` {i['name']}" for i in items]
        loc_str = f"\n📍 Локація: **{location}**" if location else ""
        kind = "особистий" if owner_type == "personal" else "корпоративний"
        await message.reply(
            f"✅ Додано до {kind} складу:{loc_str}\n" + "\n".join(lines)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCog(bot))
