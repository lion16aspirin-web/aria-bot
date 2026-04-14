import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "aria.db")

# UEX Corp API (https://uexcorp.space) — опціонально, без ключа доступні публічні ендпоінти
UEX_API_KEY = os.getenv("UEX_API_KEY", "")

# Назва каналу де виводяться статуси org
STATUS_CHANNEL_NAME = os.getenv("STATUS_CHANNEL_NAME", "org-статус")
# Назва каналу для місій
MISSIONS_CHANNEL_NAME = os.getenv("MISSIONS_CHANNEL_NAME", "місії")

# Prefix для команд бота
COMMAND_PREFIX = "!"

# Claude модель
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Максимум повідомлень в history ARIA на гравця
ARIA_HISTORY_LIMIT = 20

# Через скільки секунд без активності статус вважається "офлайн"
# (Discord сам повідомляє про offline через on_member_update)
