import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters
)

from config import BOT_TOKEN, ADMIN_ID
import database
import user_handlers
import admin_handlers

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    # Initialize SQLite Database
    database.init_db()
    logger.info("Database initialized successfully.")

    # Create Application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # --- User Conversation Handlers ---
    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(user_handlers.start_withdraw_callback, pattern="^user_withdraw$")],
        states={
            user_handlers.SELECT_PAYMENT_METHOD: [
                CallbackQueryHandler(user_handlers.payment_method_selected, pattern="^select_pay_")
            ],
            user_handlers.ENTER_ACCOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, user_handlers.account_details_entered)
            ],
            user_handlers.ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, user_handlers.amount_entered)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(user_handlers.cancel_withdraw_callback, pattern="^cancel_withdraw$"),
            CommandHandler("start", user_handlers.start_command)
        ],
        per_message=False
    )
    application.add_handler(withdraw_conv)

    # --- Admin Settings Conversation Handlers ---
    ref_reward_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_handlers.prompt_ref_reward, pattern="^change_ref_reward$")],
        states={
            admin_handlers.SET_REF_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.save_ref_reward)]
        },
        fallbacks=[CommandHandler("cancel", admin_handlers.cancel_admin_conv)],
        per_message=False
    )
    application.add_handler(ref_reward_conv)

    min_withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_handlers.prompt_min_withdraw, pattern="^change_min_withdraw$")],
        states={
            admin_handlers.SET_MIN_WITHDRAW: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.save_min_withdraw)]
        },
        fallbacks=[CommandHandler("cancel", admin_handlers.cancel_admin_conv)],
        per_message=False
    )
    application.add_handler(min_withdraw_conv)

    welcome_msg_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_handlers.prompt_welcome_msg, pattern="^change_welcome_msg$")],
        states={
            admin_handlers.SET_WELCOME_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.save_welcome_msg)]
        },
        fallbacks=[CommandHandler("cancel", admin_handlers.cancel_admin_conv)],
        per_message=False
    )
    application.add_handler(welcome_msg_conv)

    # Add Mandatory Channel Conv
    add_channel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_handlers.prompt_add_channel, pattern="^add_channel$")],
        states={
            admin_handlers.ADD_CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.channel_id_entered)],
            admin_handlers.ADD_CHANNEL_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.channel_title_entered)],
            admin_handlers.ADD_CHANNEL_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.channel_link_entered)]
        },
        fallbacks=[CommandHandler("cancel", admin_handlers.cancel_admin_conv)],
        per_message=False
    )
    application.add_handler(add_channel_conv)

    # Add Payment Method Conv
    add_payment_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_handlers.prompt_add_payment, pattern="^add_payment$")],
        states={
            admin_handlers.ADD_PAYMENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.payment_name_entered)],
            admin_handlers.ADD_PAYMENT_INST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.payment_inst_entered)]
        },
        fallbacks=[CommandHandler("cancel", admin_handlers.cancel_admin_conv)],
        per_message=False
    )
    application.add_handler(add_payment_conv)

    # Add Custom Inline Button Conv
    add_button_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_handlers.prompt_add_button, pattern="^add_custom_button$")],
        states={
            admin_handlers.ADD_BTN_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.btn_title_entered)],
            admin_handlers.ADD_BTN_TYPE: [CallbackQueryHandler(admin_handlers.btn_type_selected, pattern="^btn_type_")],
            admin_handlers.ADD_BTN_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.btn_value_entered)]
        },
        fallbacks=[CommandHandler("cancel", admin_handlers.cancel_admin_conv)],
        per_message=False
    )
    application.add_handler(add_button_conv)

    # Search / Edit User Conv
    user_mgmt_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_handlers.admin_users_callback, pattern="^admin_users$"),
            CallbackQueryHandler(admin_handlers.prompt_modify_balance, pattern="^mod_bal_")
        ],
        states={
            admin_handlers.SEARCH_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.user_searched)],
            admin_handlers.MODIFY_USER_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.save_modified_balance)]
        },
        fallbacks=[CommandHandler("cancel", admin_handlers.cancel_admin_conv)],
        per_message=False
    )
    application.add_handler(user_mgmt_conv)

    # Broadcast Conv
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_handlers.admin_broadcast_callback, pattern="^admin_broadcast$")],
        states={
            admin_handlers.BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, admin_handlers.perform_broadcast)]
        },
        fallbacks=[CommandHandler("cancel", admin_handlers.cancel_admin_conv)],
        per_message=False
    )
    application.add_handler(broadcast_conv)

    # --- Standard Command Handlers ---
    application.add_handler(CommandHandler("start", user_handlers.start_command))

    # --- Callback Query Handlers ---
    application.add_handler(CallbackQueryHandler(user_handlers.check_subscription_callback, pattern="^check_subscription$"))
    application.add_handler(CallbackQueryHandler(user_handlers.user_profile_callback, pattern="^user_profile$"))
    application.add_handler(CallbackQueryHandler(user_handlers.user_referral_callback, pattern="^user_referral$"))
    application.add_handler(CallbackQueryHandler(user_handlers.user_payment_methods_callback, pattern="^user_payment_methods$"))
    application.add_handler(CallbackQueryHandler(user_handlers.main_menu_callback, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(user_handlers.custom_btn_callback, pattern="^custom_btn_"))

    # Admin Dashboard Callbacks
    application.add_handler(CallbackQueryHandler(admin_handlers.admin_main_callback, pattern="^admin_main$"))
    application.add_handler(CallbackQueryHandler(admin_handlers.admin_stats_callback, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(admin_handlers.admin_settings_callback, pattern="^admin_settings$"))
    application.add_handler(CallbackQueryHandler(admin_handlers.admin_channels_callback, pattern="^admin_channels$"))
    application.add_handler(CallbackQueryHandler(admin_handlers.admin_payments_callback, pattern="^admin_payments$"))
    application.add_handler(CallbackQueryHandler(admin_handlers.admin_buttons_callback, pattern="^admin_buttons$"))

    # Admin Action Callbacks
    application.add_handler(CallbackQueryHandler(admin_handlers.delete_channel_callback, pattern="^del_channel_"))
    application.add_handler(CallbackQueryHandler(admin_handlers.delete_payment_callback, pattern="^del_payment_"))
    application.add_handler(CallbackQueryHandler(admin_handlers.delete_button_callback, pattern="^del_button_"))
    application.add_handler(CallbackQueryHandler(admin_handlers.admin_withdrawal_action_callback, pattern="^(approve_w_|reject_w_)"))
    application.add_handler(CallbackQueryHandler(admin_handlers.toggle_ban_callback, pattern="^(ban_|unban_)"))

    logger.info("Starting Telegram Earning Bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
