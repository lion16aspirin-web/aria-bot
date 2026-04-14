import aiosqlite
import json
from datetime import datetime
from config import DATABASE_PATH


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                discord_id   TEXT PRIMARY KEY,
                username     TEXT NOT NULL,
                status       TEXT DEFAULT 'офлайн',
                location     TEXT DEFAULT '',
                activity     TEXT DEFAULT '',
                last_seen    TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS inventory (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id     TEXT NOT NULL,
                owner_type   TEXT NOT NULL CHECK(owner_type IN ('personal','corp')),
                item_name    TEXT NOT NULL,
                quantity     REAL NOT NULL DEFAULT 1,
                location     TEXT NOT NULL DEFAULT '',
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS missions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT NOT NULL,
                creator_id       TEXT NOT NULL,
                location         TEXT DEFAULT '',
                start_time       TEXT DEFAULT '',
                status           TEXT DEFAULT 'planning',
                roles_json       TEXT DEFAULT '[]',
                participants_json TEXT DEFAULT '[]',
                log              TEXT DEFAULT '',
                message_id       TEXT DEFAULT '',
                channel_id       TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS mission_roles (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id    INTEGER NOT NULL REFERENCES missions(id),
                role_name     TEXT NOT NULL,
                slots_total   INTEGER NOT NULL DEFAULT 1,
                slots_filled  INTEGER NOT NULL DEFAULT 0,
                participants  TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS aria_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id  TEXT NOT NULL,
                role        TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
        """)
        await db.commit()


# ─── Players ──────────────────────────────────────────────────────────────────

async def upsert_player(discord_id: str, username: str, status: str,
                         location: str = "", activity: str = ""):
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO players (discord_id, username, status, location, activity, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                username=excluded.username,
                status=excluded.status,
                location=excluded.location,
                activity=excluded.activity,
                last_seen=excluded.last_seen
        """, (discord_id, username, status, location, activity, now))
        await db.commit()


async def set_player_offline(discord_id: str):
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE players SET status='офлайн', location='', activity='', last_seen=?
            WHERE discord_id=?
        """, (now, discord_id))
        await db.commit()


async def get_all_online_players():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM players WHERE status != 'офлайн'
            ORDER BY last_seen DESC
        """) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_all_players():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM players ORDER BY status, username") as cursor:
            return [dict(r) for r in await cursor.fetchall()]


# ─── Inventory ────────────────────────────────────────────────────────────────

async def add_inventory_items(owner_id: str, owner_type: str,
                               items: list[dict], location: str):
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        for item in items:
            # якщо позиція вже є в тій же локації — додаємо кількість
            async with db.execute("""
                SELECT id, quantity FROM inventory
                WHERE owner_id=? AND owner_type=? AND item_name=? AND location=?
            """, (owner_id, owner_type, item["name"], location)) as cur:
                row = await cur.fetchone()
            if row:
                await db.execute(
                    "UPDATE inventory SET quantity=?, updated_at=? WHERE id=?",
                    (row[1] + item["quantity"], now, row[0])
                )
            else:
                await db.execute("""
                    INSERT INTO inventory (owner_id, owner_type, item_name, quantity, location, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (owner_id, owner_type, item["name"], item["quantity"], location, now))
        await db.commit()


async def get_inventory(owner_id: str, owner_type: str = "personal"):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM inventory WHERE owner_id=? AND owner_type=?
            ORDER BY location, item_name
        """, (owner_id, owner_type)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_corp_inventory():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM inventory WHERE owner_type='corp'
            ORDER BY location, item_name
        """) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_all_inventory_for_context():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM inventory ORDER BY owner_type, location") as cursor:
            return [dict(r) for r in await cursor.fetchall()]


# ─── Missions ─────────────────────────────────────────────────────────────────

async def create_mission(name: str, creator_id: str, location: str = "",
                          start_time: str = "") -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO missions (name, creator_id, location, start_time, status)
            VALUES (?, ?, ?, ?, 'planning')
        """, (name, creator_id, location, start_time))
        await db.commit()
        return cursor.lastrowid


async def update_mission_message(mission_id: int, message_id: str, channel_id: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE missions SET message_id=?, channel_id=? WHERE id=?
        """, (message_id, channel_id, mission_id))
        await db.commit()


async def add_mission_role(mission_id: int, role_name: str, slots: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO mission_roles (mission_id, role_name, slots_total)
            VALUES (?, ?, ?)
        """, (mission_id, role_name, slots))
        await db.commit()
        return cursor.lastrowid


async def join_mission_role(mission_id: int, role_name: str,
                             discord_id: str, username: str) -> tuple[bool, str]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM mission_roles WHERE mission_id=? AND role_name=?
        """, (mission_id, role_name)) as cur:
            role = await cur.fetchone()
        if not role:
            return False, "Роль не знайдена"
        participants = json.loads(role["participants"])
        if discord_id in [p["id"] for p in participants]:
            return False, "Ти вже зареєстрований"
        if role["slots_filled"] >= role["slots_total"]:
            return False, "Немає вільних слотів"
        participants.append({"id": discord_id, "name": username})
        await db.execute("""
            UPDATE mission_roles
            SET slots_filled=slots_filled+1, participants=?
            WHERE mission_id=? AND role_name=?
        """, (json.dumps(participants, ensure_ascii=False), mission_id, role_name))
        await db.commit()
        return True, "OK"


async def leave_mission_role(mission_id: int, role_name: str,
                              discord_id: str) -> tuple[bool, str]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM mission_roles WHERE mission_id=? AND role_name=?
        """, (mission_id, role_name)) as cur:
            role = await cur.fetchone()
        if not role:
            return False, "Роль не знайдена"
        participants = json.loads(role["participants"])
        new_p = [p for p in participants if p["id"] != discord_id]
        if len(new_p) == len(participants):
            return False, "Тебе немає в цій ролі"
        await db.execute("""
            UPDATE mission_roles
            SET slots_filled=slots_filled-1, participants=?
            WHERE mission_id=? AND role_name=?
        """, (json.dumps(new_p, ensure_ascii=False), mission_id, role_name))
        await db.commit()
        return True, "OK"


async def get_mission(mission_id: int) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        mission = dict(row)
        async with db.execute(
            "SELECT * FROM mission_roles WHERE mission_id=?", (mission_id,)
        ) as cur:
            mission["roles"] = [dict(r) for r in await cur.fetchall()]
            for r in mission["roles"]:
                r["participants"] = json.loads(r["participants"])
        return mission


async def get_active_missions():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM missions WHERE status IN ('planning','active')
            ORDER BY start_time
        """) as cur:
            rows = await cur.fetchall()
        missions = []
        for row in rows:
            m = dict(row)
            async with db.execute(
                "SELECT * FROM mission_roles WHERE mission_id=?", (m["id"],)
            ) as cur2:
                m["roles"] = [dict(r) for r in await cur2.fetchall()]
                for r in m["roles"]:
                    r["participants"] = json.loads(r["participants"])
            missions.append(m)
        return missions


async def set_mission_status(mission_id: int, status: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE missions SET status=? WHERE id=?", (status, mission_id)
        )
        await db.commit()


# ─── ARIA history ─────────────────────────────────────────────────────────────

async def append_aria_history(discord_id: str, role: str, content: str,
                               limit: int = 20):
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO aria_history (discord_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
        """, (discord_id, role, content, now))
        # обрізаємо стару history
        await db.execute("""
            DELETE FROM aria_history WHERE discord_id=? AND id NOT IN (
                SELECT id FROM aria_history WHERE discord_id=?
                ORDER BY id DESC LIMIT ?
            )
        """, (discord_id, discord_id, limit))
        await db.commit()


async def get_aria_history(discord_id: str, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT role, content FROM aria_history
            WHERE discord_id=? ORDER BY id DESC LIMIT ?
        """, (discord_id, limit)) as cur:
            rows = await cur.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
