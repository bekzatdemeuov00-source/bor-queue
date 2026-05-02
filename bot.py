import asyncio
import time
import sqlite3
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

TOKEN = os.getenv("8483680613:AAFLt378QmboOqhk_PCksI45S-XlmiWlZAY")
ADMIN_ID = int(os.getenv("6707666425"))

bot = Bot(token=TOKEN)
dp = Dispatcher()

MAX_PEOPLE = 24

sosi_cooldown = {}  # chat_id -> timestamp
take_cooldown = {}  # user_id -> timestamp

# ================= DB =================
conn = sqlite3.connect("queue.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS queues(
    name TEXT PRIMARY KEY
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS queue_members(
    queue_name TEXT,
    user_id INTEGER UNIQUE,
    name TEXT,
    position INTEGER
)
""")

conn.commit()

for q in ["Math", "Java", "Physics"]:
    cur.execute("INSERT OR IGNORE INTO queues(name) VALUES(?)", (q,))
conn.commit()

# ================= ADMIN =================
def is_admin(user_id):
    return user_id == ADMIN_ID

# ================= HELPERS =================
def get_queues():
    cur.execute("SELECT name FROM queues ORDER BY name")
    return [x[0] for x in cur.fetchall()]


def get_busy(queue):
    cur.execute("SELECT position FROM queue_members WHERE queue_name=?", (queue,))
    return [x[0] for x in cur.fetchall()]


def get_owner(queue, pos):
    cur.execute("""
    SELECT name FROM queue_members
    WHERE queue_name=? AND position=?
    """, (queue, pos))
    r = cur.fetchone()
    return r[0] if r else None


def get_user_info(user_id):
    cur.execute("SELECT queue_name, position, name FROM queue_members WHERE user_id=?", (user_id,))
    return cur.fetchone()


def save_user(queue, user_id, name, pos):
    cur.execute("DELETE FROM queue_members WHERE user_id=?", (user_id,))
    cur.execute("""
    INSERT INTO queue_members(queue_name,user_id,name,position)
    VALUES(?,?,?,?)
    """, (queue, user_id, name, pos))
    conn.commit()


def remove_user(user_id):
    cur.execute("DELETE FROM queue_members WHERE user_id=?", (user_id,))
    conn.commit()


def queue_text(queue):
    cur.execute("""
    SELECT name, position FROM queue_members
    WHERE queue_name=?
    ORDER BY position
    """, (queue,))
    rows = cur.fetchall()
    busy_count = len(rows)
    free_count = MAX_PEOPLE - busy_count

    text = f"📚 <b>Очередь: {queue}</b>\n"
    text += f"👥 Занято: {busy_count}/{MAX_PEOPLE}   🟢 Свободно: {free_count}\n"
    text += "─" * 28 + "\n"

    if not rows:
        text += "\n<i>Очередь пуста. Будь первым!</i>"
    else:
        for r in rows:
            text += f"  <b>{r[1]}.</b> {r[0]}\n"

    return text


def all_queues_text():
    queues = get_queues()
    text = "📋 <b>Все очереди:</b>\n\n"
    for q in queues:
        cur.execute("SELECT COUNT(*) FROM queue_members WHERE queue_name=?", (q,))
        count = cur.fetchone()[0]
        bar = "█" * count + "░" * (MAX_PEOPLE - count)
        text += f"📘 <b>{q}</b>  [{count}/{MAX_PEOPLE}]\n"
        text += f"<code>{bar[:12]}</code>\n\n"
    return text if queues else "Очередей пока нет."

# ================= UI =================
def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Список очередей", callback_data="queues"),
        ],
        [
            InlineKeyboardButton(text="✏️ Встать в очередь", callback_data="choose_queue"),
            InlineKeyboardButton(text="📍 Моё место", callback_data="myplace"),
        ],
        [
            InlineKeyboardButton(text="❌ Выйти из очереди", callback_data="leave"),
        ]
    ])


def admin_menu():
    base = menu()
    base.inline_keyboard.append([
        InlineKeyboardButton(text="➕ Добавить очередь", callback_data="admin_addq"),
        InlineKeyboardButton(text="🗑 Удалить очередь", callback_data="admin_delq"),
    ])
    base.inline_keyboard.append([
        InlineKeyboardButton(text="🔄 Сбросить очередь", callback_data="admin_reset"),
    ])
    return base


def queues_kb(callback_prefix="q"):
    buttons = [
        [InlineKeyboardButton(text=f"📘 {q}", callback_data=f"{callback_prefix}:{q}")]
        for q in get_queues()
    ]
    buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def places_kb(queue):
    busy = get_busy(queue)
    rows = []
    line = []

    for i in range(1, MAX_PEOPLE + 1):
        if i in busy:
            owner = get_owner(queue, i)
            short = owner[:8] + "…" if owner and len(owner) > 8 else owner
            btn = InlineKeyboardButton(text=f"🔴{i}", callback_data=f"info:{queue}:{i}")
        else:
            btn = InlineKeyboardButton(text=f"🟢{i}", callback_data=f"take:{queue}:{i}")

        line.append(btn)

        if len(line) == 6:
            rows.append(line)
            line = []

    if line:
        rows.append(line)

    rows.append([
        InlineKeyboardButton(text="📋 Список", callback_data=f"showlist:{queue}"),
        InlineKeyboardButton(text="⬅ Назад", callback_data="choose_queue"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def del_queue_kb():
    buttons = [
        [InlineKeyboardButton(text=f"🗑 {q}", callback_data=f"admin_del:{q}")]
        for q in get_queues()
    ]
    buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def reset_queue_kb():
    buttons = [
        [InlineKeyboardButton(text=f"🔄 {q}", callback_data=f"admin_doreset:{q}")]
        for q in get_queues()
    ]
    buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================= TRIGGER =================
@dp.message(F.text.lower().in_({"сосо", "сосо!", "сосо?"}))
async def soso(message: types.Message):
    chat_id = message.chat.id
    now = time.time()
    last = sosi_cooldown.get(chat_id, 0)
    if now - last < 30:
        return
    sosi_cooldown[chat_id] = now
    await message.reply("сам сосо 🖕")


@dp.message(F.text.lower().strip().in_({"кюе", "кue", "kyue", "queue", "очередь"}))
async def trigger(message: types.Message):
    kb = admin_menu() if is_admin(message.from_user.id) else menu()

    await message.reply(
        "🤖 <b>Queue Master</b>\n\n"
        "Управление очередями. Выбери действие ниже 👇",
        reply_markup=kb,
        parse_mode="HTML"
    )

# ================= ADMIN COMMANDS =================
@dp.message(Command("addqueue"))
async def cmd_addqueue(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔ Только для администратора.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: /addqueue <Название>")
        return

    name = parts[1].strip()
    cur.execute("INSERT OR IGNORE INTO queues(name) VALUES(?)", (name,))
    conn.commit()
    await message.reply(f"✅ Очередь <b>{name}</b> добавлена!", parse_mode="HTML")


@dp.message(Command("delqueue"))
async def cmd_delqueue(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔ Только для администратора.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: /delqueue <Название>")
        return

    name = parts[1].strip()
    cur.execute("DELETE FROM queues WHERE name=?", (name,))
    cur.execute("DELETE FROM queue_members WHERE queue_name=?", (name,))
    conn.commit()
    await message.reply(f"🗑 Очередь <b>{name}</b> удалена.", parse_mode="HTML")


@dp.message(Command("queues"))
async def cmd_queues(message: types.Message):
    await message.reply(all_queues_text(), parse_mode="HTML")

# ================= CALLBACKS =================
@dp.callback_query(F.data == "menu")
async def back(cb: types.CallbackQuery):
    kb = admin_menu() if is_admin(cb.from_user.id) else menu()
    await cb.message.edit_text(
        "🤖 <b>Queue Master</b>\n\nВыбери действие 👇",
        reply_markup=kb,
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "queues")
async def show_all_queues(cb: types.CallbackQuery):
    await cb.message.edit_text(
        all_queues_text(),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅ Назад", callback_data="menu")]
        ]),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "choose_queue")
async def choose_queue(cb: types.CallbackQuery):
    await cb.message.edit_text("📘 Выбери очередь:", reply_markup=queues_kb("q"))


@dp.callback_query(F.data.startswith("q:"))
async def open_queue(cb: types.CallbackQuery):
    queue = cb.data.split(":")[1]
    await cb.message.edit_text(
        queue_text(queue),
        reply_markup=places_kb(queue),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("showlist:"))
async def show_list(cb: types.CallbackQuery):
    queue = cb.data.split(":")[1]
    await cb.answer(queue_text(queue).replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", ""), show_alert=True)


@dp.callback_query(F.data.startswith("info:"))
async def info(cb: types.CallbackQuery):
    _, queue, pos = cb.data.split(":")
    pos = int(pos)
    owner = get_owner(queue, pos)
    if owner:
        await cb.answer(f"🔴 Занято\n👤 {owner}", show_alert=True)
    else:
        await cb.answer("🟢 Свободно!", show_alert=True)


@dp.callback_query(F.data.startswith("take:"))
async def take(cb: types.CallbackQuery):
    _, queue, pos = cb.data.split(":")
    pos = int(pos)

    # Cooldown 15 сек на смену места
    now = time.time()
    last = take_cooldown.get(cb.from_user.id, 0)
    if now - last < 15:
        remaining = int(15 - (now - last))
        await cb.answer(f"⏳ Подожди ещё {remaining} сек. перед сменой места.", show_alert=True)
        return

    busy = get_busy(queue)

    if pos in busy:
        owner = get_owner(queue, pos)
        await cb.answer(f"🔴 Занято!\n👤 {owner}", show_alert=True)
        return

    if len(busy) >= MAX_PEOPLE:
        await cb.answer("❌ Очередь заполнена (24/24)", show_alert=True)
        return

    # Check if user was in another queue
    old = get_user_info(cb.from_user.id)
    old_msg = ""
    if old and old[0] != queue:
        old_msg = f"\n<i>(вышел из {old[0]} #{old[1]})</i>"

    save_user(queue, cb.from_user.id, cb.from_user.full_name, pos)
    take_cooldown[cb.from_user.id] = time.time()

    await cb.message.edit_text(
        queue_text(queue),
        reply_markup=places_kb(queue),
        parse_mode="HTML"
    )

    # silent — queue updated in place, no spam message


@dp.callback_query(F.data == "leave")
async def leave(cb: types.CallbackQuery):
    info = get_user_info(cb.from_user.id)
    if not info:
        await cb.answer("Ты не в очереди.", show_alert=True)
        return

    remove_user(cb.from_user.id)
    await cb.answer(f"✅ Вышел из {info[0]} #{info[1]}", show_alert=True)
    await cb.message.answer(
        f"👋 <b>{cb.from_user.full_name}</b> вышел из очереди <b>{info[0]}</b> (место #{info[1]})",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "myplace")
async def myplace(cb: types.CallbackQuery):
    info = get_user_info(cb.from_user.id)
    if not info:
        await cb.answer("Ты не в очереди.", show_alert=True)
        return
    await cb.answer(f"📍 {info[0]} → место #{info[1]}", show_alert=True)


# ================= ADMIN CALLBACKS =================
@dp.callback_query(F.data == "admin_addq")
async def admin_addq(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа.", show_alert=True)
        return
    await cb.message.edit_text(
        "➕ <b>Добавить очередь</b>\n\nОтправь команду:\n<code>/addqueue Название</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅ Назад", callback_data="menu")]
        ])
    )


@dp.callback_query(F.data == "admin_delq")
async def admin_delq(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа.", show_alert=True)
        return
    if not get_queues():
        await cb.answer("Очередей нет.", show_alert=True)
        return
    await cb.message.edit_text(
        "🗑 <b>Удалить очередь:</b>",
        parse_mode="HTML",
        reply_markup=del_queue_kb()
    )


@dp.callback_query(F.data.startswith("admin_del:"))
async def admin_do_del(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа.", show_alert=True)
        return
    name = cb.data.split(":", 1)[1]
    cur.execute("DELETE FROM queues WHERE name=?", (name,))
    cur.execute("DELETE FROM queue_members WHERE queue_name=?", (name,))
    conn.commit()
    await cb.answer(f"✅ Очередь {name} удалена.", show_alert=True)
    await back(cb)


@dp.callback_query(F.data == "admin_reset")
async def admin_reset(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа.", show_alert=True)
        return
    if not get_queues():
        await cb.answer("Очередей нет.", show_alert=True)
        return
    await cb.message.edit_text(
        "🔄 <b>Сбросить очередь</b> (удалить всех участников):",
        parse_mode="HTML",
        reply_markup=reset_queue_kb()
    )


@dp.callback_query(F.data.startswith("admin_doreset:"))
async def admin_do_reset(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа.", show_alert=True)
        return
    name = cb.data.split(":", 1)[1]
    cur.execute("DELETE FROM queue_members WHERE queue_name=?", (name,))
    conn.commit()
    await cb.answer(f"✅ Очередь {name} сброшена.", show_alert=True)
    await cb.message.answer(
        f"🔄 Очередь <b>{name}</b> была сброшена администратором.",
        parse_mode="HTML"
    )
    await back(cb)


# ================= RUN =================
async def main():
    print("BOT STARTED")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())