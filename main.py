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

# ===================== متغيرات الرسائل المخصصة =====================

WELCOME_MESSAGE = (
    "🎉 أهلاً وسهلاً بك {first_name} في مجموعة {group_name}!\n\n"
    "📌 <b>مجتمع Pi Network</b> يرحب بك. هنا نتبادل المعرفة وندعم بعضنا البعض.\n"
    "💡 تذكر أن التعاون والاحترام هما أساس مجتمعنا.\n\n"
    "🔍 استخدم /rules لمراجعة القوانين في أي وقت.\n"
    "📊 استخدم /stats (للمشرفين) لمتابعة إحصائيات المجموعة.\n\n"
    "🌟 نتمنى لك وقتاً ممتعاً ومفيداً!"
)

GROUP_RULES = (
    "📜 <b>قوانين مجموعة Pi Network</b> 📜\n\n"
    "1️⃣ <b>الروابط المسموحة فقط</b>: minepi.com و pi.app.\n"
    "2️⃣ <b>ممنوع نشر أرقام الهواتف</b> أو المحافظ الرقمية.\n"
    "3️⃣ <b>ممنوع التكرار السريع</b> للرسائل (سبام).\n"
    "4️⃣ <b>ممنوع نشر الصور أو الفيديوهات</b> غير المفيدة.\n"
    "5️⃣ <b>ممنوع استخدام الكلمات الممنوعة</b> (نصب، احتيال، سبام).\n"
    "6️⃣ <b>احترام جميع الأعضاء</b> والابتعاد عن الشتائم.\n\n"
    "⚠️ <b>نظام العقوبات</b>:\n"
    "• المخالفة الأولى: تحذير 📢\n"
    "• المخالفة الثانية: كتم مؤقت 🔇\n"
    "• المخالفة الثالثة: حظر تلقائي 🚫\n\n"
    "🛑 الحسابات الجديدة (أقل من يوم) = حظر فوري عند المخالفة.\n\n"
    "👆 اضغط على زر 'موافق' لتأكيد قبولك القوانين."
)

CAPTCHA_MESSAGE = (
    "🔐 <b>تحقق بشري مطلوب</b> {first_name}!\n\n"
    "لحماية المجموعة من البوتات الآلية، يرجى حل المسألة التالية:\n\n"
    "<b>{question}</b>\n\n"
    "⏳ لديك <b>{timeout}</b> ثانية للإجابة.\n"
    "📝 اكتب الرقم فقط (مثال: 5)."
)

CAPTCHA_FAIL_MESSAGE = (
    "❌ إجابة خاطئة {first_name}. حاول مرة أخرى ({attempts}/{max_attempts}):\n\n"
    "{question}"
)

CAPTCHA_SUCCESS_MESSAGE = (
    "✅ تم التحقق بنجاح {first_name}!\n"
    "سيتم الآن عرض قوانين المجموعة. يرجى الموافقة عليها لإتمام الانضمام."
)

WARNING_FIRST_MESSAGE = (
    "⚠️ <b>تحذير {count}/{max_warnings}</b> {first_name}\n\n"
    "📌 تم حذف رسالتك لأنها تحتوي على محتوى مخالف لقوانين المجموعة.\n"
    "📖 راجع القوانين عبر /rules لتجنب العقوبات المستقبلية.\n\n"
    "🔹 المخالفة الثانية = كتم مؤقت.\n"
    "🔹 المخالفة الثالثة = حظر تلقائي."
)

WARNING_SECOND_MESSAGE = (
    "⚠️ <b>تحذير {count}/{max_warnings}</b> {first_name}\n\n"
    "📌 تم حذف رسالتك المخالفة.\n"
    "🔇 تم <b>كتمك لمدة {mute_duration} دقائق</b> كعقوبة للمخالفة الثانية.\n"
    "📖 راجع القوانين عبر /rules لتجنب الحظر التلقائي.\n\n"
    "🚫 المخالفة الثالثة = حظر نهائي."
)

BAN_MESSAGE = (
    "🚫 <b>تم حظر {first_name} تلقائياً</b>\n\n"
    "📌 وصل عدد مخالفاتك إلى {max_warnings}/{max_warnings}.\n"
    "📖 القوانين واضحة، ونحن نحرص على توفير بيئة آمنة للجميع.\n\n"
    "🔄 إذا كنت تعتقد أن هذا الحظر غير مبرر، يمكنك التواصل مع المشرفين.\n"
    "📩 سيتم مراجعة طلبك بأسرع وقت."
)

FLOOD_MUTE_MESSAGE = (
    "🔇 {first_name} تم كتمك لمدة {duration} دقائق.\n"
    "📌 السبب: إرسال أكثر من {limit} رسالة خلال {time} ثوانٍ (سبام).\n"
    "📖 يرجى التوقف عن التكرار السريع للحفاظ على نقاش هادف."
)

NEW_ACCOUNT_BAN_MESSAGE = (
    "🛑 {first_name} تم حظره تلقائياً.\n"
    "📌 سبب الحظر: حساب جديد (عمره أقل من {days} يوم).\n"
    "📖 نرحب بانضمامك بعد أن يصبح حسابك أقدم قليلاً."
)

GOODBYE_MESSAGE = (
    "🚪 وداعاً {first_name}.\n"
    "📌 نتمنى لك التوفيق في رحلتك مع Pi Network.\n"
    "🌟 أبوابنا مفتوحة لك دائماً إذا أردت العودة."
)


# ===================== إعدادات البيئة =====================
TOKEN = os.getenv("BOT_TOKEN")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")
REPORT_CHANNEL_ID = os.getenv("REPORT_CHANNEL_ID")  # ✅ جديد: قناة التقارير
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

# ===================== الكلمات الممنوعة =====================
FORBIDDEN_WORDS = [
    "نصب", "احتيال", "سبام", "إعلان", "دعاية", "مؤامرة", "تزوير",
    "اختراق", "حساب مميز", "أرباح سريعة", "استثمار مضمون", "ثروة",
    "scam", "spam", "hack", "cheat", "fraud", "phishing", "promo",
    "advertisement", "click here", "earn money", "free money",
    "investment", "guaranteed profit", "بيع باي", "شراء باي", "سعر باي", "تداول باي",
]

# ===================== إعدادات الحماية الأساسية =====================
FLOOD_LIMIT = 5
FLOOD_TIME = 4
MUTE_DURATION = 5
MIN_ACCOUNT_AGE_DAYS = 1
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


def update_group_setting(chat_id: int, setting_name: str, value):
    if not supabase:
        return
    try:
        supabase.table("group_settings").update({setting_name: value}).eq("chat_id", chat_id).execute()
    except Exception as e:
        print(f"⚠️ خطأ في تحديث الإعدادات: {e}")


# ===================== دوال الإحصائيات (العامة) =====================

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


# ===================== دوال إحصائيات التقارير الدورية (جديدة) =====================

def get_weekly_stats(chat_id: int) -> dict:
    """جلب إحصائيات الأسبوع الماضي (آخر 7 أيام)"""
    if not supabase:
        return {}

    try:
        # تاريخ الأسبوع الماضي
        one_week_ago = (datetime.now() - timedelta(days=7)).isoformat()

        # إجمالي المخالفات في الأسبوع الماضي
        res = supabase.table("violations_log").select("id", count="exact").eq("chat_id", chat_id).gte("created_at", one_week_ago).execute()
        total_violations = res.count if res.count else 0

        # المخالفات حسب النوع
        violations_by_type = {}
        for vtype in ["رابط غير مسموح", "رابط غير مسموح (ملتف)", "رقم هاتف", "محفظة رقمية", "كلمة ممنوعة"]:
            res = supabase.table("violations_log").select("id", count="exact").eq("chat_id", chat_id).eq("type", vtype).gte("created_at", one_week_ago).execute()
            violations_by_type[vtype] = res.count if res.count else 0

        # التحذيرات الصادرة في الأسبوع الماضي (من جدول violations_log أيضاً، لأننا نسجلها هناك)
        res = supabase.table("violations_log").select("id", count="exact").eq("chat_id", chat_id).eq("type", "⚠️ إدارة (تحذير)").gte("created_at", one_week_ago).execute()
        total_warnings = res.count if res.count else 0

        # العضو الأكثر مخالفة في الأسبوع الماضي
        res = supabase.table("violations_log").select("user_id", "violations_log:user_id(users:first_name)").eq("chat_id", chat_id).gte("created_at", one_week_ago).execute()
        # تبسيط: نحسب التكرارات يدوياً
        user_violations = {}
        if res.data:
            for item in res.data:
                uid = item.get("user_id")
                if uid:
                    user_violations[uid] = user_violations.get(uid, 0) + 1
        
        top_violator = None
        top_violator_count = 0
        for uid, count in user_violations.items():
            if count > top_violator_count:
                top_violator_count = count
                # نحاول جلب اسم المستخدم
                user_res = supabase.table("warnings").select("first_name").eq("user_id", uid).execute()
                if user_res.data:
                    top_violator = user_res.data[0].get("first_name", f"ID:{uid}")
                else:
                    top_violator = f"ID:{uid}"

        # عدد المحظورين في الأسبوع الماضي (من نوع "حظر" في logs)
        res = supabase.table("violations_log").select("id", count="exact").eq("chat_id", chat_id).eq("type", "🚫 حظر").gte("created_at", one_week_ago).execute()
        total_bans = res.count if res.count else 0

        # عدد الكتم في الأسبوع الماضي (من نوع "كتم" في logs)
        res = supabase.table("violations_log").select("id", count="exact").eq("chat_id", chat_id).eq("type", "🔇 كتم").gte("created_at", one_week_ago).execute()
        total_mutes = res.count if res.count else 0

        return {
            "total_violations": total_violations,
            "links_deleted": violations_by_type.get("رابط غير مسموح", 0) + violations_by_type.get("رابط غير مسموح (ملتف)", 0),
            "phones_deleted": violations_by_type.get("رقم هاتف", 0),
            "wallets_deleted": violations_by_type.get("محفظة رقمية", 0),
            "forbidden_words": violations_by_type.get("كلمة ممنوعة", 0),
            "total_warnings": total_warnings,
            "total_bans": total_bans,
            "total_mutes": total_mutes,
            "top_violator": top_violator,
            "top_violator_count": top_violator_count,
        }
    except Exception as e:
        print(f"⚠️ خطأ في جلب إحصائيات الأسبوع: {e}")
        return {}


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
        "📊 تقرير": "📊",
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
                text=FLOOD_MUTE_MESSAGE.format(
                    first_name=update.effective_user.first_name,
                    duration=MUTE_DURATION,
                    limit=FLOOD_LIMIT,
                    time=FLOOD_TIME
                )
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

    captcha_text = CAPTCHA_MESSAGE.format(
        first_name=first_name,
        question=question,
        timeout=captcha_timeout
    )

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=captcha_text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔐 {first_name}، تم إرسال كابتشا إلى خاصك. أجب خلال {captcha_timeout} ثانية."
        )
    except:
        await context.bot.send_message(
            chat_id=chat_id,
            text=captcha_text,
            parse_mode="HTML",
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
                text=CAPTCHA_SUCCESS_MESSAGE.format(first_name=first_name),
                parse_mode="HTML"
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
                when=60,
                data={"chat_id": original_chat_id, "user_id": user_id, "username": first_name},
                name=f"approval_{user_id}"
            )
            pending_approvals[user_id] = job

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

            fail_text = CAPTCHA_FAIL_MESSAGE.format(
                first_name=first_name,
                attempts=attempts,
                max_attempts=3,
                question=question
            )

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=fail_text,
                    parse_mode="HTML"
                )
            except:
                await context.bot.send_message(
                    chat_id=original_chat_id,
                    text=fail_text,
                    parse_mode="HTML"
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
                    text=NEW_ACCOUNT_BAN_MESSAGE.format(
                        first_name=user.first_name,
                        days=MIN_ACCOUNT_AGE_DAYS
                    ),
                    parse_mode="HTML"
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
        chat_title = update.effective_chat.title or "المجموعة"

        await context.bot.send_message(
            chat_id=chat_id,
            text=WELCOME_MESSAGE.format(
                first_name=user.first_name,
                group_name=chat_title
            ),
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


async def goodbye_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    chat_title = chat.title or "المجموعة"
    user = update.message.left_chat_member

    if user.id == context.bot.id:
        return

    await context.bot.send_message(
        chat_id=chat.id,
        text=GOODBYE_MESSAGE.format(
            first_name=user.first_name
        ),
        parse_mode="HTML"
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


# ===================== التقارير الدورية (جديد) =====================

async def send_weekly_report(bot, chat_id: int):
    """إنشاء وإرسال التقرير الأسبوعي"""
    if not supabase:
        return

    stats = get_weekly_stats(chat_id)
    if not stats:
        return

    # تنسيق التقرير
    report_text = (
        "📊 <b>تقرير الأسبوعي للمجموعة</b>\n"
        f"📅 <b>الفترة</b>: آخر 7 أيام\n\n"
        f"🛡️ <b>إجمالي المخالفات</b>: {stats.get('total_violations', 0)}\n"
        f"🚫 <b>الروابط المحذوفة</b>: {stats.get('links_deleted', 0)}\n"
        f"📞 <b>الأرقام المحذوفة</b>: {stats.get('phones_deleted', 0)}\n"
        f"💰 <b>المحافظ المحذوفة</b>: {stats.get('wallets_deleted', 0)}\n"
        f"🚫 <b>الكلمات الممنوعة</b>: {stats.get('forbidden_words', 0)}\n"
        f"🔇 <b>عمليات الكتم</b>: {stats.get('total_mutes', 0)}\n"
        f"🚫 <b>عمليات الحظر</b>: {stats.get('total_bans', 0)}\n"
        f"⚠️ <b>إجمالي التحذيرات</b>: {stats.get('total_warnings', 0)}\n"
    )

    if stats.get('top_violator'):
        report_text += (
            f"\n🏆 <b>أكثر عضو مخالفة</b>:\n"
            f"👤 {stats.get('top_violator')} - {stats.get('top_violator_count')} مخالفات"
        )
    else:
        report_text += "\n\n🏆 <b>لا توجد مخالفات</b> هذا الأسبوع! 🎉"

    report_text += "\n\n📌 <i>يتم إنشاء هذا التقرير تلقائياً كل أسبوع.</i>"

    try:
        await bot.send_message(chat_id=REPORT_CHANNEL_ID, text=report_text, parse_mode="HTML")
        print(f"✅ تم إرسال التقرير الأسبوعي إلى القناة {REPORT_CHANNEL_ID}")
    except Exception as e:
        print(f"❌ فشل إرسال التقرير: {e}")


async def generate_report_for_all_groups(context: ContextTypes.DEFAULT_TYPE):
    """جلب جميع المجموعات التي يديرها البوت وإرسال تقرير لكل منها"""
    if not supabase:
        return

    try:
        # جلب جميع chat_id من جدول group_settings (أو violations_log)
        res = supabase.table("group_settings").select("chat_id").execute()
        if not res.data:
            return

        for item in res.data:
            chat_id = item.get("chat_id")
            if chat_id:
                await send_weekly_report(context.bot, chat_id)
    except Exception as e:
        print(f"⚠️ خطأ في إنشاء التقارير: {e}")


async def force_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر لتشغيل التقرير يدوياً (للمشرفين)"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context.bot, chat_id, user_id):
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return

    await update.message.reply_text("📊 جاري إنشاء التقرير الأسبوعي...")
    await send_weekly_report(context.bot, chat_id)
    await update.message.reply_text("✅ تم إرسال التقرير إلى قناة التقارير.")


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


# ===================== أوامر الإعدادات =====================

async def set_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "🔹 <b>إعدادات قابلة للتخصيص</b>: ✅\n"
        "🔹 <b>تقارير دورية</b>: أسبوعية 📊\n\n"
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
        "/setcaptchatime [ثواني] - مهلة الكابتشا\n"
        "/report - تشغيل التقرير يدوياً 📊\n\n"
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
                text=WARNING_FIRST_MESSAGE.format(
                    first_name=user.first_name,
                    count=count,
                    max_warnings=max_warnings
                ),
                parse_mode="HTML"
            )
        elif count == 2:
            mute_success = await mute_user(context.bot, chat_id, user_id, mute_duration)
            if mute_success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=WARNING_SECOND_MESSAGE.format(
                        first_name=user.first_name,
                        count=count,
                        max_warnings=max_warnings,
                        mute_duration=mute_duration
                    ),
                    parse_mode="HTML"
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
                    text=BAN_MESSAGE.format(
                        first_name=user.first_name,
                        max_warnings=max_warnings
                    ),
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
                    text=NEW_ACCOUNT_BAN_MESSAGE.format(
                        first_name=user.first_name,
                        days=MIN_ACCOUNT_AGE_DAYS
                    ),
                    parse_mode="HTML"
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
                text=WARNING_FIRST_MESSAGE.format(
                    first_name=user.first_name,
                    count=count,
                    max_warnings=max_warnings
                ),
                parse_mode="HTML"
            )
        elif count == 2:
            mute_success = await mute_user(context.bot, chat_id, user_id, mute_duration)
            if mute_success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=WARNING_SECOND_MESSAGE.format(
                        first_name=user.first_name,
                        count=count,
                        max_warnings=max_warnings,
                        mute_duration=mute_duration
                    ),
                    parse_mode="HTML"
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
                    text=BAN_MESSAGE.format(
                        first_name=user.first_name,
                        max_warnings=max_warnings
                    ),
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

    # أوامر الإعدادات
    app.add_handler(CommandHandler("setwarnings", set_warnings))
    app.add_handler(CommandHandler("setmutetime", set_mute_time))
    app.add_handler(CommandHandler("setcaptchatime", set_captcha_time))

    # أمر التقرير اليدوي (جديد)
    app.add_handler(CommandHandler("report", force_report))

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

    # ===================== جدولة التقارير الأسبوعية (جديد) =====================
    scheduler = AsyncIOScheduler()
    
    # جدولة التقرير كل يوم أحد الساعة 12:00 مساءً
    scheduler.add_job(
        generate_report_for_all_groups,
        CronTrigger(day_of_week='sun', hour=12, minute=0),
        args=[app]
    )
    scheduler.start()
    print("📊 تم جدولة التقارير الأسبوعية (كل يوم أحد الساعة 12:00)")

    print("🤖 Raskov Security Bot يعمل الآن مع التقارير الدورية...")
    app.run_polling()


if __name__ == "__main__":
    main()
