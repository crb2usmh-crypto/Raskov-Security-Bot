import os
import re
import random
from datetime import datetime, timedelta
import telegram

# ===================== استيراد Supabase =====================
from supabase import create_client, Client

# ===================== استيراد جدولة المهام =====================
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ===================== إعدادات البيئة =====================
TOKEN = os.getenv("BOT_TOKEN")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")
REPORT_CHANNEL_ID = os.getenv("REPORT_CHANNEL_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ===================== تهيئة Supabase =====================
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ تم الاتصال بـ Supabase بنجاح")
    except Exception as e:
        print(f"❌ فشل الاتصال بـ Supabase: {e}")
        supabase = None
else:
    supabase = None
    print("⚠️ Supabase غير مضبوط، سيتم استخدام الذاكرة المؤقتة")

# ===================== القوانين =====================
GROUP_RULES = (
    "📜 <b>قوانين المجموعة</b> 📜\n\n"
    "1️⃣ ممنوع نشر الروابط (ما عدا minepi.com و pi.app).\n"
    "2️⃣ ممنوع نشر أرقام الهواتف أو المحافظ الرقمية.\n"
    "3️⃣ ممنوع التكرار السريع للرسائل (سبام).\n"
    "4️⃣ ممنوع نشر الصور أو الفيديوهات غير المفيدة.\n"
    "5️⃣ ممنوع استخدام الكلمات الممنوعة (نصب، احتيال، سبام).\n"
    "6️⃣ احترام جميع الأعضاء.\n\n"
    "⚠️ المخالفة الأولى: تحذير.\n"
    "⚠️ المخالفة الثانية: كتم 10 دقائق.\n"
    "⚠️ المخالفة الثالثة: حظر تلقائي.\n"
    "🔐 عند الانضمام، يجب حل الكابتشا للتحقق البشري."
)

# ===================== إعدادات الحماية =====================
AUTO_KICK_TIMEOUT = 60
CAPTCHA_ATTEMPTS = 3
FLOOD_LIMIT = 5
FLOOD_TIME = 4
MUTE_DURATION = 5
MUTE_DURATION_SECOND = 10

# ===================== القائمة البيضاء =====================
ALLOWED_DOMAINS = ["minepi.com", "pi.app"]

# ===================== إعدادات القفل =====================
LOCK_LINKS = True
LOCK_MEDIA = False
LOCK_FORWARD = False

# ===================== الكلمات الممنوعة =====================
FORBIDDEN_WORDS = [
    "نصب", "احتيال", "سبام", "إعلان", "دعاية",
    "تزوير", "اختراق", "أرباح سريعة", "استثمار مضمون",
    "بيع باي", "شراء باي", "سعر باي", "تداول باي",
    "scam", "spam", "hack", "cheat", "fraud", "phishing",
    "promo", "advertisement", "earn money", "free money",
]

# ===================== الأنماط (Regex) =====================
LINK_PATTERN = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|[a-zA-Z0-9-]+\.(com|net|org|io|app|xyz|me|co))",
    re.IGNORECASE
)
WALLET_PATTERN = re.compile(
    r"\b(0x[a-fA-F0-9]{40}|T[a-zA-Z0-9]{33})\b",
    re.IGNORECASE
)
PHONE_PATTERN = re.compile(r"\+?\d{7,15}")

# ===================== التخزين المؤقت =====================
warnings_db = {}
user_messages = {}
pending_captcha = {}


# ===================== دوال Supabase الأساسية =====================

def get_warnings(user_id: int) -> int:
    if not supabase:
        return warnings_db.get(user_id, 0)
    try:
        res = supabase.table("warnings").select("count").eq("user_id", user_id).execute()
        if res.data:
            return res.data[0].get("count", 0)
        return 0
    except Exception as e:
        print(f"⚠️ خطأ في جلب المخالفات: {e}")
        return warnings_db.get(user_id, 0)


def increment_warning(user_id: int, first_name: str) -> int:
    if not supabase:
        warnings_db[user_id] = warnings_db.get(user_id, 0) + 1
        return warnings_db[user_id]
    try:
        res = supabase.table("warnings").select("count").eq("user_id", user_id).execute()
        if res.data:
            current = res.data[0].get("count", 0)
            new_count = current + 1
            supabase.table("warnings").update({"count": new_count}).eq("user_id", user_id).execute()
            return new_count
        else:
            supabase.table("warnings").insert({
                "user_id": user_id,
                "first_name": first_name,
                "count": 1
            }).execute()
            return 1
    except Exception as e:
        print(f"⚠️ خطأ في زيادة المخالفات: {e}")
        warnings_db[user_id] = warnings_db.get(user_id, 0) + 1
        return warnings_db[user_id]


def reset_warnings_db(user_id: int):
    if not supabase:
        if user_id in warnings_db:
            del warnings_db[user_id]
        return
    try:
        supabase.table("warnings").delete().eq("user_id", user_id).execute()
    except Exception as e:
        print(f"⚠️ خطأ في إعادة التعيين: {e}")
        if user_id in warnings_db:
            del warnings_db[user_id]


def log_violation(user_id: int, chat_id: int, violation_type: str, content: str):
    if not supabase:
        return
    try:
        supabase.table("violations_log").insert({
            "user_id": user_id,
            "chat_id": chat_id,
            "type": violation_type,
            "content": content[:200]
        }).execute()
    except Exception as e:
        print(f"⚠️ خطأ في تسجيل المخالفة: {e}")


def get_group_settings(chat_id: int) -> dict:
    default = {"lock_links": True, "lock_media": False, "lock_forward": False}
    if not supabase:
        return default
    try:
        res = supabase.table("group_settings").select("*").eq("chat_id", chat_id).execute()
        if res.data:
            data = res.data[0]
            return {
                "lock_links": data.get("lock_links", True),
                "lock_media": data.get("lock_media", False),
                "lock_forward": data.get("lock_forward", False),
            }
        else:
            supabase.table("group_settings").insert({
                "chat_id": chat_id,
                "lock_links": True,
                "lock_media": False,
                "lock_forward": False
            }).execute()
            return default
    except Exception as e:
        print(f"⚠️ خطأ في جلب الإعدادات: {e}")
        return default


def update_group_setting(chat_id: int, setting_name: str, value: bool):
    if not supabase:
        return
    try:
        supabase.table("group_settings").update({setting_name: value}).eq("chat_id", chat_id).execute()
    except Exception as e:
        print(f"⚠️ خطأ في تحديث الإعدادات: {e}")


# ===================== دوال المساعدة =====================

async def is_admin(bot, chat_id, user_id):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False


def clean_obfuscated_text(text: str) -> str:
    cleaned = re.sub(r'\s+', '', text)
    cleaned = re.sub(r'dot', '.', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'at', '@', cleaned, flags=re.IGNORECASE)
    replacements = {'0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '@': 'a'}
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r'hxxps?', 'https', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'hxxp', 'http', cleaned, flags=re.IGNORECASE)
    return cleaned


def contains_forbidden_word(text: str) -> tuple:
    text_lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if word.lower() in text_lower:
            return True, word
    return False, None


async def send_log(bot, user, chat_title, deleted_text, violation_type="رابط"):
    if not LOG_CHANNEL_ID:
        return
    time_now = datetime.now().strftime("%I:%M %p - %d/%m/%Y")
    emoji_map = {
        "رابط غير مسموح": "🚫",
        "رابط غير مسموح (ملتف)": "🚫",
        "رقم هاتف": "📞",
        "محفظة رقمية": "💰",
        "⏳ سبام (تكرار)": "⏳",
        "صورة/فيديو": "🖼️",
        "رسالة معاد توجيهها": "↩️",
        "⚠️ إدارة": "⚙️",
        "🔄 إعادة تعيين مخالفات": "🔄",
        "👋 ترحيب": "👋",
        "🚪 مغادرة": "🚪",
        "❌ طرد": "⛔",
        "🚫 كلمة ممنوعة": "🚫",
        "🔇 كتم 10 دقائق": "🔇",
        "🤖 كابتشا - نجاح": "✅",
        "🤖 كابتشا - فشل": "❌",
    }
    emoji = emoji_map.get(violation_type, "⚠️")
    log_message = (
        f"🕒 {time_now}\n"
        f"{emoji} <b>{violation_type}</b>\n"
        f"👤 المستخدم: {user.first_name}\n"
        f"🆔 معرفه: <code>{user.id}</code>\n"
        f"🏠 المجموعة: {chat_title}\n"
        f"📝 التفاصيل:\n<code>{deleted_text[:150]}</code>"
    )
    try:
        await bot.send_message(chat_id=LOG_CHANNEL_ID, text=log_message, parse_mode="HTML")
    except Exception as e:
        print(f"❌ فشل إرسال اللوج: {e}")


async def mute_user(bot, chat_id, user_id, duration_minutes):
    try:
        until_date = datetime.now() + timedelta(minutes=duration_minutes)
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        return True
    except Exception as e:
        print(f"❌ فشل الكتم: {e}")
        return False


async def check_flood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    now = datetime.now()

    if await is_admin(context.bot, chat_id, user_id):
        return False

    if user_id not in user_messages:
        user_messages[user_id] = []

    user_messages[user_id].append(now)
    cutoff = now - timedelta(seconds=FLOOD_TIME)
    user_messages[user_id] = [t for t in user_messages[user_id] if t > cutoff]

    if len(user_messages[user_id]) > FLOOD_LIMIT:
        success = await mute_user(context.bot, chat_id, user_id, MUTE_DURATION)
        if success:
            await send_log(
                bot=context.bot,
                user=update.effective_user,
                chat_title=update.effective_chat.title or "المجموعة",
                deleted_text=f"كتم {MUTE_DURATION} دقائق لتكرار الرسائل",
                violation_type="⏳ سبام (تكرار)"
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔇 {update.effective_user.first_name} تم كتمه {MUTE_DURATION} دقائق للتكرار السريع."
            )
        try:
            await update.message.delete()
        except:
            pass
        return True
    return False


# ===================== دوال الكابتشا =====================

def generate_captcha() -> tuple:
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    op = random.choice(['+', '-'])
    if op == '-':
        if a < b:
            a, b = b, a
        answer = a - b
    else:
        answer = a + b
    question = f"{a} {op} {b} = ؟"
    return question, answer


async def send_captcha(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, first_name: str):
    question, answer = generate_captcha()
    pending_captcha[user_id] = {
        "answer": answer,
        "attempts": 0,
        "chat_id": chat_id,
        "first_name": first_name
    }

    keyboard = [[InlineKeyboardButton("🔄 تحديث الكابتشا", callback_data=f"refresh_captcha_{user_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🔐 <b>تحقق بشري مطلوب</b> {first_name}!\n\nلحماية المجموعة من البوتات، يرجى حل المسألة التالية (اكتب الرقم فقط):\n\n<b>{question}</b>\n\n⏳ لديك {AUTO_KICK_TIMEOUT} ثانية.",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔐 {first_name}، تم إرسال كابتشا إلى خاصك. أجب خلال {AUTO_KICK_TIMEOUT} ثانية."
        )
    except:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔐 {first_name}، أجب على الكابتشا التالية (اكتب الرقم فقط) في المجموعة:\n\n{question}\n\n⏳ لديك {AUTO_KICK_TIMEOUT} ثانية.",
            parse_mode="HTML",
            reply_markup=reply_markup
        )

    if context.job_queue:
        job = context.job_queue.run_once(
            callback=kick_if_no_captcha,
            when=AUTO_KICK_TIMEOUT,
            data={"chat_id": chat_id, "user_id": user_id, "first_name": first_name},
            name=f"captcha_{user_id}"
        )
        pending_captcha[user_id]["job"] = job
    else:
        print("⚠️ job_queue غير مفعل، لن يتم طرد المستخدم تلقائياً.")


async def kick_if_no_captcha(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    user_id = data["user_id"]
    first_name = data["first_name"]

    if user_id in pending_captcha:
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⛔ {first_name} تم طرده لعدم إجابة الكابتشا خلال {AUTO_KICK_TIMEOUT} ثانية."
            )
            await send_log(
                bot=context.bot,
                user=telegram.User(id=user_id, first_name=first_name, is_bot=False),
                chat_title="المجموعة",
                deleted_text="طرد بسبب عدم إجابة الكابتشا",
                violation_type="❌ طرد"
            )
        except Exception as e:
            print(f"فشل طرد العضو {user_id}: {e}")
        finally:
            if user_id in pending_captcha:
                del pending_captcha[user_id]


async def refresh_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("refresh_captcha_"):
        return

    user_id = int(data.split("_")[2])
    user = query.from_user
    if user.id != user_id:
        await query.edit_message_text("❌ هذا الزر ليس مخصصاً لك.")
        return

    if user_id not in pending_captcha:
        await query.edit_message_text("ℹ️ انتهت مهلة الكابتشا أو تم التحقق مسبقاً.")
        return

    question, new_answer = generate_captcha()
    pending_captcha[user_id]["answer"] = new_answer

    await query.edit_message_text(
        text=f"🔄 تم تحديث الكابتشا:\n\n{question}\n\nأجب بالرقم فقط.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث الكابتشا", callback_data=f"refresh_captcha_{user_id}")]
        ])
    )


async def handle_captcha_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id

    if user_id not in pending_captcha:
        return

    if await is_admin(context.bot, chat_id, user_id):
        return

    data = pending_captcha[user_id]
    correct_answer = data["answer"]
    first_name = data["first_name"]
    original_chat_id = data["chat_id"]

    try:
        await update.message.delete()
    except:
        pass

    try:
        user_answer = int(update.message.text.strip())
    except ValueError:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ يجب إدخال رقم صحيح. حاول مرة أخرى."
        )
        return

    if user_answer == correct_answer:
        if "job" in data and data["job"]:
            data["job"].schedule_removal()

        del pending_captcha[user_id]

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ تم التحقق بنجاح! أهلاً بك في المجموعة 🎉"
            )
        except:
            pass

        await context.bot.send_message(
            chat_id=original_chat_id,
            text=f"🎉 أهلاً وسهلاً بك {first_name} في المجموعة! تم التحقق بنجاح ✅"
        )

        await send_log(
            bot=context.bot,
            user=user,
            chat_title=update.effective_chat.title or "المجموعة",
            deleted_text="حل الكابتشا بنجاح وانضم إلى المجموعة",
            violation_type="🤖 كابتشا - نجاح"
        )

    else:
        attempts = data.get("attempts", 0) + 1
        data["attempts"] = attempts
        pending_captcha[user_id] = data

        if attempts >= CAPTCHA_ATTEMPTS:
            try:
                await context.bot.ban_chat_member(chat_id=original_chat_id, user_id=user_id)
                await context.bot.send_message(
                    chat_id=original_chat_id,
                    text=f"⛔ {first_name} تم طرده لتكرار الإجابة الخاطئة ({CAPTCHA_ATTEMPTS} محاولات)."
                )
                if "job" in data and data["job"]:
                    data["job"].schedule_removal()
                del pending_captcha[user_id]
                await send_log(
                    bot=context.bot,
                    user=user,
                    chat_title=update.effective_chat.title or "المجموعة",
                    deleted_text=f"طرد بسبب فشل الكابتشا {CAPTCHA_ATTEMPTS} مرات.",
                    violation_type="🤖 كابتشا - فشل"
                )
            except Exception as e:
                print(f"فشل الطرد: {e}")
        else:
            question, new_answer = generate_captcha()
            data["answer"] = new_answer
            pending_captcha[user_id] = data

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ إجابة خاطئة. حاول مرة أخرى ({attempts}/{CAPTCHA_ATTEMPTS}):\n\n{question}"
                )
            except:
                await context.bot.send_message(
                    chat_id=original_chat_id,
                    text=f"❌ {first_name} إجابة خاطئة. حاول مرة أخرى ({attempts}/{CAPTCHA_ATTEMPTS}):\n\n{question}"
                )


# ===================== الترحيب =====================

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    chat_title = chat.title or "المجموعة"

    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if bot_member.status not in ["administrator", "creator"]:
            return
    except:
        return

    for new_member in update.message.new_chat_members:
        user = new_member
        if user.id == context.bot.id:
            continue
        if await is_admin(context.bot, chat.id, user.id):
            continue

        await send_captcha(context, chat.id, user.id, user.first_name)

        await send_log(
            bot=context.bot,
            user=user,
            chat_title=chat_title,
            deleted_text="انضم العضو. جاري إرسال الكابتشا.",
            violation_type="👋 ترحيب (كابتشا)"
        )


async def goodbye_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    chat_title = chat.title or "المجموعة"
    user = update.message.left_chat_member

    if user.id == context.bot.id:
        return

    await context.bot.send_message(
        chat_id=chat.id,
        text=f"🚪 وداعاً {user.first_name}، نتمنى لك التوفيق! 🤍"
    )

    if user.id in pending_captcha:
        job = pending_captcha[user.id].get("job")
        if job:
            job.schedule_removal()
        del pending_captcha[user.id]

    await send_log(
        bot=context.bot,
        user=user,
        chat_title=chat_title,
        deleted_text="غادر العضو المجموعة.",
        violation_type="🚪 مغادرة"
    )


# ===================== أوامر المشرفين =====================

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ للمشرفين فقط.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ ارد على رسالة العضو.")
        return

    target = update.message.reply_to_message.from_user
    target_id = target.id
    if await is_admin(context.bot, chat_id, target_id):
        await update.message.reply_text("❌ لا يمكنك حظر مشرف.")
        return

    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
        await update.message.reply_text(f"✅ تم حظر {target.first_name}.")
        await send_log(
            bot=context.bot,
            user=update.effective_user,
            chat_title=update.effective_chat.title or "المجموعة",
            deleted_text=f"حظر {target.first_name}",
            violation_type="⚠️ إدارة (حظر)"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ فشل الحظر: {e}")


async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ للمشرفين فقط.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ استخدم: /unban [المعرف]")
        return

    try:
        target_id = int(args[0])
        await context.bot.unban_chat_member(chat_id=chat_id, user_id=target_id)
        await update.message.reply_text(f"✅ تم فك الحظر عن {target_id}.")
        await send_log(
            bot=context.bot,
            user=update.effective_user,
            chat_title=update.effective_chat.title or "المجموعة",
            deleted_text=f"فك حظر {target_id}",
            violation_type="⚠️ إدارة (فك حظر)"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ فشل فك الحظر: {e}")


async def reset_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ للمشرفين فقط.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ ارد على رسالة العضو.")
        return

    target = update.message.reply_to_message.from_user
    target_id = target.id
    reset_warnings_db(target_id)

    await update.message.reply_text(f"✅ تم إعادة تعيين مخالفات {target.first_name}.")
    await send_log(
        bot=context.bot,
        user=update.effective_user,
        chat_title=update.effective_chat.title or "المجموعة",
        deleted_text=f"إعادة تعيين مخالفات {target.first_name}",
        violation_type="🔄 إعادة تعيين مخالفات"
    )


async def toggle_lock_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ للمشرفين فقط.")
        return
    
    settings = get_group_settings(chat_id)
    new_value = not settings.get("lock_links", True)
    update_group_setting(chat_id, "lock_links", new_value)
    await update.message.reply_text(f"🔗 منع الروابط: {'مفعل ✅' if new_value else 'معطل ❌'}")


async def toggle_lock_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ للمشرفين فقط.")
        return
    
    settings = get_group_settings(chat_id)
    new_value = not settings.get("lock_media", False)
    update_group_setting(chat_id, "lock_media", new_value)
    await update.message.reply_text(f"🖼️ منع الميديا: {'مفعل ✅' if new_value else 'معطل ❌'}")


async def toggle_lock_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ للمشرفين فقط.")
        return
    
    settings = get_group_settings(chat_id)
    new_value = not settings.get("lock_forward", False)
    update_group_setting(chat_id, "lock_forward", new_value)
    await update.message.reply_text(f"↩️ منع التوجيه: {'مفعل ✅' if new_value else 'معطل ❌'}")


# ===================== الأوامر العامة =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>Raskov Security Bot v6.0</b>\n\n"
        "🔹 <b>القائمة البيضاء</b>: minepi.com, pi.app\n"
        "🔹 <b>مانع التكرار</b>: 5 رسائل / 4 ثوان = كتم 5د\n"
        "🔹 <b>منع الروابط</b>: مفعل ✅\n"
        "🔹 <b>منع الميديا</b>: معطل ❌\n"
        "🔹 <b>منع التوجيه</b>: معطل ❌\n"
        "🔹 <b>الترحيب</b>: كابتشا بشري 🔐\n"
        "🔹 <b>الكلمات الممنوعة</b>: مفعلة 🚫\n"
        "🔹 <b>عقوبات المخالفات</b>: 1=تحذير, 2=كتم 10د, 3=حظر 🔇\n"
        "🔹 <b>قاعدة البيانات</b>: مفعلة ✅\n"
        "🔹 <b>تقارير دورية</b>: أسبوعية 📊\n\n"
        "👑 <b>أوامر المشرفين</b>:\n"
        "/ban - رد على رسالة العضو\n"
        "/unban [ID]\n"
        "/resetwarnings - رد على رسالة العضو\n"
        "/locklinks - تبديل\n"
        "/lockmedia - تبديل\n"
        "/lockforward - تبديل\n"
        "/stats - عرض إحصائيات البوت 📊\n\n"
        "👤 <b>أوامر الأعضاء</b>:\n"
        "/rules - عرض قوانين المجموعة 📜\n"
        "/warnings - عرض مخالفاتك\n"
        "/testlog - اختبار اللوجات",
        parse_mode="HTML"
    )


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(GROUP_RULES, parse_mode="HTML")


async def warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = get_warnings(user_id)
    await update.message.reply_text(f"⚠️ عدد مخالفاتك: {count}/3")


async def test_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not LOG_CHANNEL_ID:
        await update.message.reply_text("❌ LOG_CHANNEL_ID غير مضبوط.")
        return
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text="🧪 رسالة اختبار ✅")
        await update.message.reply_text("✅ تم الإرسال إلى القناة.")
    except Exception as e:
        await update.message.reply_text(f"❌ فشل الإرسال: {e}")


# ===================== أمر الإحصائيات =====================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return

    if supabase:
        try:
            res = supabase.table("warnings").select("count").execute()
            total_warnings = sum(item.get("count", 0) for item in res.data) if res.data else 0
            res = supabase.table("warnings").select("user_id", count="exact").execute()
            total_users_with_warnings = res.count if res.count else 0
        except:
            total_warnings = sum(warnings_db.values())
            total_users_with_warnings = len(warnings_db)
    else:
        total_warnings = sum(warnings_db.values())
        total_users_with_warnings = len(warnings_db)

    total_banned = 0

    try:
        chat_members_count = await context.bot.get_chat_member_count(chat_id)
    except:
        chat_members_count = "غير معروف"

    stats_message = (
        "📊 <b>إحصائيات البوت</b>\n\n"
        f"👥 <b>عدد أعضاء المجموعة</b>: {chat_members_count}\n"
        f"⚠️ <b>إجمالي المخالفات</b>: {total_warnings}\n"
        f"👤 <b>الأعضاء المخالفين</b>: {total_users_with_warnings}\n"
        f"🚫 <b>المحظورين</b>: {total_banned}\n\n"
        "📌 يتم تحديث الإحصائيات تلقائياً مع كل مخالفة."
    )

    await update.message.reply_text(stats_message, parse_mode="HTML")


# ===================== التقارير الدورية =====================

async def send_weekly_report(bot):
    if not REPORT_CHANNEL_ID:
        print("⚠️ REPORT_CHANNEL_ID غير مضبوط، لن يتم إرسال التقرير.")
        return

    if supabase:
        try:
            res = supabase.table("warnings").select("count").execute()
            total_warnings = sum(item.get("count", 0) for item in res.data) if res.data else 0
            res = supabase.table("warnings").select("user_id", count="exact").execute()
            total_users_with_warnings = res.count if res.count else 0
        except:
            total_warnings = sum(warnings_db.values())
            total_users_with_warnings = len(warnings_db)
    else:
        total_warnings = sum(warnings_db.values())
        total_users_with_warnings = len(warnings_db)

    top_violator = None
    top_violator_count = 0
    for user_id, count in warnings_db.items():
        if count > top_violator_count:
            top_violator_count = count
            top_violator = f"ID: {user_id}"

    report_date = datetime.now().strftime("%A, %d %B %Y")
    week_start = (datetime.now() - timedelta(days=7)).strftime("%d/%m/%Y")
    week_end = datetime.now().strftime("%d/%m/%Y")

    report_message = (
        "📊 <b>التقرير الأسبوعي للمجموعة</b>\n"
        f"📅 <b>الأسبوع</b>: {week_start} - {week_end}\n"
        f"📌 <b>تاريخ التقرير</b>: {report_date}\n\n"
        f"🛡️ <b>إجمالي المخالفات</b>: {total_warnings}\n"
        f"👤 <b>الأعضاء المخالفين</b>: {total_users_with_warnings}\n"
    )
    
    if top_violator:
        report_message += f"🏆 <b>أكثر عضو مخالفة</b>: {top_violator} ({top_violator_count} مخالفات)\n"
    else:
        report_message += "🏆 <b>لا توجد مخالفات</b> هذا الأسبوع! 🎉\n"

    report_message += "\n📌 <i>يتم إنشاء هذا التقرير تلقائياً كل يوم أحد.</i>"

    try:
        await bot.send_message(chat_id=REPORT_CHANNEL_ID, text=report_message, parse_mode="HTML")
        print("✅ تم إرسال التقرير الأسبوعي بنجاح.")
    except Exception as e:
        print(f"❌ فشل إرسال التقرير: {e}")


async def weekly_report_job(context: ContextTypes.DEFAULT_TYPE):
    await send_weekly_report(context.bot)


# ===================== المعالج الرئيسي =====================

async def anti_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    chat_title = update.effective_chat.title or "المجموعة"
    user = update.effective_user

    # ✅ 1. منع الأعضاء الذين لم يحلوا الكابتشا من الكلام
    if user_id in pending_captcha:
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.first_name}، أنت في مرحلة التحقق البشري. أجب على الكابتشا أولاً."
            )
        except:
            pass
        return

    # 2. فحص التكرار
    if await check_flood(update, context):
        return

    # 3. تجاهل المشرفين
    if await is_admin(context.bot, chat_id, user_id):
        return

    # جلب الإعدادات
    settings = get_group_settings(chat_id)
    lock_links = settings.get("lock_links", True)
    lock_media = settings.get("lock_media", False)
    lock_forward = settings.get("lock_forward", False)

    # 4. فحص الميديا
    if lock_media and (update.message.photo or update.message.video):
        try:
            await update.message.delete()
        except:
            pass
        await send_log(
            bot=context.bot,
            user=user,
            chat_title=chat_title,
            deleted_text="[صورة أو فيديو]",
            violation_type="🖼️ صورة/فيديو (ممنوع)"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {user.first_name} ممنوع نشر الصور والفيديوهات."
        )
        return

    # 5. فحص الرسائل المعاد توجيهها
    if lock_forward and update.message.forward_date:
        try:
            await update.message.delete()
        except:
            pass
        await send_log(
            bot=context.bot,
            user=user,
            chat_title=chat_title,
            deleted_text="[رسالة معاد توجيهها]",
            violation_type="↩️ رسالة معاد توجيهها (ممنوع)"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {user.first_name} ممنوع إعادة توجيه الرسائل."
        )
        return

    # 6. فحص النص
    if not update.message.text:
        return

    original_text = update.message.text

    # 7. فحص الكلمات الممنوعة
    has_forbidden, found_word = contains_forbidden_word(original_text)
    if has_forbidden:
        try:
            await update.message.delete()
        except:
            pass
        
        await send_log(
            bot=context.bot,
            user=user,
            chat_title=chat_title,
            deleted_text=original_text,
            violation_type=f"🚫 كلمة ممنوعة: '{found_word}'"
        )

        count = increment_warning(user_id, user.first_name)

        if count == 1:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.first_name} تحذير 1/3 - ممنوع استخدام الكلمات الممنوعة ('{found_word}')."
            )
        elif count == 2:
            mute_success = await mute_user(context.bot, chat_id, user_id, MUTE_DURATION_SECOND)
            if mute_success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {user.first_name} تحذير 2/3 - تم كتمك لمدة {MUTE_DURATION_SECOND} دقائق لاستخدام كلمات ممنوعة."
                )
                await send_log(
                    bot=context.bot,
                    user=user,
                    chat_title=chat_title,
                    deleted_text=f"كتم {MUTE_DURATION_SECOND} دقائق (كلمة ممنوعة)",
                    violation_type="🔇 كتم 10 دقائق"
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {user.first_name} تحذير 2/3 - التحذير الأخير. (فشل الكتم)"
                )
        elif count >= 3:
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 تم حظر {user.first_name} تلقائياً (3/3)."
                )
                reset_warnings_db(user_id)
            except Exception as e:
                await send_log(
                    bot=context.bot,
                    user=user,
                    chat_title=chat_title,
                    deleted_text=f"فشل الحظر: {e}",
                    violation_type="⚠️ خطأ صلاحيات"
                )
        return

    # 8. فحص الروابط والأرقام والمحافظ
    phone_cleaned = re.sub(r'[\s\-\(\)]', '', original_text)
    wallet_cleaned = re.sub(r'\s', '', original_text)
    link_cleaned = clean_obfuscated_text(original_text)

    is_violation = False
    violation_type = "رابط غير مسموح"

    if WALLET_PATTERN.search(wallet_cleaned):
        is_violation = True
        violation_type = "محفظة رقمية"
    elif not is_violation and PHONE_PATTERN.search(phone_cleaned):
        is_violation = True
        violation_type = "رقم هاتف"
    elif not is_violation and lock_links and LINK_PATTERN.search(link_cleaned):
        is_allowed = any(domain in link_cleaned.lower() for domain in ALLOWED_DOMAINS)
        if not is_allowed:
            is_violation = True
            violation_type = "رابط غير مسموح" if original_text == link_cleaned else "رابط غير مسموح (ملتف)"

    if is_violation:
        try:
            await update.message.delete()
        except Exception as e:
            print(f"Delete error: {e}")
            return

        await send_log(
            bot=context.bot,
            user=user,
            chat_title=chat_title,
            deleted_text=original_text,
            violation_type=violation_type
        )

        log_violation(user_id, chat_id, violation_type, original_text)

        count = increment_warning(user_id, user.first_name)

        if count == 1:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.first_name} تحذير 1/3 - ممنوع النشر المخالف."
            )
        elif count == 2:
            mute_success = await mute_user(context.bot, chat_id, user_id, MUTE_DURATION_SECOND)
            if mute_success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {user.first_name} تحذير 2/3 - تم كتمك لمدة {MUTE_DURATION_SECOND} دقائق. المخالفة الثالثة = حظر."
                )
                await send_log(
                    bot=context.bot,
                    user=user,
                    chat_title=chat_title,
                    deleted_text=f"كتم {MUTE_DURATION_SECOND} دقائق (المخالفة الثانية)",
                    violation_type="🔇 كتم 10 دقائق"
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {user.first_name} تحذير 2/3 - التحذير الأخير. (فشل الكتم)"
                )
        elif count >= 3:
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 تم حظر {user.first_name} تلقائياً (3/3)."
                )
                reset_warnings_db(user_id)
            except Exception as e:
                await send_log(
                    bot=context.bot,
                    user=user,
                    chat_title=chat_title,
                    deleted_text=f"فشل الحظر: {e}",
                    violation_type="⚠️ خطأ صلاحيات"
                )


# ===================== تشغيل البوت =====================

def main():
    app = Application.builder().token(TOKEN).build()

    # أوامر المشرفين
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("resetwarnings", reset_warnings))
    app.add_handler(CommandHandler("locklinks", toggle_lock_links))
    app.add_handler(CommandHandler("lockmedia", toggle_lock_media))
    app.add_handler(CommandHandler("lockforward", toggle_lock_forward))
    app.add_handler(CommandHandler("stats", stats))

    # الأوامر العامة
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("warnings", warnings))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("testlog", test_log))

    # معالجات الأحداث
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, goodbye_member))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_captcha_answer))
    app.add_handler(CallbackQueryHandler(refresh_captcha, pattern="^refresh_captcha_"))

    # المعالج الرئيسي (يأتي أخيراً)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, anti_link))

    # جدولة التقارير
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        weekly_report_job,
        CronTrigger(day_of_week='sun', hour=12, minute=0),
        args=[app]
    )
    scheduler.start()
    print("📊 تم جدولة التقارير الأسبوعية (كل يوم أحد الساعة 12:00)")

    print("🤖 Raskov Security Bot يعمل الآن مع Supabase والكابتشا...")
    app.run_polling()


if __name__ == "__main__":
    main()
