import os
import re
from datetime import datetime, timedelta
import telegram

# ===================== استيراد Supabase =====================
from supabase import create_client, Client

# ===================== استيراد جدولة المهام =====================
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, WebAppInfo, ReplyKeyboardMarkup
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

# ===================== القوانين المحسّنة =====================
GROUP_RULES = (
    "📜 <b>قوانين المجموعة</b> 📜\n\n"
    "1️⃣ <b>الروابط</b>: ممنوع نشر الروابط نهائياً، ما عدا (minepi.com, pi.app).\n"
    "2️⃣ <b>الأرقام والمحافظ</b>: ممنوع نشر أرقام الهواتف أو المحافظ الرقمية.\n"
    "3️⃣ <b>التكرار</b>: ممنوع إرسال أكثر من 5 رسائل في 4 ثوانٍ (سبام).\n"
    "4️⃣ <b>الميديا</b>: ممنوع نشر الصور أو الفيديوهات غير المفيدة.\n"
    "5️⃣ <b>الكلمات الممنوعة</b>: ممنوع استخدام كلمات النصب والاحتيال والسبام.\n"
    "6️⃣ <b>الاحترام</b>: احترام جميع الأعضاء والابتعاد عن الشتائم.\n\n"
    "⚠️ <b>نظام العقوبات</b>:\n"
    "• <b>المخالفة الأولى</b>: تحذير 📢\n"
    "• <b>المخالفة الثانية</b>: كتم لمدة 10 دقائق 🔇\n"
    "• <b>المخالفة الثالثة</b>: حظر تلقائي 🚫\n\n"
    "👆 اضغط على زر 'موافق' لتأكيد قبولك القوانين."
)

# ===================== إعدادات الحماية =====================
AUTO_KICK_TIMEOUT = 60
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
pending_approvals = {}


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


# ===================== دوال إحصائيات المجموعة (جديدة) =====================

def update_group_stats(chat_id: int, members: int, violations: int, bans: int):
    """تحديث أو إدراج إحصائيات المجموعة في Supabase"""
    if not supabase:
        return
    try:
        supabase.table("group_stats").upsert({
            "chat_id": chat_id,
            "members_count": members,
            "violations_count": violations,
            "bans_count": bans,
            "updated_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"⚠️ خطأ في تحديث إحصائيات المجموعة: {e}")


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
        "⚠️ تحذير يدوي": "⚠️",
        "🔇 كتم يدوي": "🔇",
        "👢 طرد": "👢",
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


async def unmute_user(bot, chat_id, user_id):
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
        )
        return True
    except Exception as e:
        print(f"❌ فشل فك الكتم: {e}")
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
                text=f"🔇 <b>{update.effective_user.first_name}</b> تم كتمك لمدة {MUTE_DURATION} دقائق بسبب التكرار السريع للرسائل. يرجى التوقف عن السبام."
            )
        try:
            await update.message.delete()
        except:
            pass
        return True
    return False


# ===================== الترحيب والموافقة =====================

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

        keyboard = [[InlineKeyboardButton("✅ أوافق على القوانين", callback_data=f"agree_rules_{user.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        welcome_text = (
            f"👋 مرحباً <b>{user.first_name}</b>!\n\n"
            f"📌 <b>مجتمع Pi Network</b> يرحب بك. يرجى قراءة القوانين والموافقة عليها للانضمام.\n\n"
            f"{GROUP_RULES}"
        )

        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=welcome_text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            await update.message.reply_text(f"👋 مرحباً {user.first_name}! تم إرسال القوانين إلى خاصك. يرجى الموافقة عليها.")
        except:
            msg = await context.bot.send_message(
                chat_id=chat.id,
                text=welcome_text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            try:
                await context.bot.pin_chat_message(chat.id, msg.message_id, disable_notification=True)
            except:
                pass

        if context.job_queue:
            job = context.job_queue.run_once(
                callback=kick_non_agreed,
                when=AUTO_KICK_TIMEOUT,
                data={"chat_id": chat.id, "user_id": user.id, "username": user.first_name},
                name=f"kick_{user.id}"
            )
            pending_approvals[user.id] = job

        await send_log(
            bot=context.bot,
            user=user,
            chat_title=chat_title,
            deleted_text=f"انضم العضو. في انتظار الموافقة على القوانين",
            violation_type="👋 ترحيب"
        )


async def kick_non_agreed(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    user_id = data["user_id"]
    username = data.get("username", f"ID:{user_id}")

    if user_id in pending_approvals:
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⛔ {username} تم طرده لعدم الموافقة على القوانين خلال المهلة المحددة."
            )
            await send_log(
                bot=context.bot,
                user=telegram.User(id=user_id, first_name=username, is_bot=False),
                chat_title="المجموعة",
                deleted_text=f"طرد {username} لعدم الموافقة",
                violation_type="❌ طرد"
            )
            del pending_approvals[user_id]
        except Exception as e:
            print(f"فشل طرد العضو {user_id}: {e}")


async def handle_rules_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not data.startswith("agree_rules_"):
        return

    user_id = int(data.split("_")[2])
    user = query.from_user
    if user.id != user_id:
        await query.edit_message_text("❌ هذا الزر ليس مخصصاً لك.")
        return

    if user_id in pending_approvals:
        job = pending_approvals[user_id]
        job.schedule_removal()
        del pending_approvals[user_id]

        await query.edit_message_text(
            text=f"✅ {user.first_name}، تم تأكيد موافقتك على القوانين!\nأهلاً وسهلاً بك في المجموعة 🎉",
            parse_mode="HTML"
        )

        chat_id = update.effective_chat.id
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 أهلاً وسهلاً بك <b>{user.first_name}</b> في المجموعة! استمتع بوقتك ونتمنى لك تجربة مفيدة 🤍",
            parse_mode="HTML"
        )
        try:
            await context.bot.unpin_chat_message(chat_id=chat_id)
        except:
            pass

        await send_log(
            bot=context.bot,
            user=user,
            chat_title=update.effective_chat.title or "المجموعة",
            deleted_text="وافق العضو على القوانين وانضم بنجاح.",
            violation_type="👋 ترحيب (موافقة)"
        )
    else:
        await query.edit_message_text("ℹ️ انتهت المهلة أو تمت الموافقة مسبقاً.")


# ===================== رسالة الوداع (محسّنة ومؤكدة) =====================

async def goodbye_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة وداع عند مغادرة عضو - تم إصلاحها"""
    # التأكد من وجود عضو غادر
    if not update.message.left_chat_member:
        return

    chat = update.effective_chat
    chat_title = chat.title or "المجموعة"
    user = update.message.left_chat_member

    # تجاهل مغادرة البوت نفسه
    if user.id == context.bot.id:
        return

    # رسالة وداع محسّنة
    goodbye_text = (
        f"🚪 <b>وداعاً {user.first_name}</b>\n\n"
        f"📌 نتمنى لك التوفيق في رحلتك مع Pi Network.\n"
        f"🌟 أبوابنا مفتوحة لك دائماً إذا أردت العودة.\n"
        f"🤍 شكراً لك على وقتك معنا."
    )

    await context.bot.send_message(
        chat_id=chat.id,
        text=goodbye_text,
        parse_mode="HTML"
    )

    # تنظيف من قائمة الانتظار إذا كان موجوداً
    if user.id in pending_approvals:
        job = pending_approvals[user.id]
        job.schedule_removal()
        del pending_approvals[user.id]

    await send_log(
        bot=context.bot,
        user=user,
        chat_title=chat_title,
        deleted_text="غادر العضو المجموعة.",
        violation_type="🚪 مغادرة"
    )


# ===================== أوامر المشرفين الأساسية =====================

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ ارد على رسالة العضو المستهدف.")
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
        await update.message.reply_text("⚠️ استخدم: /unban [معرف المستخدم]")
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


# ===================== الأوامر اليدوية (محسّنة) =====================

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ ارد على رسالة العضو المستهدف.")
        return

    target = update.message.reply_to_message.from_user
    target_id = target.id

    if await is_admin(context.bot, chat_id, target_id):
        await update.message.reply_text("❌ لا يمكنك تحذير مشرف.")
        return

    count = increment_warning(target_id, target.first_name)

    await update.message.reply_text(
        f"⚠️ تم تحذير <b>{target.first_name}</b> (المخالفة {count}/3).\n"
        f"📌 المخالفة الثالثة تؤدي إلى حظر تلقائي.",
        parse_mode="HTML"
    )

    await send_log(
        bot=context.bot,
        user=update.effective_user,
        chat_title=update.effective_chat.title or "المجموعة",
        deleted_text=f"تحذير يدوي لـ {target.first_name} (المخالفة {count})",
        violation_type="⚠️ تحذير يدوي"
    )


async def mute_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ ارد على رسالة العضو المستهدف.")
        return

    target = update.message.reply_to_message.from_user
    target_id = target.id

    if await is_admin(context.bot, chat_id, target_id):
        await update.message.reply_text("❌ لا يمكنك كتم مشرف.")
        return

    args = context.args
    duration = 5
    if args:
        try:
            duration = int(args[0])
            if duration < 1:
                duration = 1
            if duration > 60:
                duration = 60
        except ValueError:
            await update.message.reply_text("⚠️ مدة غير صحيحة، سيتم استخدام 5 دقائق.")

    success = await mute_user(context.bot, chat_id, target_id, duration)
    if success:
        await update.message.reply_text(
            f"🔇 تم كتم <b>{target.first_name}</b> لمدة {duration} دقائق.\n"
            f"📌 يمكن فك الكتم باستخدام /unmute.",
            parse_mode="HTML"
        )
        await send_log(
            bot=context.bot,
            user=update.effective_user,
            chat_title=update.effective_chat.title or "المجموعة",
            deleted_text=f"كتم يدوي لـ {target.first_name} لمدة {duration} دقائق",
            violation_type="🔇 كتم يدوي"
        )
    else:
        await update.message.reply_text("❌ فشل الكتم. تأكد من صلاحيات البوت.")


async def unmute_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ ارد على رسالة العضو المستهدف.")
        return

    target = update.message.reply_to_message.from_user
    target_id = target.id

    success = await unmute_user(context.bot, chat_id, target_id)
    if success:
        await update.message.reply_text(f"✅ تم فك الكتم عن <b>{target.first_name}</b>.", parse_mode="HTML")
        await send_log(
            bot=context.bot,
            user=update.effective_user,
            chat_title=update.effective_chat.title or "المجموعة",
            deleted_text=f"فك كتم يدوي لـ {target.first_name}",
            violation_type="⚠️ إدارة (فك كتم)"
        )
    else:
        await update.message.reply_text("❌ فشل فك الكتم.")


async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ ارد على رسالة العضو المستهدف.")
        return

    target = update.message.reply_to_message.from_user
    target_id = target.id

    if await is_admin(context.bot, chat_id, target_id):
        await update.message.reply_text("❌ لا يمكنك طرد مشرف.")
        return

    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
        await context.bot.unban_chat_member(chat_id=chat_id, user_id=target_id)
        await update.message.reply_text(f"👢 تم طرد <b>{target.first_name}</b> من المجموعة.", parse_mode="HTML")
        await send_log(
            bot=context.bot,
            user=update.effective_user,
            chat_title=update.effective_chat.title or "المجموعة",
            deleted_text=f"طرد {target.first_name}",
            violation_type="👢 طرد"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ فشل الطرد: {e}")


# ===================== الأوامر العامة =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id  # ✅ جلب معرف المجموعة تلقائياً

    # ✅ زر فتح التطبيق مع تمرير chat_id في الرابط
    web_app_button = KeyboardButton(
        text="📊 فتح لوحة Pi",
        web_app=WebAppInfo(url=f"https://crb2usmh-crypto.github.io/Pi-Dashboard/?chat_id={chat_id}")
    )
    reply_markup = ReplyKeyboardMarkup([[web_app_button]], resize_keyboard=True)

    await update.message.reply_text(
        "🛡️ <b>Raskov Security Bot v6.0</b>\n\n"
        "🔹 <b>القائمة البيضاء</b>: minepi.com, pi.app\n"
        "🔹 <b>مانع التكرار</b>: 5 رسائل / 4 ثوان = كتم 5د\n"
        "🔹 <b>منع الروابط</b>: مفعل ✅\n"
        "🔹 <b>منع الميديا</b>: معطل ❌\n"
        "🔹 <b>منع التوجيه</b>: معطل ❌\n"
        "🔹 <b>الترحيب</b>: مفعل ✅\n"
        "🔹 <b>الكلمات الممنوعة</b>: مفعلة 🚫\n"
        "🔹 <b>عقوبات المخالفات</b>: 1=تحذير, 2=كتم 10د, 3=حظر 🔇\n"
        "🔹 <b>قاعدة البيانات</b>: مفعلة ✅\n"
        "🔹 <b>تقارير دورية</b>: أسبوعية 📊\n\n"
        "👑 <b>أوامر المشرفين</b>:\n"
        "/ban - حظر عضو (بالرد)\n"
        "/unban [ID] - فك حظر عضو\n"
        "/resetwarnings - إعادة تعيين مخالفات (بالرد)\n"
        "/locklinks - تشغيل/إيقاف منع الروابط\n"
        "/lockmedia - تشغيل/إيقاف منع الميديا\n"
        "/lockforward - تشغيل/إيقاف منع التوجيه\n"
        "/stats - عرض إحصائيات البوت 📊\n"
        "/warn - تحذير يدوي (بالرد)\n"
        "/mute [دقائق] - كتم يدوي (بالرد)\n"
        "/kick - طرد عضو (بالرد)\n"
        "/unmute - فك الكتم (بالرد)\n\n"
        "👤 <b>أوامر الأعضاء</b>:\n"
        "/rules - عرض قوانين المجموعة 📜\n"
        "/warnings - عرض مخالفاتك\n"
        "/testlog - اختبار اللوجات\n\n"
        "📊 <b>لوحة Pi Dashboard</b>:\n"
        "اضغط على الزر أدناه لفتح لوحة التحكم الخاصة بهذه المجموعة.",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(GROUP_RULES, parse_mode="HTML")


async def warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = get_warnings(user_id)
    await update.message.reply_text(
        f"⚠️ <b>عدد مخالفاتك: {count}/3</b>\n\n"
        f"📌 المخالفة الثالثة تؤدي إلى حظر تلقائي.\n"
        f"📖 راجع القوانين عبر /rules لتجنب العقوبات.",
        parse_mode="HTML"
    )


async def test_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not LOG_CHANNEL_ID:
        await update.message.reply_text("❌ LOG_CHANNEL_ID غير مضبوط.")
        return
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text="🧪 رسالة اختبار ✅")
        await update.message.reply_text("✅ تم الإرسال إلى القناة.")
    except Exception as e:
        await update.message.reply_text(f"❌ فشل الإرسال: {e}")


# ===================== أمر الإحصائيات (محسّن) =====================

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


# ===================== تحديث إحصائيات المجموعات (جديد) =====================

async def update_all_group_stats(context: ContextTypes.DEFAULT_TYPE):
    """تحديث إحصائيات جميع المجموعات التي يديرها البوت"""
    if not supabase:
        return
    try:
        res = supabase.table("group_settings").select("chat_id").execute()
        if not res.data:
            return
        for item in res.data:
            chat_id = item.get("chat_id")
            if chat_id:
                try:
                    members = await context.bot.get_chat_member_count(chat_id)
                    viol_res = supabase.table("violations_log").select("id", count="exact").eq("chat_id", chat_id).execute()
                    violations = viol_res.count if viol_res.count else 0
                    ban_res = supabase.table("violations_log").select("id", count="exact").eq("chat_id", chat_id).eq("type", "🚫 حظر").execute()
                    bans = ban_res.count if ban_res.count else 0
                    update_group_stats(chat_id, members, violations, bans)
                except Exception as e:
                    print(f"⚠️ فشل تحديث إحصائيات المجموعة {chat_id}: {e}")
    except Exception as e:
        print(f"⚠️ خطأ في جلب المجموعات: {e}")


# ===================== المعالج الرئيسي =====================

async def anti_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    chat_title = update.effective_chat.title or "المجموعة"
    user = update.effective_user

    # 1. منع الأعضاء غير الموافقين على القوانين
    if user_id in pending_approvals:
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ <b>{user.first_name}</b>، أنت في مرحلة الموافقة على القوانين. يرجى الضغط على زر 'موافق' في الرسالة المرسلة إليك.",
                parse_mode="HTML"
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
            text=f"⚠️ <b>{user.first_name}</b>، ممنوع نشر الصور والفيديوهات في هذه المجموعة.",
            parse_mode="HTML"
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
            text=f"⚠️ <b>{user.first_name}</b>، ممنوع إعادة توجيه الرسائل في هذه المجموعة.",
            parse_mode="HTML"
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
                text=f"⚠️ <b>{user.first_name}</b> تحذير 1/3 - ممنوع استخدام الكلمات الممنوعة ('{found_word}').\n📖 راجع القوانين عبر /rules.",
                parse_mode="HTML"
            )
        elif count == 2:
            mute_success = await mute_user(context.bot, chat_id, user_id, MUTE_DURATION_SECOND)
            if mute_success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ <b>{user.first_name}</b> تحذير 2/3 - تم كتمك لمدة {MUTE_DURATION_SECOND} دقائق لاستخدام كلمات ممنوعة.\n📖 المخالفة الثالثة تؤدي إلى حظر تلقائي.",
                    parse_mode="HTML"
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
                    text=f"⚠️ <b>{user.first_name}</b> تحذير 2/3 - التحذير الأخير. (فشل الكتم، تأكد من صلاحيات البوت)",
                    parse_mode="HTML"
                )
        elif count >= 3:
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 <b>{user.first_name}</b> تم حظرك تلقائياً (3/3).\n📌 القوانين واضحة، نتمنى لك التوفيق في المستقبل.",
                    parse_mode="HTML"
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
                text=f"⚠️ <b>{user.first_name}</b> تحذير 1/3 - ممنوع نشر المحتوى المخالف.\n📖 راجع القوانين عبر /rules.",
                parse_mode="HTML"
            )
        elif count == 2:
            mute_success = await mute_user(context.bot, chat_id, user_id, MUTE_DURATION_SECOND)
            if mute_success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ <b>{user.first_name}</b> تحذير 2/3 - تم كتمك لمدة {MUTE_DURATION_SECOND} دقائق.\n📌 المخالفة الثالثة تؤدي إلى حظر تلقائي.",
                    parse_mode="HTML"
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
                    text=f"⚠️ <b>{user.first_name}</b> تحذير 2/3 - التحذير الأخير. (فشل الكتم، تأكد من صلاحيات البوت)",
                    parse_mode="HTML"
                )
        elif count >= 3:
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 <b>{user.first_name}</b> تم حظرك تلقائياً (3/3).\n📌 القوانين واضحة، نتمنى لك التوفيق في المستقبل.",
                    parse_mode="HTML"
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

    # أوامر المشرفين الأساسية
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("resetwarnings", reset_warnings))
    app.add_handler(CommandHandler("locklinks", toggle_lock_links))
    app.add_handler(CommandHandler("lockmedia", toggle_lock_media))
    app.add_handler(CommandHandler("lockforward", toggle_lock_forward))
    app.add_handler(CommandHandler("stats", stats))

    # أوامر يدوية
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("mute", mute_manual))
    app.add_handler(CommandHandler("unmute", unmute_manual))
    app.add_handler(CommandHandler("kick", kick_user))

    # الأوامر العامة
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("warnings", warnings))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("testlog", test_log))

    # معالجات الأحداث
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, goodbye_member))
    app.add_handler(CallbackQueryHandler(handle_rules_approval, pattern="^agree_rules_"))

    # المعالج الرئيسي
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, anti_link))

    # جدولة المهام
    scheduler = AsyncIOScheduler()
    
    # التقارير الأسبوعية (كل يوم أحد الساعة 12:00)
    scheduler.add_job(
        weekly_report_job,
        CronTrigger(day_of_week='sun', hour=12, minute=0),
        args=[app]
    )
    print("📊 تم جدولة التقارير الأسبوعية (كل يوم أحد الساعة 12:00)")

    # تحديث إحصائيات المجموعات (كل ساعة عند الدقيقة 0)
    scheduler.add_job(
        update_all_group_stats,
        CronTrigger(minute=0),
        args=[app]
    )
    print("📈 تم جدولة تحديث إحصائيات المجموعات (كل ساعة)")

    scheduler.start()

    print("🤖 Raskov Security Bot يعمل الآن مع جميع الميزات والرسائل المحسّنة...")
    app.run_polling()


if __name__ == "__main__":
    main()
