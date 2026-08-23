import logging
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

# States for conversation handler (Withdrawal Flow)
SELECT_PAYMENT_METHOD, ENTER_ACCOUNT, ENTER_AMOUNT = range(3)

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
            # If bot cannot check (e.g., chat not found or bot not admin), keep it in unsubscribed or skip depending on policy
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
    # Build main keyboard with primary actions + dynamic custom buttons added by admin
    keyboard = [
        [InlineKeyboardButton("💰 رصيدي وحسابي", callback_data="user_profile"), InlineKeyboardButton("🔗 رابط الإحالة", callback_data="user_referral")],
        [InlineKeyboardButton("💳 طلب سحب", callback_data="user_withdraw"), InlineKeyboardButton("ℹ️ طرق الدفع المتاحة", callback_data="user_payment_methods")]
    ]

    # Custom inline buttons added by admin
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
        keyboard.append([InlineKeyboardButton("⚙️ لوحة تحكم المدير", callback_data="admin_main")])

    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Check referral ID from args
    referred_by = None
    if context.args:
        try:
            ref_id = int(context.args[0])
            if ref_id != user.id:
                referred_by = ref_id
        except ValueError:
            pass

    # Register user
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

    # Check mandatory subscription
    is_subbed, unsubscribed = await check_user_subscriptions(context.bot, user.id)
    if not is_subbed:
        reply_markup = get_mandatory_sub_keyboard(unsubscribed)
        await update.message.reply_text(
            "⚠️ عذراً عزيزي، يجب عليك الاشتراك في قنوات البوت أولاً لاستخدام البوت!\n\n"
            "يرجى الانضمام للقنوات التالية ثم الضغط على (تحقق من الاشتراك 🔄):",
            reply_markup=reply_markup
        )
        return

    # Reward referrer if verified
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

    # Send Welcome Message
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

    # Reward referrer if verified
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
        f"👤 **معلومات حسابك:**\n\n"
        f"🆔 المعرف: `{u['user_id']}`\n"
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

    text = (
        f"🔗 **رابط الإحالة الخاص بك:**\n\n"
        f"`{ref_link}`\n\n"
        f"💰 **المكافأة:** كسب `${ref_reward}` لكل صديق يقوم بالانضمام والاشتراك بقنوات البوت عبر رابطك!\n"
        f"شارك الرابط مع أصدقائك أو في المجموعات وابدأ بكسب المال 🚀"
    )
    keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]]
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

    # Create withdrawal request in DB
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

    # Notify Admin instantly
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
    await query.edit_message_text("❌ تم إلغاء طلب السحب.", reply_markup=get_main_menu_keyboard(query.from_user.id))
    return ConversationHandler.END
