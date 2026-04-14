"""
modules/intel.py — Фаза 3
UEX Corp API (uexcorp.space/api/2.0) для актуальних цін і торгових маршрутів SC.

Команди:
  !ціна <товар> [локація]
  !маршрут [бюджет] [корабель]
  !термінали [фільтр]

@ARIA ціна золото Microtech
@ARIA маршрут бюджет 50k Cutlass Black
"""

import re
import time
import discord
from discord.ext import commands
import aiohttp
from config import UEX_API_KEY

UEX_BASE = "https://uexcorp.space/api/2.0"
HEADERS = {"api_key": UEX_API_KEY} if UEX_API_KEY else {}

# Простий in-memory кеш: {cache_key: (timestamp, data)}
_CACHE: dict[str, tuple[float, any]] = {}
CACHE_TTL = 300  # 5 хвилин


async def _get(session: aiohttp.ClientSession, path: str, params: dict | None = None) -> dict | list | None:
    """GET запит до UEX API з кешуванням."""
    cache_key = path + str(sorted((params or {}).items()))
    now = time.monotonic()
    if cache_key in _CACHE:
        ts, data = _CACHE[cache_key]
        if now - ts < CACHE_TTL:
            return data

    url = f"{UEX_BASE}{path}"
    try:
        async with session.get(url, params=params, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            payload = await resp.json()
            # UEX API повертає {"status":"ok","data":[...]} або {"status":"ok","data":{...}}
            data = payload.get("data") if isinstance(payload, dict) else payload
            _CACHE[cache_key] = (now, data)
            return data
    except Exception:
        return None


def _fmt_credits(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f} aUEC"


def _parse_budget(text: str) -> int | None:
    """Парсить "50k", "50000", "50К" → int."""
    text = text.strip().lower().replace("к", "k").replace(" ", "")
    m = re.match(r"^(\d+(?:\.\d+)?)(k?)$", text)
    if not m:
        return None
    val = float(m.group(1))
    if m.group(2) == "k":
        val *= 1000
    return int(val)


# ─── Embed builders ───────────────────────────────────────────────────────────

def _price_embed(commodity_name: str, prices: list[dict], location_filter: str = "") -> discord.Embed:
    embed = discord.Embed(
        title=f"📊 Ціни: {commodity_name.title()}",
        color=discord.Color.gold(),
    )
    if location_filter:
        embed.description = f"Фільтр локації: `{location_filter}`"

    if not prices:
        embed.description = "⚠️ Дані не знайдено. Перевір назву товару або локації."
        return embed

    buy_rows = [p for p in prices if p.get("price_buy") and p.get("price_buy", 0) > 0]
    sell_rows = [p for p in prices if p.get("price_sell") and p.get("price_sell", 0) > 0]

    if buy_rows:
        buy_rows.sort(key=lambda x: x.get("price_buy", 0))
        lines = []
        for p in buy_rows[:8]:
            terminal = p.get("terminal_name") or p.get("name", "?")
            lines.append(f"`{_fmt_credits(p['price_buy'])}` — {terminal}")
        embed.add_field(name="🛒 Купити (найдешевше)", value="\n".join(lines), inline=False)

    if sell_rows:
        sell_rows.sort(key=lambda x: x.get("price_sell", 0), reverse=True)
        lines = []
        for p in sell_rows[:8]:
            terminal = p.get("terminal_name") or p.get("name", "?")
            lines.append(f"`{_fmt_credits(p['price_sell'])}` — {terminal}")
        embed.add_field(name="💰 Продати (найвигідніше)", value="\n".join(lines), inline=False)

    embed.set_footer(text="Дані: UEX Corp • оновлюється кожні 5 хв")
    return embed


def _route_embed(routes: list[dict], budget: int | None, ship: str) -> discord.Embed:
    embed = discord.Embed(
        title="🗺️ Торгові маршрути",
        color=discord.Color.green(),
    )
    details = []
    if budget:
        details.append(f"Бюджет: `{_fmt_credits(budget)}`")
    if ship:
        details.append(f"Корабель: `{ship}`")
    if details:
        embed.description = " | ".join(details)

    if not routes:
        embed.description = (embed.description or "") + "\n⚠️ Маршрути не знайдено."
        return embed

    for i, r in enumerate(routes[:6], 1):
        origin = r.get("origin_terminal_name") or r.get("terminal_origin_name", "?")
        dest = r.get("destination_terminal_name") or r.get("terminal_destination_name", "?")
        commodity = r.get("commodity_name", "?")
        profit = r.get("profit_total") or r.get("profit", 0)
        profit_per_scu = r.get("profit_per_scu") or r.get("profit_unit", 0)
        qty = r.get("quantity_scu") or r.get("scu", 0)

        value_lines = [
            f"**{origin}** → **{dest}**",
            f"Товар: `{commodity}` | {qty} SCU",
            f"Прибуток: `{_fmt_credits(profit)}` ({_fmt_credits(profit_per_scu)}/SCU)",
        ]
        embed.add_field(name=f"#{i}", value="\n".join(value_lines), inline=False)

    embed.set_footer(text="Дані: UEX Corp • оновлюється кожні 5 хв")
    return embed


# ─── Cog ──────────────────────────────────────────────────────────────────────

class IntelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self._session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self._session:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # ─── on_message — перехоплюємо @ARIA ціна / маршрут ──────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if self.bot.user not in message.mentions:
            return

        content = message.content.replace(f"<@{self.bot.user.id}>", "").replace(
            f"<@!{self.bot.user.id}>", ""
        ).strip()
        lower = content.lower()

        # @ARIA ціна <товар> [локація]
        if lower.startswith("ціна") or lower.startswith("price"):
            parts = content.split(maxsplit=1)
            rest = parts[1] if len(parts) > 1 else ""
            # розбиваємо на товар і локацію (через "на", "in", "at", "@")
            loc_match = re.split(r"\s+(?:на|in|at|@)\s+", rest, maxsplit=1, flags=re.IGNORECASE)
            commodity = loc_match[0].strip()
            location = loc_match[1].strip() if len(loc_match) > 1 else ""
            await self._do_price(message, commodity, location)
            return

        # @ARIA маршрут [бюджет X] [корабель Y]
        if lower.startswith("маршрут") or lower.startswith("route") or lower.startswith("торгівля"):
            budget_match = re.search(r"бюджет\s+(\S+)", content, re.IGNORECASE)
            budget = _parse_budget(budget_match.group(1)) if budget_match else None

            ship_match = re.search(r"(?:корабель|ship|на)\s+(.+?)(?:\s+бюджет|$)", content, re.IGNORECASE)
            ship = ship_match.group(1).strip() if ship_match else ""

            await self._do_routes(message, budget, ship)
            return

        # @ARIA порівняй <ship1> і <ship2>  — поки відповідь через ARIA/Claude
        # intel.py не перехоплює — нехай обробляє aria.py

    # ─── !ціна ────────────────────────────────────────────────────────────

    @commands.command(name="ціна")
    async def price_cmd(self, ctx: commands.Context, commodity: str, *, location: str = ""):
        await self._do_price(ctx, commodity, location)

    async def _do_price(self, ctx_or_msg, commodity: str, location: str):
        is_msg = isinstance(ctx_or_msg, discord.Message)
        reply = ctx_or_msg.reply if is_msg else ctx_or_msg.reply

        async with (ctx_or_msg.channel if is_msg else ctx_or_msg).typing():
            # шукаємо commodity_id за назвою
            commodities = await _get(self.session, "/commodities")
            commodity_id = None
            if commodities:
                for c in commodities:
                    if commodity.lower() in c.get("name", "").lower():
                        commodity_id = c.get("id")
                        commodity = c.get("name", commodity)
                        break

            params = {}
            if commodity_id:
                params["id_commodity"] = commodity_id

            prices = await _get(self.session, "/commodities_prices", params or None)

            # фільтруємо по локації якщо вказана
            if prices and location:
                filtered = [
                    p for p in prices
                    if location.lower() in (p.get("terminal_name") or p.get("name", "")).lower()
                ]
                prices = filtered if filtered else prices

            embed = _price_embed(commodity, prices or [], location)
            await reply(embed=embed)

    # ─── !маршрут ─────────────────────────────────────────────────────────

    @commands.command(name="маршрут")
    async def route_cmd(self, ctx: commands.Context, budget: str = "", *, ship: str = ""):
        budget_val = _parse_budget(budget) if budget else None
        await self._do_routes(ctx, budget_val, ship)

    async def _do_routes(self, ctx_or_msg, budget: int | None, ship: str):
        is_msg = isinstance(ctx_or_msg, discord.Message)
        reply = ctx_or_msg.reply if is_msg else ctx_or_msg.reply

        async with (ctx_or_msg.channel if is_msg else ctx_or_msg).typing():
            params: dict = {}
            if budget:
                params["money_available"] = budget

            # шукаємо id корабля
            if ship:
                ships = await _get(self.session, "/ships")
                if ships:
                    for s in ships:
                        if ship.lower() in s.get("name", "").lower():
                            params["id_ship"] = s.get("id")
                            ship = s.get("name", ship)
                            break

            routes = await _get(self.session, "/trade_routes", params or None)
            embed = _route_embed(routes or [], budget, ship)
            await reply(embed=embed)

    # ─── !термінали ───────────────────────────────────────────────────────

    @commands.command(name="термінали")
    async def terminals_cmd(self, ctx: commands.Context, *, search: str = ""):
        """!термінали [пошук] — список торгових терміналів."""
        async with ctx.typing():
            terminals = await _get(self.session, "/terminals")
            if not terminals:
                await ctx.reply("⚠️ Не вдалося отримати список терміналів.", delete_after=15)
                return

            if search:
                terminals = [t for t in terminals if search.lower() in t.get("name", "").lower()]

            embed = discord.Embed(
                title="🏪 Торгові термінали",
                color=discord.Color.blurple(),
            )
            if not terminals:
                embed.description = f"Нічого не знайдено для `{search}`"
            else:
                lines = [f"• {t.get('name', '?')}" for t in terminals[:25]]
                if len(terminals) > 25:
                    lines.append(f"... і ще {len(terminals) - 25}")
                embed.description = "\n".join(lines)
            embed.set_footer(text="Дані: UEX Corp")
            await ctx.reply(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(IntelCog(bot))
