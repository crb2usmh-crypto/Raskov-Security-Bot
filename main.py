import os
import re
import random
from datetime import datetime, timedelta
import telegram

# ===================== استيراد Supabase =====================
from supabase import create_client, Client

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
    "⚠️ نظام العقوبات قابل للتخصيص عبر أوامر المشرفين.\n"
    "🔇 المخالفة الثانية = كتم (قابل للتعديل).\n"
    "🛑 الحسابات الجديدة (أقل من يوم) = حظر فوري.\n"
    "👆 اضغط على زر 'موافق' لتأكيد قبولك القوانين."
)

# ===================== 🚫 الكلمات الممنوعة =====================
FORBIDDEN_WORDS = [
    "نصب", "احتيال", "سبام", "إعلان", "دعاية", "مؤامرة", "تزوير",
    "اختراق", "حساب مميز", "أرباح سريعة", "استثمار مضمون", "ثروة",
    "scam", "spam", "hack", "cheat", "fraud", "phishing", "promo",
    "advertisement", "click here", "earn money", "free money",
    "investment", "guaranteed profit", "بيع باي", "شراء باي", "سعر باي", "تداول باي",
]

# ===================== إعدادات الحماية الأساسية (كاحتياطي) =====================
AUTO_KICK_TIMEOUT = 60          # سيتم استبدالها بإعدادات المجموعة
FLOOD_LIMIT = 5
FLOOD_TIME = 4
MUTE_DURATION = 5               # مدة كتم السبام (ثابتة)
MIN_ACCOUNT_AGE_DAYS = 1

# ===================== القائمة البيضاء =====================
ALLOWED_DOMAINS = ["minepi.com", "pi.app"]

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
    """جلب جميع إعدادات المجموعة (بما فيها الجديدة)"""
    default = {
        "lock_links": True,
        "lock_media": False,
        "lock_forward": False,
        "max_warnings": 3,
        "mute_duration": 10,
        "captcha_timeout": 60,
    }
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
                "max_warnings": data.get("max_warnings", 3),
                "mute_duration": data.get("mute_duration", 10),
                "captcha_timeout": data.get("captcha_timeout", 60),
            }
        else:
            # إنشاء سجل افتراضي مع الإعدادات الجديدة
            supabase.table("group_settings").insert({
                "chat_id": chat_id,
                "lock_links": True,
                "lock_media": False,
                "lock_forward": False,
                "max_warnings": 3,
                "mute_duration": 10,
                "captcha_timeout": 60,
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


# ===================== دوال الإحصائيات =====================

def get_total_violations(chat_id: int) -> int:
    if not supabase:
        return 0
    try:
        res = supabase.table("violations_log").select("id", count="exact").eq("chat_id", chat_id).execute()
        return res.count if res.count else 0
    except Exception as e:
        print(f"⚠️ خطأ في جلب إجمالي المخالفات: {e}")
        return 0


def get_violations_by_type(chat_id: int, violation_type: str) -> int:
    if not supabase:
        return 0
    try:
        res = supabase.table("violations_log").select("id", count="exact").eq("chat_id", chat_id).eq("type", violation_type).execute()
        return res.count if res.count else 0
    except Exception as e:
        print(f"⚠️ خطأ في جلب المخالفات حسب النوع: {e}")
        return 0


def get_total_warnings() -> int:
    if not supabase:
        return 0
    try:
        data = supabase.table("warnings").select("count").execute()
        total = sum(item.get("count", 0) for item in data.data) if data.data else 0
        return total
    except Exception as e:
        print(f"⚠️ خطأ في جلب إجمالي التحذيرات: {e}")
        return 0


def get_users_with_warnings() -> int:
    if not supabase:
        return 0
    try:
        res = supabase.table("warnings").select("user_id", count="exact").execute()
        return res.count if res.count else 0
    except Exception as e:
        print(f"⚠️ خطأ في جلب عدد المستخدمين: {e}")
        return 0


# ===================== دوال المساعدة الأساسية =====================

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
        "🔇 كتم": "🔇",
        "🛑 حساب جديد (ممنوع)": "🛑",
        "🚫 كلمة ممنوعة": "🚫",
        "🤖 كابتشا - نجاح": "✅",
        "🤖 كابتشا - فشل": "❌",
        "⚙️ إعدادات": "⚙️",
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
    # ✅ جلب الإعدادات المخصصة للمجموعة
    settings = get_group_settings(chat_id)
    captcha_timeout = settings.get("captcha_timeout", 60)

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
            text=f"🤖 تحقق بشري مطلوب! أجب على السؤال التالي (اكتب الرقم فقط):\n\n{question}\n\n⏳ لديك {captcha_timeout} ثانية.",
            reply_markup=reply_markup
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔐 {first_name}، تم إرسال كابتشا إلى خاصك. أجب خلال {captcha_timeout} ثانية."
        )
    except:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔐 {first_name}، أجب على الكابتشا التالية (اكتب الرقم فقط) في المجموعة:\n\n{question}\n\n⏳ لديك {captcha_timeout} ثانية.",
            reply_markup=reply_markup
        )

    if context.job_queue:
        job = context.job_queue.run_once(
            callback=kick_if_no_captcha,
            when=captcha_timeout,
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
                text=f"⛔ {first_name} تم طرده لعدم إجابة الكابتشا."
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
                text="✅ تم التحقق بنجاح! سيتم الآن عرض قوانين المجموعة."
            )
        except:
            pass

        keyboard = [[InlineKeyboardButton("✅ أوافق على القوانين", callback_data=f"agree_rules_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=GROUP_RULES,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            await context.bot.send_message(
                chat_id=original_chat_id,
                text=f"👋 {first_name}، تم التحقق بنجاح! تم إرسال القوانين إلى خاصك. وافق عليها للانضمام."
            )
        except:
            msg = await context.bot.send_message(
                chat_id=original_chat_id,
                text=f"👋 مرحباً {first_name}!\n\n{GROUP_RULES}",
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            try:
                await context.bot.pin_chat_message(original_chat_id, msg.message_id, disable_notification=True)
            except:
                pass

        if context.job_queue:
            job = context.job_queue.run_once(
                callback=kick_non_agreed,
                when=60,  # هذه المهلة لا تزال ثابتة، يمكنك جعلها قابلة للتخصيص لاحقاً
                data={"chat_id": original_chat_id, "user_id": user_id, "username": first_name},
                name=f"approval_{user_id}"
            )
            pending_approvals[user_id] = job
        else:
            print("⚠️ job_queue غير مفعل، لن يتم طرد المستخدم تلقائياً.")

        await send_log(
            bot=context.bot,
            user=user,
            chat_title="المجموعة",
            deleted_text="حل الكابتشا بنجاح، في انتظار الموافقة على القوانين",
            violation_type="🤖 كابتشا - نجاح"
        )

    else:
        attempts = data.get("attempts", 0) + 1
        data["attempts"] = attempts
        pending_captcha[user_id] = data

        if attempts >= 3:
            try:
                await context.bot.ban_chat_member(chat_id=original_chat_id, user_id=user_id)
                await context.bot.send_message(
                    chat_id=original_chat_id,
                    text=f"⛔ {first_name} تم طرده لتكرار الإجابة الخاطئة (3 محاولات)."
                )
                if "job" in data and data["job"]:
                    data["job"].schedule_removal()
                del pending_captcha[user_id]
                await send_log(
                    bot=context.bot,
                    user=user,
                    chat_title="المجموعة",
                    deleted_text="طرد بسبب فشل الكابتشا 3 مرات.",
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
                    text=f"❌ إجابة خاطئة. حاول مرة أخرى ({attempts}/3):\n\n{question}"
                )
            except:
                await context.bot.send_message(
                    chat_id=original_chat_id,
                    text=f"❌ {first_name} إجابة خاطئة. حاول مرة أخرى ({attempts}/3):\n\n{question}"
                )


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
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث الكابتشا", callback_data=f"refresh_captcha_{user_id}")]
        ])
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

        try:
            account_age_days = (datetime.now() - user.date).days
            if account_age_days < MIN_ACCOUNT_AGE_DAYS:
                await context.bot.ban_chat_member(chat.id, user.id)
                await context.bot.send_message(
                    chat.id,
                    text=f"🛑 {user.first_name} تم طرده لأن حسابه جديد (عمره أقل من {MIN_ACCOUNT_AGE_DAYS} يوم)."
                )
                await send_log(
                    bot=context.bot,
                    user=user,
                    chat_title=chat_title,
                    deleted_text=f"حساب جديد (عمره {account_age_days} يوم) - تم الطرد",
                    violation_type="🛑 حساب جديد (ممنوع)"
                )
                continue
        except:
            pass

        await send_captcha(context, chat.id, user.id, user.first_name)
        await send_log(
            bot=context.bot,
            user=user,
            chat_title=chat_title,
            deleted_text="انضم العضو. جاري إرسال الكابتشا.",
            violation_type="👋 ترحيب (كابتشا)"
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
                text=f"⛔ {username} تم طرده لعدم الموافقة على القوانين."
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
            text=f"✅ {user.first_name}، تم تأكيد موافقتك!\nأهلاً وسهلاً بك 🎉",
            parse_mode="HTML"
        )

        chat_id = update.effective_chat.id
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 أهلاً وسهلاً بك {user.first_name} في المجموعة!"
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


# ===================== أوامر المشرفين (بما فيها الجديدة) =====================

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


# ===================== الأوامر الجديدة لإدارة الإعدادات =====================

async def set_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحديد عدد التحذيرات قبل الحظر التلقائي"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("⚠️ استخدم: /setwarnings [عدد]\nمثال: /setwarnings 5")
        return

    try:
        count = int(args[0])
        if count < 1:
            await update.message.reply_text("⚠️ يجب أن يكون العدد أكبر من 0.")
            return
        if count > 10:
            await update.message.reply_text("⚠️ لا يمكن أن يتجاوز العدد 10.")
            return

        update_group_setting(chat_id, "max_warnings", count)
        await update.message.reply_text(f"✅ تم تعيين عدد التحذيرات إلى {count}.")
        await send_log(
            bot=context.bot,
            user=update.effective_user,
            chat_title=update.effective_chat.title or "المجموعة",
            deleted_text=f"تغيير عدد التحذيرات إلى {count}",
            violation_type="⚙️ إعدادات"
        )
    except ValueError:
        await update.message.reply_text("⚠️ يجب إدخال عدد صحيح.\nمثال: /setwarnings 5")


async def set_mute_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحديد مدة الكتم عند المخالفة الثانية (بالدقائق)"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("⚠️ استخدم: /setmutetime [دقائق]\nمثال: /setmutetime 15")
        return

    try:
        minutes = int(args[0])
        if minutes < 1:
            await update.message.reply_text("⚠️ يجب أن تكون المدة أكبر من 0 دقيقة.")
            return
        if minutes > 60:
            await update.message.reply_text("⚠️ لا يمكن أن تتجاوز المدة 60 دقيقة.")
            return

        update_group_setting(chat_id, "mute_duration", minutes)
        await update.message.reply_text(f"✅ تم تعيين مدة الكتم إلى {minutes} دقائق.")
        await send_log(
            bot=context.bot,
            user=update.effective_user,
            chat_title=update.effective_chat.title or "المجموعة",
            deleted_text=f"تغيير مدة الكتم إلى {minutes} دقائق",
            violation_type="⚙️ إعدادات"
        )
    except ValueError:
        await update.message.reply_text("⚠️ يجب إدخال عدد صحيح.\nمثال: /setmutetime 15")


async def set_captcha_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحديد مهلة حل الكابتشا (بالثواني)"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("⚠️ استخدم: /setcaptchatime [ثواني]\nمثال: /setcaptchatime 90")
        return

    try:
        seconds = int(args[0])
        if seconds < 10:
            await update.message.reply_text("⚠️ يجب أن تكون المهلة 10 ثوان على الأقل.")
            return
        if seconds > 300:
            await update.message.reply_text("⚠️ لا يمكن أن تتجاوز المهلة 300 ثانية (5 دقائق).")
            return

        update_group_setting(chat_id, "captcha_timeout", seconds)
        await update.message.reply_text(f"✅ تم تعيين مهلة الكابتشا إلى {seconds} ثانية.")
        await send_log(
            bot=context.bot,
            user=update.effective_user,
            chat_title=update.effective_chat.title or "المجموعة",
            deleted_text=f"تغيير مهلة الكابتشا إلى {seconds} ثانية",
            violation_type="⚙️ إعدادات"
        )
    except ValueError:
        await update.message.reply_text("⚠️ يجب إدخال عدد صحيح.\nمثال: /setcaptchatime 90")


# ===================== الأوامر العامة =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>Raskov Security Bot v6.0</b>\n\n"
        "🔹 <b>القائمة البيضاء</b>: minepi.com, pi.app\n"
        "🔹 <b>مانع التكرار</b>: 5 رسائل / 4 ثوان = كتم 5د\n"
        "🔹 <b>منع الروابط</b>: مفعل ✅\n"
        "🔹 <b>منع الميديا</b>: معطل ❌\n"
        "🔹 <b>منع التوجيه</b>: معطل ❌\n"
        "🔹 <b>الترحيب</b>: كابتشا + موافقة 🔐\n"
        "🔹 <b>قاعدة البيانات</b>: مفعلة ✅\n"
        "🔹 <b>إعدادات قابلة للتخصيص</b>: ✅\n\n"
        "👑 <b>أوامر المشرفين</b>:\n"
        "/ban - رد على رسالة العضو\n"
        "/unban [ID]\n"
        "/resetwarnings - رد على رسالة العضو\n"
        "/locklinks - تبديل\n"
        "/lockmedia - تبديل\n"
        "/lockforward - تبديل\n"
        "/stats - عرض الإحصائيات\n"
        "/setwarnings [عدد] - عدد التحذيرات قبل الحظر\n"
        "/setmutetime [دقائق] - مدة الكتم عند المخالفة الثانية\n"
        "/setcaptchatime [ثواني] - مهلة الكابتشا\n\n"
        "👤 <b>أوامر الأعضاء</b>:\n"
        "/warnings - عرض مخالفاتك\n"
        "/rules - عرض قوانين المجموعة\n"
        "/testlog - اختبار اللوجات",
        parse_mode="HTML"
    )


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(GROUP_RULES, parse_mode="HTML")


async def warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = get_warnings(user_id)
    await update.message.reply_text(f"⚠️ عدد مخالفاتك: {count}")


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

    total_violations = get_total_violations(chat_id)
    links_deleted = get_violations_by_type(chat_id, "رابط غير مسموح") + get_violations_by_type(chat_id, "رابط غير مسموح (ملتف)")
    phones_deleted = get_violations_by_type(chat_id, "رقم هاتف")
    wallets_deleted = get_violations_by_type(chat_id, "محفظة رقمية")
    total_warnings = get_total_warnings()
    users_with_warnings = get_users_with_warnings()

    stats_message = (
        "📊 <b>إحصائيات البوت</b>\n\n"
        f"🛡️ <b>إجمالي المخالفات</b>: {total_violations}\n"
        f"🚫 <b>الروابط المحذوفة</b>: {links_deleted}\n"
        f"📞 <b>أرقام الهواتف المحذوفة</b>: {phones_deleted}\n"
        f"💰 <b>المحافظ الرقمية المحذوفة</b>: {wallets_deleted}\n"
        f"⚠️ <b>إجمالي التحذيرات الصادرة</b>: {total_warnings}\n"
        f"👤 <b>الأعضاء الذين لديهم مخالفات</b>: {users_with_warnings}\n\n"
        "📌 يتم تحديث الإحصائيات تلقائياً مع كل مخالفة."
    )

    await update.message.reply_text(stats_message, parse_mode="HTML")


# ===================== المعالج الرئيسي =====================

async def anti_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    chat_title = update.effective_chat.title or "المجموعة"
    user = update.effective_user

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

    if user_id in pending_approvals:
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.first_name}، أنت في مرحلة الموافقة على القوانين. اضغط على زر 'موافق'."
            )
        except:
            pass
        return

    if await check_flood(update, context):
        return

    if await is_admin(context.bot, chat_id, user_id):
        return

    settings = get_group_settings(chat_id)
    lock_links = settings.get("lock_links", True)
    lock_media = settings.get("lock_media", False)
    lock_forward = settings.get("lock_forward", False)
    max_warnings = settings.get("max_warnings", 3)
    mute_duration = settings.get("mute_duration", 10)

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

    if not update.message.text:
        return

    original_text = update.message.text

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

        log_violation(user_id, chat_id, "كلمة ممنوعة", original_text)
        count = increment_warning(user_id, user.first_name)

        if count == 1:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.first_name} تحذير 1/{max_warnings} - ممنوع استخدام الكلمات الممنوعة ('{found_word}')."
            )
        elif count == 2:
            mute_success = await mute_user(context.bot, chat_id, user_id, mute_duration)
            if mute_success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {user.first_name} تحذير 2/{max_warnings} - تم كتمك {mute_duration} دقائق."
                )
                await send_log(
                    bot=context.bot,
                    user=user,
                    chat_title=chat_title,
                    deleted_text=f"كتم {mute_duration} دقائق (كلمة ممنوعة)",
                    violation_type=f"🔇 كتم {mute_duration} دقائق"
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {user.first_name} تحذير 2/{max_warnings} - التحذير الأخير. (فشل الكتم)"
                )
        elif count >= max_warnings:
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 تم حظر {user.first_name} تلقائياً ({max_warnings}/{max_warnings})."
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
            account_age_days = (datetime.now() - user.date).days
            if account_age_days < MIN_ACCOUNT_AGE_DAYS:
                await update.message.delete()
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🛑 {user.first_name} تم حظره تلقائياً لأن حسابه جديد (عمره أقل من {MIN_ACCOUNT_AGE_DAYS} يوم)."
                )
                await send_log(
                    bot=context.bot,
                    user=user,
                    chat_title=chat_title,
                    deleted_text=original_text,
                    violation_type="🛑 حساب جديد (ممنوع)"
                )
                return
        except:
            pass

        try:
            await update.message.delete()
        except:
            pass

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
                text=f"⚠️ {user.first_name} تحذير 1/{max_warnings} - ممنوع النشر المخالف."
            )
        elif count == 2:
            mute_success = await mute_user(context.bot, chat_id, user_id, mute_duration)
            if mute_success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {user.first_name} تحذير 2/{max_warnings} - تم كتمك {mute_duration} دقائق. المخالفة التالية = حظر."
                )
                await send_log(
                    bot=context.bot,
                    user=user,
                    chat_title=chat_title,
                    deleted_text=f"كتم {mute_duration} دقائق (المخالفة الثانية)",
                    violation_type=f"🔇 كتم {mute_duration} دقائق"
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {user.first_name} تحذير 2/{max_warnings} - التحذير الأخير. (فشل الكتم)"
                )
        elif count >= max_warnings:
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 تم حظر {user.first_name} تلقائياً ({max_warnings}/{max_warnings})."
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

    # أوامر الإعدادات الجديدة
    app.add_handler(CommandHandler("setwarnings", set_warnings))
    app.add_handler(CommandHandler("setmutetime", set_mute_time))
    app.add_handler(CommandHandler("setcaptchatime", set_captcha_time))

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
    app.add_handler(CallbackQueryHandler(handle_rules_approval, pattern="^agree_rules_"))

    # المعالج الرئيسي
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, anti_link))

    print("🤖 Raskov Security Bot يعمل الآن مع الإعدادات القابلة للتخصيص...")
    app.run_polling()


if __name__ == "__main__":
    main()
