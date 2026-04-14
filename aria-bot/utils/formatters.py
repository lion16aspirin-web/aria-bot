import discord
from datetime import datetime

# Емодзі для типів активності
ACTIVITY_EMOJI = {
    "торгівля": "📦",
    "mining":   "⛏️",
    "pvp":      "⚔️",
    "patrol":   "🛡️",
    "bounty":   "🎯",
    "salvage":  "🔧",
    "explore":  "🔭",
    "offline":  "💤",
    "офлайн":   "💤",
}

STATUS_COLOR = {
    "торгівля": discord.Color.gold(),
    "mining":   discord.Color.dark_gold(),
    "pvp":      discord.Color.red(),
    "patrol":   discord.Color.blue(),
    "офлайн":   discord.Color.grayed_out(),
}

MISSION_STATUS_EMOJI = {
    "planning": "📋",
    "active":   "🚀",
    "done":     "✅",
    "cancelled":"❌",
}


def status_embed(players: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title="🛸 ARIA — Статус організації",
        color=discord.Color.blurple(),
        timestamp=datetime.utcnow(),
    )
    if not players:
        embed.description = "*Всі пілоти офлайн. Тиша у Всесвіті.*"
        return embed

    by_activity: dict[str, list[str]] = {}
    for p in players:
        act = p.get("activity", "").lower() or "інше"
        emoji = ACTIVITY_EMOJI.get(act, "🔹")
        loc = p.get("location", "")
        line = f"`{p['username']}`"
        if loc:
            line += f" — {loc}"
        by_activity.setdefault(f"{emoji} {act.capitalize()}", []).append(line)

    for section, members in by_activity.items():
        embed.add_field(name=section, value="\n".join(members), inline=False)

    embed.set_footer(text=f"Онлайн: {len(players)} пілотів • ARIA v1.0")
    return embed


def mission_embed(mission: dict) -> discord.Embed:
    status_emoji = MISSION_STATUS_EMOJI.get(mission["status"], "📋")
    embed = discord.Embed(
        title=f"{status_emoji} Місія: {mission['name']}",
        color=discord.Color.orange(),
    )
    if mission.get("location"):
        embed.add_field(name="📍 Локація", value=mission["location"], inline=True)
    if mission.get("start_time"):
        embed.add_field(name="⏰ Старт", value=mission["start_time"], inline=True)

    embed.add_field(name="\u200b", value="**── Склад місії ──**", inline=False)

    roles = mission.get("roles", [])
    if roles:
        for role in roles:
            parts = json_participants(role["participants"])
            filled = role["slots_filled"]
            total = role["slots_total"]
            bar = "🟢" * filled + "⬜" * (total - filled)
            value = f"{bar} `{filled}/{total}`"
            if parts:
                value += "\n" + "\n".join(f"• {n}" for n in parts)
            embed.add_field(name=f"🔹 {role['role_name']}", value=value, inline=True)
    else:
        embed.add_field(name="Ролі", value="*Ще не додані*", inline=False)

    embed.set_footer(text=f"ID місії: {mission['id']} • ARIA v1.0")
    return embed


def json_participants(participants) -> list[str]:
    if isinstance(participants, str):
        import json
        participants = json.loads(participants)
    return [p["name"] for p in participants]


def inventory_embed(items: list[dict], title: str) -> discord.Embed:
    embed = discord.Embed(title=f"📦 {title}", color=discord.Color.teal())
    if not items:
        embed.description = "*Склад порожній*"
        return embed

    by_location: dict[str, list[str]] = {}
    for item in items:
        loc = item.get("location") or "Невідомо"
        qty = item["quantity"]
        qty_str = str(int(qty)) if qty == int(qty) else str(qty)
        by_location.setdefault(loc, []).append(f"`{qty_str}x` {item['item_name']}")

    for loc, lines in by_location.items():
        embed.add_field(name=f"📍 {loc}", value="\n".join(lines), inline=False)

    return embed
