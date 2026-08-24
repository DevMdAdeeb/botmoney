import logging
import random
import urllib.parse
from typing import List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters
)
import database
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# States for conversation handler
SELECT_PAYMENT_METHOD, ENTER_ACCOUNT, ENTER_AMOUNT = range(3)
ENTER_GIFT_CODE = 3

async def check_user_subscriptions(bot, user_id: int) -> tuple[bool, List[dict]]:
    """Checks if the user is subscribed to all mandatory channels."""
    channels = database.get_all_channels()
    unsubscribed = []

    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch["chat_id"], user_id=user_id)
            if member.status not in ["creator", "administrator", "member"]:
                unsubscribed.append(ch)
        except Exception as e:
            logger.warning(f"Error checking sub for user {user_id} in {ch['chat_id']}: {e}")
            unsubscribed.append(ch)

    is_subscribed = (len(unsubscribed) == 0)
    return is_subscribed, unsubscribed

def get_mandatory_sub_keyboard(unsubscribed_channels: List[dict]) -> InlineKeyboardMarkup:
    keyboard = []
    for ch in unsubscribed_channels:
        keyboard.append([InlineKeyboardButton(text=f"📢 {ch['title']}", url=ch['invite_link'])])
    keyboard.append([InlineKeyboardButton(text="تحقق من الاشتراك 🔄", callback_data="check_subscription")])
    return InlineKeyboardMarkup(keyboard)

def get_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💰 رصيدي وحسابي", callback_data="user_profile"), InlineKeyboardButton("🔗 رابط الإحالة", callback_data="user_referral")]
    ]

    # Check if there are available tasks for user
    available_tasks = database.get_available_tasks_for_user(user_id)
    if available_tasks:
        keyboard.append([InlineKeyboardButton("🎯 المهام اليومية", callback_data="user_tasks"), InlineKeyboardButton("🎁 كود الهدية", callback_data="enter_gift_code")])
    else:
        keyboard.append([InlineKeyboardButton("🎁 كود الهدية", callback_data="enter_gift_code")])

    keyboard.extend([
        [InlineKeyboardButton("🎁 المكافأة اليومية", callback_data="daily_bonus"), InlineKeyboardButton("🏆 أوائل الداعين", callback_data="leaderboard")],
        [InlineKeyboardButton("💳 طلب سحب", callback_data="user_withdraw"), InlineKeyboardButton("ℹ️ طرق الدفع المتاحة", callback_data="user_payment_methods")]
    ])

    custom_btns = database.get_all_custom_buttons()
    row = []
    for btn in custom_btns:
        if btn["type"] == "url":
            row.append(InlineKeyboardButton(text=btn["title"], url=btn["value"]))
        else: # text
            row.append(InlineKeyboardButton(text=btn["title"], callback_data=f"custom_btn_{btn['id']}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ لوحة تحكم المدير الشاملة", callback_data="admin_main")])

    return InlineKeyboardMarkup(keyboard)

def generate_captcha():
    num1 = random.randint(1, 9)
    num2 = random.randint(1, 9)
    correct = num1 + num2
    wrong1 = correct + random.choice([-2, -1, 1, 2])
    wrong2 = correct + random.choice([-3, 3, 4])
    options = [correct, wrong1, wrong2]
    random.shuffle(options)
    return num1, num2, correct, options

async def send_captcha_challenge(update_or_query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    num1, num2, correct, options = generate_captcha()
    context.user_data["captcha_correct"] = correct

    keyboard = []
    row = []
    for opt in options:
        row.append(InlineKeyboardButton(str(opt), callback_data=f"captcha_ans_{opt}"))
    keyboard.append(row)

    text = f"🤖 **اختبار الكابتشا للأمان:**\n\nيرجى حل المسألة الحسابية البسيطة التالية لاستخدام البوت:\n\n❓ **{num1} + {num2} = ?**"

    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update_or_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    referred_by = None
    if context.args:
        try:
            ref_id = int(context.args[0])
            if ref_id != user.id:
                referred_by = ref_id
        except ValueError:
            pass

    database.register_user(
        user_id=user.id,
        first_name=user.first_name,
        username=user.username,
        referred_by=referred_by
    )

    user_data = database.get_user(user.id)
    if user_data and user_data.get("is_banned"):
        await update.message.reply_text("❌ حسابك محظور من استخدام هذا البوت.")
        return

    captcha_enabled = database.get_setting("captcha_enabled", "1") == "1"
    if captcha_enabled and not user_data.get("captcha_verified"):
        await send_captcha_challenge(update, context, user.id)
        return

    is_subbed, unsubscribed = await check_user_subscriptions(context.bot, user.id)
    if not is_subbed:
        reply_markup = get_mandatory_sub_keyboard(unsubscribed)
        await update.message.reply_text(
            "⚠️ عذراً عزيزي، يجب عليك الاشتراك في قنوات البوت أولاً لاستخدام البوت!\n\n"
            "يرجى الانضمام للقنوات التالية ثم الضغط على (تحقق من الاشتراك 🔄):",
            reply_markup=reply_markup
        )
        return

    # Check if there is a pending reward before calling reward_referrer_if_pending
    user_before = database.get_user(user.id)
    ref_id_before = user_before.get("referred_by") if user_before else None

    reward_info = database.reward_referrer_if_pending(user.id)
    if reward_info:
        ref_id, amount = reward_info
        try:
            await context.bot.send_message(
                chat_id=ref_id,
                text=f"🎉 انضم مستخدم جديد عبر رابطك!\n💰 تمت إضافة مكافأة الإحالة `${amount}` إلى رصيدك."
            )
        except Exception:
            pass

        await send_referral_audit_log(context, user.id, ref_id, amount)

    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.id}"
    welcome_fmt = database.get_setting("welcome_message")
    welcome_text = welcome_fmt.format(
        name=user.first_name,
        id=user.id,
        balance=f"{user_data['balance']:.2f}" if user_data else "0.00",
        ref_link=ref_link
    )

    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user.id))

def clean_md(text: str) -> str:
    """Escapes Markdown formatting characters like underscores and asterisks."""
    if not text:
        return ""
    return str(text).replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")

async def send_referral_audit_log(context: ContextTypes.DEFAULT_TYPE, user_id: int, ref_id: int, amount: float):
    ref_log_ch = database.get_setting("referral_log_channel_id", "")
    if ref_log_ch:
        new_u = database.get_user(user_id)
        ref_u = database.get_user(ref_id)

        new_fname = clean_md(new_u['first_name']) if new_u and new_u.get('first_name') else "غير معروف"
        new_uname = f"@{clean_md(new_u['username'])}" if new_u and new_u.get('username') else "لا يوجد"

        ref_fname = clean_md(ref_u['first_name']) if ref_u and ref_u.get('first_name') else "غير معروف"
        ref_uname = f"@{clean_md(ref_u['username'])}" if ref_u and ref_u.get('username') else "لا يوجد"

        log_text = (
            f"🚨 **تقرير إحالة جديدة (تسجيل عضو جديد)**\n\n"
            f"👤 **بيانات العضو الجديد:**\n"
            f"• الاسم: **{new_fname}**\n"
            f"• المعرف (ID): `{user_id}`\n"
            f"• اليوزر: {new_uname}\n\n"
            f"👥 **بيانات صاحب الإحالة (الداعي):**\n"
            f"• الاسم: **{ref_fname}**\n"
            f"• المعرف (ID): `{ref_id}`\n"
            f"• اليوزر: {ref_uname}\n"
            f"💰 المكافأة المضافة: `${amount:.2f}`\n\n"
            f"🔎 *تم التحقق من الحساب وعبر الكابتشا والقنوات بنجاح.*"
        )
        try:
            await context.bot.send_message(chat_id=ref_log_ch, text=log_text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to post to referral log channel {ref_log_ch}: {e}")

async def captcha_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    ans = int(query.data.replace("captcha_ans_", ""))
    correct = context.user_data.get("captcha_correct")

    if ans != correct:
        await query.answer("❌ إجابة خاطئة! أعد المحاولة.", show_alert=True)
        await send_captcha_challenge(query, context, user.id)
        return

    database.set_captcha_verified(user.id)
    await query.message.reply_text("✅ تم التحقق من الكابتشا بنجاح!")

    is_subbed, unsubscribed = await check_user_subscriptions(context.bot, user.id)
    if not is_subbed:
        reply_markup = get_mandatory_sub_keyboard(unsubscribed)
        await query.message.reply_text(
            "⚠️ يرجى الانضمام للقنوات التالية ثم الضغط على (تحقق من الاشتراك 🔄):",
            reply_markup=reply_markup
        )
        return

    reward_info = database.reward_referrer_if_pending(user.id)
    if reward_info:
        ref_id, amount = reward_info
        try:
            await context.bot.send_message(
                chat_id=ref_id,
                text=f"🎉 انضم مستخدم جديد عبر رابطك!\n💰 تمت إضافة مكافأة الإحالة `${amount}` إلى رصيدك."
            )
        except Exception:
            pass
        await send_referral_audit_log(context, user.id, ref_id, amount)

    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.id}"
    welcome_fmt = database.get_setting("welcome_message")
    user_data = database.get_user(user.id)
    welcome_text = welcome_fmt.format(
        name=user.first_name,
        id=user.id,
        balance=f"{user_data['balance']:.2f}" if user_data else "0.00",
        ref_link=ref_link
    )

    await query.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user.id))

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    user_data = database.get_user(user.id)
    if user_data and user_data.get("is_banned"):
        await query.edit_message_text("❌ حسابك محظور من استخدام هذا البوت.")
        return

    is_subbed, unsubscribed = await check_user_subscriptions(context.bot, user.id)
    if not is_subbed:
        reply_markup = get_mandatory_sub_keyboard(unsubscribed)
        try:
            await query.edit_message_text(
                "❌ لم تقم بالاشتراك في جميع القنوات بعد!\nيرجى الانضمام والضغط على تحقق مرة أخرى:",
                reply_markup=reply_markup
            )
        except Exception:
            pass
        return

    reward_info = database.reward_referrer_if_pending(user.id)
    if reward_info:
        ref_id, amount = reward_info
        try:
            await context.bot.send_message(
                chat_id=ref_id,
                text=f"🎉 انضم مستخدم جديد عبر رابطك!\n💰 تمت إضافة مكافأة الإحالة `${amount}` إلى رصيدك."
            )
        except Exception:
            pass
        await send_referral_audit_log(context, user.id, ref_id, amount)

    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.id}"
    welcome_fmt = database.get_setting("welcome_message")
    user_data = database.get_user(user.id)
    welcome_text = welcome_fmt.format(
        name=user.first_name,
        id=user.id,
        balance=f"{user_data['balance']:.2f}" if user_data else "0.00",
        ref_link=ref_link
    )

    await query.message.reply_text("✅ شكراً لاشتراكك! تم تفعيل البوت بنجاح.")
    await query.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user.id))

# --- Gift Code Flow ---
async def prompt_gift_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🎁 **أدخل كود الهدية الذي حصلت عليه:**")
    return ENTER_GIFT_CODE

async def redeem_gift_code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code_text = update.message.text.strip()
    user_id = update.effective_user.id

    success, message, amount = database.redeem_gift_code(user_id, code_text)
    await update.message.reply_text(message, reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

# --- Micro-Tasks Flow ---
async def user_tasks_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    tasks = database.get_available_tasks_for_user(user_id)
    text = "🎯 **المهام الإضافية المتاحة للكسب:**\n\n"
    keyboard = []

    if not tasks:
        text += "لا توجد مهام جديدة متاحة حالياً. أعد التفقد لاحقاً!"
    else:
        for t in tasks:
            text += f"🔹 **{t['title']}**\n💰 المكافأة: `${t['reward']:.2f}`\n\n"
            keyboard.append([InlineKeyboardButton(f"🚀 تنفيذ: {t['title']}", url=t['link'])])
            keyboard.append([InlineKeyboardButton(f"✅ تأكيد استلام `${t['reward']:.2f}`", callback_data=f"claim_task_{t['id']}")])

    keyboard.append([InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def claim_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    task_id = int(query.data.replace("claim_task_", ""))

    # Check if task has a channel requirement
    tasks = database.get_all_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)

    if task and task.get("chat_id"):
        chat_id = task["chat_id"].strip()
        if chat_id:
            try:
                member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                if member.status not in ["creator", "administrator", "member"]:
                    await query.answer("❌ لم تقم بالاشتراك في القناة بعد! اشترك أولاً لتأكيد المهمة واستلام المكافأة.", show_alert=True)
                    return
            except Exception as e:
                logger.warning(f"Failed to check sub for task {task_id} in {chat_id}: {e}")

    success, msg, amount = database.complete_task(user_id, task_id)

    await query.answer(msg, show_alert=True)
    await user_tasks_callback(update, context)

async def daily_bonus_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if database.get_setting("daily_bonus_enabled", "1") != "1":
        await query.answer("⚠️ المكافأة اليومية غير مفعلة حالياً من قبل المدير.", show_alert=True)
        return

    can_claim, time_remaining_str = database.get_daily_bonus_time_status(user.id)
    if not can_claim:
        await query.answer(f"⏳ تم استلام المكافأة اليومية سابقاً! عد بعد: {time_remaining_str}", show_alert=True)
        return

    bonus_amount = float(database.get_setting("daily_bonus_amount", "0.05"))
    database.claim_daily_bonus(user.id, bonus_amount)

    await query.answer(f"🎉 مبروك! حصلت على مكافأة يومية قدرها ${bonus_amount:.2f}", show_alert=True)

    user_data = database.get_user(user.id)
    text = (
        f"🎁 **تم استلام المكافأة اليومية بنجاح!**\n\n"
        f"💰 القيمة: `${bonus_amount:.2f}`\n"
        f"💳 رصيدك الحالي: `${user_data['balance']:.2f}`\n\n"
        f"يمكنك العودة بعد 24 ساعة لاستلام المكافأة القادمة 🚀"
    )
    keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    top_users = database.get_top_referrers(10)
    text = "🏆 **قائمة أوائل المسوقين والداعين:**\n\n"

    if not top_users:
        text += "لا يوجد متصدرين حتى الآن."
    else:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for idx, u in enumerate(top_users):
            medal = medals[idx] if idx < len(medals) else "👤"
            name = u['first_name']
            count = u['referrals_count']
            text += f"{medal} **{name}** — `{count}` إحالة\n"

    keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def user_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    is_subbed, unsubscribed = await check_user_subscriptions(context.bot, user.id)
    if not is_subbed:
        await query.edit_message_text("⚠️ يجب الاشتراك في القنوات أولاً!", reply_markup=get_mandatory_sub_keyboard(unsubscribed))
        return

    u = database.get_user(user.id)
    if not u:
        return

    ref_reward = database.get_setting("referral_reward", "0.5")
    text = (
        f"👤 **معلومات حسابك الشخصي:**\n\n"
        f"🆔 المعرف الرقمي: `{u['user_id']}`\n"
        f"👤 الاسم: {u['first_name']}\n"
        f"💰 الرصيد الحالي: `${u['balance']:.2f}`\n"
        f"💵 إجمالي الأرباح: `${u['total_earned']:.2f}`\n"
        f"👥 عدد الإحالات: `{u['referrals_count']}`\n"
        f"🎁 سعر الإحالة: `${ref_reward}`"
    )
    keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def user_referral_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    is_subbed, unsubscribed = await check_user_subscriptions(context.bot, user.id)
    if not is_subbed:
        await query.edit_message_text("⚠️ يجب الاشتراك في القنوات أولاً!", reply_markup=get_mandatory_sub_keyboard(unsubscribed))
        return

    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.id}"
    ref_reward = database.get_setting("referral_reward", "0.5")
    promo_text = database.get_setting("promo_text", "")

    share_msg = f"{promo_text}\n{ref_link}"
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(share_msg)}"

    text = (
        f"🔗 **رابط الإحالة الخاص بك:**\n\n"
        f"`{ref_link}`\n\n"
        f"💰 **المكافأة:** كسب `${ref_reward}` لكل صديق يقوم بالانضمام والاشتراك بقنوات البوت عبر رابطك!\n"
        f"شارك الرابط مع أصدقائك أو في المجموعات وابدأ بكسب المال 🚀"
    )

    keyboard = [
        [InlineKeyboardButton("🚀 مشاركة رابطك بنقرة واحدة", url=share_url)],
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def user_payment_methods_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    methods = database.get_all_payment_methods()
    if not methods:
        text = "ℹ️ لا توجد طرق دفع مضافة حالياً من قبل المدير."
    else:
        text = "💳 **طرق الدفع المتاحة للسحب:**\n\n"
        for m in methods:
            inst = f" ({m['instructions']})" if m['instructions'] else ""
            text += f"🔹 **{m['name']}**{inst}\n"

    keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def custom_btn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    btn_id = int(query.data.split("custom_btn_")[1])
    btn = database.get_custom_button(btn_id)
    if btn:
        keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]]
        await query.edit_message_text(btn["value"], reply_markup=InlineKeyboardMarkup(keyboard))

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.id}"
    welcome_fmt = database.get_setting("welcome_message")
    user_data = database.get_user(user.id)
    welcome_text = welcome_fmt.format(
        name=user.first_name,
        id=user.id,
        balance=f"{user_data['balance']:.2f}" if user_data else "0.00",
        ref_link=ref_link
    )

    await query.edit_message_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user.id))

# --- Withdrawal Conversation Handlers ---
async def start_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    user_data = database.get_user(user.id)
    if not user_data:
        return ConversationHandler.END

    min_withdraw = float(database.get_setting("min_withdrawal", "5.0"))
    if user_data["balance"] < min_withdraw:
        keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]]
        await query.edit_message_text(
            f"❌ رصيدك الحالي (`${user_data['balance']:.2f}`) أقل من الحد الأدنى للسحب (`${min_withdraw:.2f}`).\n"
            f"قم بمشاركة رابطك لإكمال الرصيد المطلوب!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    methods = database.get_all_payment_methods()
    if not methods:
        keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]]
        await query.edit_message_text(
            "❌ لا توجد طرق دفع متاحة حالياً للسحب. يرجى التواصل مع المدير.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    keyboard = []
    for m in methods:
        keyboard.append([InlineKeyboardButton(m["name"], callback_data=f"select_pay_{m['name']}")])
    keyboard.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_withdraw")])

    await query.edit_message_text(
        "💳 **اختر طريقة الدفع المناسبة لك:**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_PAYMENT_METHOD

async def payment_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    method_name = query.data.replace("select_pay_", "")
    context.user_data["withdraw_method"] = method_name

    await query.edit_message_text(
        f"✅ تم اختيار طريقة الدفع: **{method_name}**\n\n"
        f"📝 يرجى الآن إرسال (عنوان المحفظة / الرقم / معلومات الحساب) التي تود استلام المبلغ عليها:",
        parse_mode="Markdown"
    )
    return ENTER_ACCOUNT

async def account_details_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    account_details = update.message.text.strip()
    if not account_details:
        await update.message.reply_text("❌ يرجى إدخال معلومات حساب/محفظة صالحة:")
        return ENTER_ACCOUNT

    context.user_data["withdraw_account"] = account_details
    user_id = update.effective_user.id
    user_data = database.get_user(user_id)
    min_withdraw = float(database.get_setting("min_withdrawal", "5.0"))

    await update.message.reply_text(
        f"💰 **أدخل مبلغ السحب بالدولار ($):**\n"
        f"• رصيدك المتاح: `${user_data['balance']:.2f}`\n"
        f"• الحد الأدنى للسحب: `${min_withdraw:.2f}`",
        parse_mode="Markdown"
    )
    return ENTER_AMOUNT

async def amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    user_data = database.get_user(user_id)
    min_withdraw = float(database.get_setting("min_withdrawal", "5.0"))

    try:
        amount = float(text)
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح للمبلغ (مثال: 10.5):")
        return ENTER_AMOUNT

    if amount < min_withdraw:
        await update.message.reply_text(f"❌ المبلغ أودعته أقل من الحد الأدنى للسحب (`${min_withdraw:.2f}`). أعد المحاولة:")
        return ENTER_AMOUNT

    if amount > user_data["balance"]:
        await update.message.reply_text(f"❌ المبلغ المطلوب يفيض عن رصيدك المتاح (`${user_data['balance']:.2f}`). أعد المحاولة:")
        return ENTER_AMOUNT

    method = context.user_data.get("withdraw_method")
    account = context.user_data.get("withdraw_account")

    w_id = database.create_withdrawal_request(user_id, method, account, amount)
    if not w_id:
        await update.message.reply_text("❌ حدث خطأ في إنشاء الطلب. يرجى التأكد من رصيدك والمحاولة لاحقاً.")
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ **تم تقديم طلب السحب بنجاح!**\n\n"
        f"🆔 رقم الطلب: `#{w_id}`\n"
        f"💳 طريقة الدفع: **{method}**\n"
        f"👤 المحفظة/الحساب: `{account}`\n"
        f"💵 المبلغ: `${amount:.2f}`\n\n"
        f"طلبك حالياً قيد التقييم وسيصلك إشعار عند موافقة المدير.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(user_id)
    )

    try:
        admin_id = ADMIN_ID
        admin_text = (
            f"🚨 **طلب سحب جديد!** `#{w_id}`\n\n"
            f"👤 المستخدم: {update.effective_user.first_name} (`{user_id}`)\n"
            f"💳 طريقة الدفع: **{method}**\n"
            f"📌 الحساب/المحفظة: `{account}`\n"
            f"💰 المبلغ المطلوب: `${amount:.2f}`"
        )
        admin_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("موافقة ✅", callback_data=f"approve_w_{w_id}"),
                InlineKeyboardButton("رفض ❌", callback_data=f"reject_w_{w_id}")
            ]
        ])
        await context.bot.send_message(chat_id=admin_id, text=admin_text, parse_mode="Markdown", reply_markup=admin_keyboard)
    except Exception as e:
        logger.error(f"Failed to notify admin about withdrawal request #{w_id}: {e}")

    return ConversationHandler.END

async def cancel_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ تم إلغاء العملية.", reply_markup=get_main_menu_keyboard(query.from_user.id))
    return ConversationHandler.END
