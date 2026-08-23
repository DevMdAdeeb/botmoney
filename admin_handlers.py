import logging
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

# Admin Conversation States
(
    SET_REF_REWARD,
    SET_MIN_WITHDRAW,
    SET_WELCOME_MSG,
    ADD_CHANNEL_ID,
    ADD_CHANNEL_TITLE,
    ADD_CHANNEL_LINK,
    ADD_PAYMENT_NAME,
    ADD_PAYMENT_INST,
    ADD_BTN_TITLE,
    ADD_BTN_TYPE,
    ADD_BTN_VALUE,
    SEARCH_USER,
    MODIFY_USER_BALANCE,
    BROADCAST_MESSAGE
) = range(14)

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def get_admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📊 إحصائيات البوت", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ إعدادات البوت", callback_data="admin_settings"), InlineKeyboardButton("📢 القنوات الإجبارية", callback_data="admin_channels")],
        [InlineKeyboardButton("💳 طرق الدفع", callback_data="admin_payments"), InlineKeyboardButton("🔘 الأزرار الشفافة", callback_data="admin_buttons")],
        [InlineKeyboardButton("👤 إدارة المستخدمين", callback_data="admin_users"), InlineKeyboardButton("📢 إذاعة لجميع الأعضاء", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def admin_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ ليس لديك صلاحية الوصول لهذه اللوحة.")
        return

    await query.edit_message_text(
        "🛠️ **لوحة تحكم المدير الشاملة**\n\nاختر الخيار الذي تريد التحكم به من الأسفل:",
        parse_mode="Markdown",
        reply_markup=get_admin_dashboard_keyboard()
    )

async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    stats = database.get_stats()
    text = (
        f"📊 **إحصائيات البوت الشاملة:**\n\n"
        f"👥 إجمالي المستخدمين: `{stats['total_users']}`\n"
        f"🔗 إجمالي الإحالات: `{stats['total_referrals']}`\n"
        f"💰 إجمالي المبالغ المدفوعة: `${stats['total_withdrawn']:.2f}`\n"
        f"⏳ طلبات السحب المعلقة: `{stats['pending_withdrawals']}`"
    )
    keyboard = [[InlineKeyboardButton("🔙 العودة للوحة المدير", callback_data="admin_main")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Withdrawal Approval Handler ---
async def admin_withdrawal_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    data = query.data
    if data.startswith("approve_w_"):
        w_id = int(data.replace("approve_w_", ""))
        w = database.process_withdrawal_request(w_id, approve=True)
        if w:
            await query.edit_message_text(f"✅ تم **قَبُول** طلب السحب `#{w_id}` بنجاح!", parse_mode="Markdown")
            try:
                await context.bot.send_message(
                    chat_id=w["user_id"],
                    text=f"🎉 **مبروك!** تم قبول طلب السحب الخاص بك `#{w_id}` بمبلغ `${w['amount']:.2f}` وإرسال الأموال لحسابك.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            await query.edit_message_text("❌ لم يتم العثور على الطلب أو أنه مًعالج سابقاً.")

    elif data.startswith("reject_w_"):
        w_id = int(data.replace("reject_w_", ""))
        w = database.process_withdrawal_request(w_id, approve=False)
        if w:
            await query.edit_message_text(f"❌ تم **رَفْض** طلب السحب `#{w_id}` وإعادة المبلغ لرصيد المستخدم.", parse_mode="Markdown")
            try:
                await context.bot.send_message(
                    chat_id=w["user_id"],
                    text=f"❌ **تنويه:** تم رفض طلب السحب `#{w_id}` بمبلغ `${w['amount']:.2f}` وتمت إعادة المبلغ لرصيدك.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            await query.edit_message_text("❌ لم يتم العثور على الطلب أو أنه مُعالج سابقاً.")

# --- Settings Management ---
async def admin_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    ref_reward = database.get_setting("referral_reward", "0.5")
    min_withdraw = database.get_setting("min_withdrawal", "5.0")
    welcome_msg = database.get_setting("welcome_message")

    text = (
        f"⚙️ **إعدادات البوت الحالية:**\n\n"
        f"💰 سعر الإحالة الواحدة: `${ref_reward}`\n"
        f"💳 الحد الأدنى للسحب: `${min_withdraw}`\n\n"
        f"📝 **رسالة الترحيب الحالية:**\n{welcome_msg}"
    )
    keyboard = [
        [InlineKeyboardButton("✏️ تعديل سعر الإحالة", callback_data="change_ref_reward")],
        [InlineKeyboardButton("✏️ تعديل حد السحب الأدنى", callback_data="change_min_withdraw")],
        [InlineKeyboardButton("✏️ تعديل رسالة الترحيب", callback_data="change_welcome_msg")],
        [InlineKeyboardButton("🔙 العودة للوحة المدير", callback_data="admin_main")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def prompt_ref_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💰 **أدخل سعر/مكافأة الإحالة الواحدة الجديد بالدولار ($):**\nمثال: `0.75`")
    return SET_REF_REWARD

async def save_ref_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        val = float(text)
        database.set_setting("referral_reward", str(val))
        await update.message.reply_text(f"✅ تم تحديث سعر الإحالة إلى: `${val}`", reply_markup=get_admin_dashboard_keyboard())
    except ValueError:
        await update.message.reply_text("❌ يرجى أدخال رقم صحيح (مثال: 0.5):")
        return SET_REF_REWARD
    return ConversationHandler.END

async def prompt_min_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💳 **أدخل الحد الأدنى الجديد للسحب بالدولار ($):**\nمثال: `10.0`")
    return SET_MIN_WITHDRAW

async def save_min_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        val = float(text)
        database.set_setting("min_withdrawal", str(val))
        await update.message.reply_text(f"✅ تم تحديث الحد الأدنى للسحب إلى: `${val}`", reply_markup=get_admin_dashboard_keyboard())
    except ValueError:
        await update.message.reply_text("❌ يرجى أدخال رقم صحيح (مثال: 5.0):")
        return SET_MIN_WITHDRAW
    return ConversationHandler.END

async def prompt_welcome_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    help_txt = (
        "📝 **أدخل نص رسالة الترحيب الجديدة.**\n\n"
        "يمكنك استخدام المتغيرات التالية وسيقوم البوت باستبدالها تلقائياً:\n"
        "• `{name}` : اسم المستخدم\n"
        "• `{id}` : معرف المستخدم\n"
        "• `{balance}` : رصيد المستخدم\n"
        "• `{ref_link}` : رابط الإحالة الخاص بالمستخدم\n"
    )
    await query.edit_message_text(help_txt, parse_mode="Markdown")
    return SET_WELCOME_MSG

async def save_welcome_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    database.set_setting("welcome_message", text)
    await update.message.reply_text("✅ تم تحديث رسالة الترحيب بنجاح!", reply_markup=get_admin_dashboard_keyboard())
    return ConversationHandler.END


# --- Mandatory Channels Management ---
async def admin_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    channels = database.get_all_channels()
    text = "📢 **إدارة القنوات الإجبارية:**\n\n"
    keyboard = []

    if not channels:
        text += "لا توجد قنوات إجبارية مضافة حالياً."
    else:
        for ch in channels:
            text += f"• **{ch['title']}** (`{ch['chat_id']}`)\n🔗 {ch['invite_link']}\n\n"
            keyboard.append([InlineKeyboardButton(f"❌ حذف {ch['title']}", callback_data=f"del_channel_{ch['id']}")])

    keyboard.append([InlineKeyboardButton("➕ إضافة قناة جديدة", callback_data="add_channel")])
    keyboard.append([InlineKeyboardButton("🔙 العودة للوحة المدير", callback_data="admin_main")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ch_id = int(query.data.replace("del_channel_", ""))
    database.remove_channel(ch_id)
    await query.edit_message_text("✅ تم حذف القناة بنجاح.")
    await admin_channels_callback(update, context)

async def prompt_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 **يرجى كتابة معرّف القناة** (مثال: `@mychannel` أو معرف رقمي مثل `-100123456789`):\n\n⚠️ *ملاحظة:* تأكد من إضافة البوت كـ مشرف في القناة أولاً لتفعيل التحقق.")
    return ADD_CHANNEL_ID

async def channel_id_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.text.strip()
    context.user_data["add_ch_id"] = chat_id
    await update.message.reply_text("📝 **أدخل اسم/عنوان القناة** (سيظهر للمستخدمين في زر القناة):")
    return ADD_CHANNEL_TITLE

async def channel_title_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    context.user_data["add_ch_title"] = title
    await update.message.reply_text("🔗 **أدخل رابط الدعوة للقناة** (مثال: `https://t.me/mychannel`):")
    return ADD_CHANNEL_LINK

async def channel_link_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    chat_id = context.user_data.get("add_ch_id")
    title = context.user_data.get("add_ch_title")

    success = database.add_channel(chat_id, title, link)
    if success:
        await update.message.reply_text(f"✅ تم إضافة القناة **{title}** بنجاح!", parse_mode="Markdown", reply_markup=get_admin_dashboard_keyboard())
    else:
        await update.message.reply_text("❌ هذه القناة مضافة بالفعل أو حدث خطأ.", reply_markup=get_admin_dashboard_keyboard())
    return ConversationHandler.END


# --- Payment Methods Management ---
async def admin_payments_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    methods = database.get_all_payment_methods()
    text = "💳 **إدارة طرق الدفع:**\n\n"
    keyboard = []

    if not methods:
        text += "لا توجد طرق دفع مضافة حالياً."
    else:
        for m in methods:
            inst = f"\n📝 تعليمات: {m['instructions']}" if m['instructions'] else ""
            text += f"🔹 **{m['name']}**{inst}\n\n"
            keyboard.append([InlineKeyboardButton(f"❌ حذف {m['name']}", callback_data=f"del_payment_{m['id']}")])

    keyboard.append([InlineKeyboardButton("➕ إضافة طريقة دفع جديدة", callback_data="add_payment")])
    keyboard.append([InlineKeyboardButton("🔙 العودة للوحة المدير", callback_data="admin_main")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    m_id = int(query.data.replace("del_payment_", ""))
    database.remove_payment_method(m_id)
    await query.edit_message_text("✅ تم حذف طريقة الدفع بنجاح.")

async def prompt_add_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💳 **أدخل اسم طريقة الدفع** (مثال: `USDT TRC20`, `Payeer`, `Vodafone Cash`):")
    return ADD_PAYMENT_NAME

async def payment_name_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["add_pay_name"] = name
    await update.message.reply_text("📝 **أدخل تعليمات/ملاحظات طريقة الدفع للمستخدم** (أو أرسل `تخطي`):")
    return ADD_PAYMENT_INST

async def payment_inst_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inst = update.message.text.strip()
    if inst == "تخطي":
        inst = ""
    name = context.user_data.get("add_pay_name")

    success = database.add_payment_method(name, inst)
    if success:
        await update.message.reply_text(f"✅ تم إضافة طريقة الدفع **{name}** بنجاح!", parse_mode="Markdown", reply_markup=get_admin_dashboard_keyboard())
    else:
        await update.message.reply_text("❌ طريقة الدفع مضافة سابقاً.", reply_markup=get_admin_dashboard_keyboard())
    return ConversationHandler.END


# --- Custom Inline Buttons Management ---
async def admin_buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    btns = database.get_all_custom_buttons()
    text = "🔘 **إدارة الأزرار الشفافة التفاعلية:**\n\n"
    keyboard = []

    if not btns:
        text += "لا توجد أزرار شفافة مضافة."
    else:
        for b in btns:
            b_type = "رابط خارجي 🔗" if b['type'] == 'url' else "محتوى نصي 📝"
            text += f"🔸 **{b['title']}** ({b_type})\nالقيم: `{b['value']}`\n\n"
            keyboard.append([InlineKeyboardButton(f"❌ حذف {b['title']}", callback_data=f"del_button_{b['id']}")])

    keyboard.append([InlineKeyboardButton("➕ إضافة زر جديد", callback_data="add_custom_button")])
    keyboard.append([InlineKeyboardButton("🔙 العودة للوحة المدير", callback_data="admin_main")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    b_id = int(query.data.replace("del_button_", ""))
    database.remove_custom_button(b_id)
    await query.edit_message_text("✅ تم حذف الزر بنجاح.")

async def prompt_add_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔘 **أدخل عنوان الزر الذي سيظهر للمستخدمين:**")
    return ADD_BTN_TITLE

async def btn_title_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    context.user_data["add_btn_title"] = title

    keyboard = [
        [InlineKeyboardButton("رابط خارجي 🔗 (URL)", callback_data="btn_type_url")],
        [InlineKeyboardButton("محتوى نصي 📝 (Text Reply)", callback_data="btn_type_text")]
    ]
    await update.message.reply_text("اختر نوع الزر:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_BTN_TYPE

async def btn_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    btn_type = "url" if query.data == "btn_type_url" else "text"
    context.user_data["add_btn_type"] = btn_type

    if btn_type == "url":
        await query.edit_message_text("🔗 **أدخل رابط URL الخارجي للزر** (مثال: `https://t.me/example`):")
    else:
        await query.edit_message_text("📝 **أدخل النص الذي سيظهر للمستخدم عند الضغط على الزر:**")
    return ADD_BTN_VALUE

async def btn_value_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    title = context.user_data.get("add_btn_title")
    btn_type = context.user_data.get("add_btn_type")

    database.add_custom_button(title, btn_type, val)
    await update.message.reply_text(f"✅ تم إضافة الزر الشفاف **{title}** بنجاح!", parse_mode="Markdown", reply_markup=get_admin_dashboard_keyboard())
    return ConversationHandler.END


# --- User Management ---
async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    await query.edit_message_text("👤 **أدخل المعرف (Telegram User ID) للمستخدم للبحث عنه وتعديل رصيده أو حظره:**")
    return SEARCH_USER

async def user_searched(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        u_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ معرف غير صالح. أعد كتابته:")
        return SEARCH_USER

    u = database.get_user(u_id)
    if not u:
        await update.message.reply_text("❌ لم يتم العثور على مستخدم بهذا المعرف في قاعدة البيانات.")
        return ConversationHandler.END

    context.user_data["selected_user_id"] = u_id
    ban_text = "فك الحظر 🔓" if u["is_banned"] else "حظر المستخدم 🚫"
    ban_action = f"unban_{u_id}" if u["is_banned"] else f"ban_{u_id}"

    info_text = (
        f"👤 **معلومات المستخدم:**\n\n"
        f"🆔 المعرف: `{u['user_id']}`\n"
        f"👤 الاسم: {u['first_name']}\n"
        f"💰 الرصيد الحالي: `${u['balance']:.2f}`\n"
        f"👥 عدد الإحالات: `{u['referrals_count']}`\n"
        f"🔒 الحالة: {'محظور ❌' if u['is_banned'] else 'نشط ✅'}"
    )

    keyboard = [
        [InlineKeyboardButton("💰 تعديل الرصيد", callback_data=f"mod_bal_{u_id}")],
        [InlineKeyboardButton(ban_text, callback_data=ban_action)],
        [InlineKeyboardButton("🔙 العودة للوحة المدير", callback_data="admin_main")]
    ]
    await update.message.reply_text(info_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def toggle_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("ban_"):
        u_id = int(data.replace("ban_", ""))
        database.set_user_ban_status(u_id, is_banned=True)
        await query.edit_message_text("🚫 تم حظر المستخدم بنجاح.")
    elif data.startswith("unban_"):
        u_id = int(data.replace("unban_", ""))
        database.set_user_ban_status(u_id, is_banned=False)
        await query.edit_message_text("🔓 تم فك حظر المستخدم بنجاح.")

async def prompt_modify_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    u_id = int(query.data.replace("mod_bal_", ""))
    context.user_data["selected_user_id"] = u_id
    await query.edit_message_text(f"💰 **أدخل المبلغ لإضافته أو خصمه من رصيد المستخدم (`{u_id}`):**\n(أدخل رقم موجب للإضافة مثل `5` أو سالب للخصم مثل `-2`)", parse_mode="Markdown")
    return MODIFY_USER_BALANCE

async def save_modified_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    u_id = context.user_data.get("selected_user_id")
    try:
        amount = float(text)
        database.update_user_balance(u_id, amount)
        await update.message.reply_text(f"✅ تم تعديل رصيد المستخدم `{u_id}` بمقدار `${amount:.2f}`", parse_mode="Markdown", reply_markup=get_admin_dashboard_keyboard())
    except ValueError:
        await update.message.reply_text("❌ يرجى أدخال مبلغ رقمي صحيح:")
        return MODIFY_USER_BALANCE
    return ConversationHandler.END


# --- Broadcast Management ---
async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    await query.edit_message_text("📢 **أرسل الرسالة (نص، صورة، فيديو...) التي تريد توجيها/إرسالها لجميع أعضاء البوت:**")
    return BROADCAST_MESSAGE

async def perform_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    users = database.get_all_users()
    success = 0
    failed = 0

    status_msg = await msg.reply_text("⏳ جاري إرسال الإذاعة للجميع...")

    for u in users:
        try:
            await msg.copy(chat_id=u["user_id"])
            success += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ **تم الانتهاء من الإذاعة!**\n\n"
        f"🟢 نجح الإرسال إلى: `{success}`\n"
        f"🔴 فشل الإرسال إلى: `{failed}`",
        parse_mode="Markdown",
        reply_markup=get_admin_dashboard_keyboard()
    )
    return ConversationHandler.END

async def cancel_admin_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء العملية.", reply_markup=get_admin_dashboard_keyboard())
    return ConversationHandler.END
