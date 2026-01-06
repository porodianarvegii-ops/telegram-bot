import asyncio
import aiosqlite
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.command import Command
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "0").split(",") if id.strip()]
DB_PATH = "bookings.db"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables")

def is_admin(user_id):
    return user_id in ADMIN_IDS

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# in-memory state for pending review submissions
pending_reviews = set()

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            date TEXT,
            time TEXT,
            comment TEXT
        )
        """)
        # Ensure new columns exist if the table was created earlier
        cursor = await db.execute("PRAGMA table_info(bookings)")
        cols = await cursor.fetchall()
        col_names = {c[1] for c in cols}
        if 'time' not in col_names:
            try:
                await db.execute("ALTER TABLE bookings ADD COLUMN time TEXT")
            except Exception:
                pass
        if 'comment' not in col_names:
            try:
                await db.execute("ALTER TABLE bookings ADD COLUMN comment TEXT")
            except Exception:
                pass
        await db.commit()
        # create reviews table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            text TEXT,
            created_at TEXT
        )
        """)
        await db.commit()

def date_keyboard():
    buttons = []
    for i in range(7):
        d = (datetime.now() + timedelta(days=i)).strftime("%d.%m.%Y")
        buttons.append([InlineKeyboardButton(text=d, callback_data=f"date_{d}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def time_keyboard(date: str):
    # fixed time slots — you can change these
    times = ["10:00", "11:00", "12:00", "14:00", "15:00", "16:00"]
    buttons = []
    for t in times:
        buttons.append([InlineKeyboardButton(text=t, callback_data=f"time_{date}_{t}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_keyboard():
    buttons = [
        [InlineKeyboardButton(text="📋 Просмотреть все записи", callback_data="admin_view")],
        [InlineKeyboardButton(text="❌ Отменить запись", callback_data="admin_cancel")],
        [InlineKeyboardButton(text="✏️ Изменить дату записи", callback_data="admin_edit")],
        [InlineKeyboardButton(text="📝 Отзывы", callback_data="admin_reviews")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def main_keyboard():
    buttons = [
        [InlineKeyboardButton(text="📞 Связаться", callback_data="contact")],
        [InlineKeyboardButton(text="🛠 Мои работы", callback_data="mywork")],
        [InlineKeyboardButton(text="💬 Отзывы", callback_data="reviews")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def start(message: types.Message):
    try:
        await message.answer("📅 Выберите дату для записи:", reply_markup=date_keyboard())
        await message.answer("Быстрые команды:", reply_markup=main_keyboard())
    except Exception as e:
        print(f"Error in start command: {e}")
        await message.answer("❌ Произошла ошибка")

@dp.callback_query(lambda c: c.data.startswith("date_"))
async def date_selected(call: types.CallbackQuery):
    try:
        date = call.data.replace("date_", "")
        # ask user to choose time after date
        await call.message.answer(f"Вы выбрали дату: {date}\nВыберите время:", reply_markup=time_keyboard(date))
        await call.answer()
    except Exception as e:
        print(f"Error in date_selected: {e}")
        await call.message.answer("❌ Ошибка")
        await call.answer()

@dp.callback_query(lambda c: c.data.startswith("time_"))
async def time_selected(call: types.CallbackQuery):
    try:
        payload = call.data.replace("time_", "")
        # payload = "{date}_{time}"
        parts = payload.rsplit("_", 1)
        date = parts[0]
        time = parts[1]

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO bookings (user_id, name, date, time, comment) VALUES (?, ?, ?, ?, ?)",
                (call.from_user.id, call.from_user.first_name, date, time, None)
            )
            await db.commit()

        await call.message.answer(f"✅ Вы записаны на {date} в {time}.\nНапишите комментарий к записи или отправьте /skip, чтобы пропустить.")
        # notify admins
        if ADMIN_IDS:
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, f"📌 Новая запись:\n👤 {call.from_user.first_name}\n📅 {date} {time}")
                except:
                    pass
        await call.answer()
    except Exception as e:
        print(f"Error in time_selected: {e}")
        await call.message.answer("❌ Ошибка при сохранении записи")
        await call.answer()

@dp.callback_query(lambda c: c.data == "contact")
async def contact_info(call: types.CallbackQuery):
    try:
        await call.message.answer("📞 Контакты администратора:\n@simbviska\nID: 1076207542")
        await call.answer()
    except Exception as e:
        print(f"Error in contact_info: {e}")
        await call.answer()

@dp.callback_query(lambda c: c.data == "mywork")
async def my_work(call: types.CallbackQuery):
    try:
        await call.message.answer("🛠 Мои работы и отзывы: https://t.me/vii_nails_art")
        await call.answer()
    except Exception as e:
        print(f"Error in my_work: {e}")
        await call.answer()

@dp.callback_query(lambda c: c.data == "reviews")
async def show_reviews(call: types.CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT name, text, created_at FROM reviews ORDER BY id DESC LIMIT 10")
            rows = await cursor.fetchall()

        text = "💬 Отзывы:\n\n"
        if not rows:
            text = "Пока нет отзывов."
        else:
            for name, text_rev, created in rows:
                text += f"👤 {name}: {text_rev} ({created})\n\n"

        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Оставить отзыв", callback_data="leave_review")]])
        await call.message.answer(text, reply_markup=kb)
        await call.answer()
    except Exception as e:
        print(f"Error in show_reviews: {e}")
        await call.answer()

@dp.callback_query(lambda c: c.data == "leave_review")
async def leave_review_cb(call: types.CallbackQuery):
    try:
        pending_reviews.add(call.from_user.id)
        await call.message.answer("Напишите, пожалуйста, ваш отзыв в сообщении.")
        await call.answer()
    except Exception as e:
        print(f"Error in leave_review_cb: {e}")
        await call.answer()

@dp.message(Command("review"))
async def review_cmd(message: types.Message):
    pending_reviews.add(message.from_user.id)
    await message.reply("Напишите, пожалуйста, ваш отзыв в сообщении.")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Доступ запрещён")
        return

    await message.answer("🔧 Панель администратора", reply_markup=admin_keyboard())

@dp.callback_query(lambda c: c.data == "admin_view")
async def admin_view_all(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Доступ запрещён")
        return

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT id, name, date, time, comment FROM bookings")
            rows = await cursor.fetchall()

        if not rows:
            await call.message.answer("Записей пока нет.")
            return

        text = "📋 Все записи:\n\n"
        for row_id, name, date, time, comment in rows:
            text += f"ID: {row_id}\n👤 {name}\n📅 {date} {time}\nКомментарий: {comment if comment else '-'}\n\n"

        await call.message.answer(text)
    except Exception as e:
        print(f"Error in admin_view_all: {e}")
        await call.message.answer("❌ Ошибка при получении записей")


@dp.callback_query(lambda c: c.data == "admin_reviews")
async def admin_show_reviews(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Доступ запрещён")
        return

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT id, name, text, created_at FROM reviews ORDER BY id DESC LIMIT 50")
            rows = await cursor.fetchall()

        if not rows:
            await call.message.answer("Отзывы отсутствуют.")
            return

        text = "📝 Все отзывы:\n\n"
        for r_id, name, text_rev, created in rows:
            text += f"ID:{r_id} 👤 {name}: {text_rev} ({created})\n\n"

        await call.message.answer(text)
    except Exception as e:
        print(f"Error in admin_show_reviews: {e}")
        await call.message.answer("❌ Ошибка при получении отзывов")

@dp.callback_query(lambda c: c.data == "admin_cancel")
async def admin_cancel_booking(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Доступ запрещён")
        return

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT id, name, date, time FROM bookings")
            rows = await cursor.fetchall()

        if not rows:
            await call.message.answer("Нет записей для отмены.")
            return

        buttons = []
        for row_id, name, date, time in rows:
            buttons.append([InlineKeyboardButton(
                text=f"Отменить: {name} ({date} {time})",
                callback_data=f"cancel_id_{row_id}"
            )])
        
        await call.message.answer("Выберите запись для отмены:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception as e:
        print(f"Error in admin_cancel_booking: {e}")
        await call.message.answer("❌ Error loading bookings")

@dp.callback_query(lambda c: c.data.startswith("cancel_id_"))
async def confirm_cancel(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Доступ запрещён")
        return

    try:
        booking_id = int(call.data.replace("cancel_id_", ""))
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT user_id, name, date, time FROM bookings WHERE id = ?", (booking_id,))
            row = await cursor.fetchone()
            
            if row:
                user_id, name, date, time = row
                await db.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
                await db.commit()
                
                await call.message.answer(f"✅ Отменено: {name} ({date} {time})")
                
                # Notify user
                try:
                    await bot.send_message(user_id, f"⚠️ Ваша запись на {date} {time} была отменена администратором")
                except:
                    pass
            else:
                await call.message.answer("❌ Запись не найдена")
    except Exception as e:
        print(f"Error in confirm_cancel: {e}")
        await call.message.answer("❌ Error cancelling booking")

@dp.callback_query(lambda c: c.data == "admin_edit")
async def admin_edit_booking(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Доступ запрещён")
        return

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT id, name, date, time, comment FROM bookings")
            rows = await cursor.fetchall()

        if not rows:
            await call.message.answer("Нет записей для изменения.")
            return

        buttons = []
        for row_id, name, date, time, comment in rows:
            buttons.append([InlineKeyboardButton(
                text=f"Изменить: {name} ({date} {time})",
                callback_data=f"edit_id_{row_id}"
            )])
        
        await call.message.answer("Выберите запись для изменения:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception as e:
        print(f"Error in admin_edit_booking: {e}")
        await call.message.answer("❌ Error loading bookings")

@dp.callback_query(lambda c: c.data.startswith("edit_id_"))
async def select_new_date(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Access denied")
        return

    booking_id = int(call.data.replace("edit_id_", ""))
    
    buttons = []
    for i in range(7):
        d = (datetime.now() + timedelta(days=i)).strftime("%d.%m.%Y")
        buttons.append([InlineKeyboardButton(
            text=d,
            callback_data=f"new_date_{booking_id}_{d}"
        )])
    
    await call.message.answer("Выберите новую дату:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(lambda c: c.data.startswith("new_date_"))
async def confirm_edit(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Access denied")
        return

    try:
        parts = call.data.replace("new_date_", "").split("_", 1)
        booking_id = int(parts[0])
        new_date = parts[1]
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT user_id, name FROM bookings WHERE id = ?", (booking_id,))
            row = await cursor.fetchone()
            
            if row:
                user_id, name = row
                await db.execute("UPDATE bookings SET date = ? WHERE id = ?", (new_date, booking_id))
                await db.commit()
                
                await call.message.answer(f"✅ Обновлено: {name} → {new_date}")
                
                # Notify user
                try:
                    await bot.send_message(user_id, f"📅 Ваша запись перенесена на {new_date}")
                except:
                    pass
            else:
                await call.message.answer("❌ Запись не найдена")
    except Exception as e:
        print(f"Error in confirm_edit: {e}")
        await call.message.answer("❌ Ошибка при обновлении записи")


@dp.message()
async def handle_comment(message: types.Message):
    # ignore commands
    if not message.text or message.text.startswith("/"):
        return

    # If user is leaving a review
    if message.from_user.id in pending_reviews:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT INTO reviews (user_id, name, text, created_at) VALUES (?, ?, ?, ?)",
                    (message.from_user.id, message.from_user.first_name, message.text.strip(), datetime.now().isoformat())
                )
                await db.commit()

            pending_reviews.discard(message.from_user.id)
            await message.reply("✅ Спасибо за отзыв!")
            # notify admins
            if ADMIN_IDS:
                for admin_id in ADMIN_IDS:
                    try:
                        await bot.send_message(admin_id, f"🆕 Новый отзыв от {message.from_user.first_name}: {message.text.strip()}")
                    except:
                        pass
            return
        except Exception as e:
            print(f"Error saving review: {e}")
            await message.reply("❌ Ошибка при сохранении отзыва")
            pending_reviews.discard(message.from_user.id)
            return

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id FROM bookings WHERE user_id = ? AND comment IS NULL ORDER BY id DESC LIMIT 1",
                (message.from_user.id,)
            )
            row = await cursor.fetchone()

            if not row:
                await message.reply("Я не нашёл запись для добавления комментария. Отправьте /start, чтобы записаться.")
                return

            booking_id = row[0]
            await db.execute("UPDATE bookings SET comment = ? WHERE id = ?", (message.text.strip(), booking_id))
            await db.commit()

        await message.reply("✅ Комментарий сохранён. Ваша запись подтверждена.")
        # notify admins about comment
        if ADMIN_IDS:
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, f"💬 Комментарий к записи от {message.from_user.first_name}: {message.text.strip()}")
                except:
                    pass
    except Exception as e:
        print(f"Error in handle_comment: {e}")
        await message.reply("❌ Ошибка при сохранении комментария")


@dp.message(Command("skip"))
async def skip_comment(message: types.Message):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id FROM bookings WHERE user_id = ? AND comment IS NULL ORDER BY id DESC LIMIT 1",
                (message.from_user.id,)
            )
            row = await cursor.fetchone()
            if not row:
                await message.reply("Нет ожидающих комментариев.")
                return

            booking_id = row[0]
            await db.execute("UPDATE bookings SET comment = ? WHERE id = ?", ("", booking_id))
            await db.commit()

        await message.reply("Комментарий пропущен. Ваша запись подтверждена.")
    except Exception as e:
        print(f"Error in skip_comment: {e}")
        await message.reply("❌ Ошибка")

async def main():
    await init_db()
    
    # Delete any existing webhook to use polling instead
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Webhook cleanup: {e}")
    
    print("✅ Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Bot stopped")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
