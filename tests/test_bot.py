import pytest
import os
import database
from config import ADMIN_ID

TEST_DB = "test_bot.db"

@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    database.init_db(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_user_registration_and_referral():
    # Register referrer
    assert database.register_user(1111, "Alice", "alice", db_path=TEST_DB) is True
    # Duplicate registration should return False
    assert database.register_user(1111, "Alice", "alice", db_path=TEST_DB) is False

    # Register referee
    assert database.register_user(2222, "Bob", "bob", referred_by=1111, db_path=TEST_DB) is True

    # Check user data before reward
    referee = database.get_user(2222, db_path=TEST_DB)
    assert referee["referred_by"] == 1111

    # Reward referrer
    reward_res = database.reward_referrer_if_pending(2222, db_path=TEST_DB)
    assert reward_res == (1111, 0.5)

    # Verify referrer balance and count
    referrer = database.get_user(1111, db_path=TEST_DB)
    assert referrer["balance"] == 0.5
    assert referrer["referrals_count"] == 1

def test_settings_management():
    database.set_setting("referral_reward", "1.5", db_path=TEST_DB)
    assert database.get_setting("referral_reward", db_path=TEST_DB) == "1.5"

    database.set_setting("min_withdrawal", "10.0", db_path=TEST_DB)
    assert database.get_setting("min_withdrawal", db_path=TEST_DB) == "10.0"

def test_channels_management():
    assert database.add_channel("@testchannel", "Test Channel", "https://t.me/testchannel", db_path=TEST_DB) is True
    channels = database.get_all_channels(db_path=TEST_DB)
    assert len(channels) == 1
    assert channels[0]["chat_id"] == "@testchannel"

    assert database.remove_channel(channels[0]["id"], db_path=TEST_DB) is True
    assert len(database.get_all_channels(db_path=TEST_DB)) == 0

def test_payment_methods_management():
    assert database.add_payment_method("Vodafone Cash", "Send to 01000000000", db_path=TEST_DB) is True
    methods = database.get_all_payment_methods(db_path=TEST_DB)
    assert len(methods) == 1
    assert methods[0]["name"] == "Vodafone Cash"

    assert database.remove_payment_method(methods[0]["id"], db_path=TEST_DB) is True
    assert len(database.get_all_payment_methods(db_path=TEST_DB)) == 0

def test_custom_buttons_management():
    assert database.add_custom_button("Our Website", "url", "https://example.com", db_path=TEST_DB) is True
    btns = database.get_all_custom_buttons(db_path=TEST_DB)
    assert len(btns) == 1
    assert btns[0]["title"] == "Our Website"
    assert btns[0]["type"] == "url"

    assert database.remove_custom_button(btns[0]["id"], db_path=TEST_DB) is True
    assert len(database.get_all_custom_buttons(db_path=TEST_DB)) == 0

def test_withdrawal_workflow():
    database.register_user(3333, "Charlie", "charlie", db_path=TEST_DB)
    database.update_user_balance(3333, 20.0, db_path=TEST_DB)

    # Insufficient balance check
    w_invalid = database.create_withdrawal_request(3333, "USDT", "0x123...", 50.0, db_path=TEST_DB)
    assert w_invalid is None

    # Valid request
    w_id = database.create_withdrawal_request(3333, "USDT", "0x123...", 10.0, db_path=TEST_DB)
    assert w_id is not None

    # Check balance after request
    user = database.get_user(3333, db_path=TEST_DB)
    assert user["balance"] == 10.0

    # Reject request -> Refund balance
    rejected_w = database.process_withdrawal_request(w_id, approve=False, db_path=TEST_DB)
    assert rejected_w["status"] == "rejected"

    user_after_reject = database.get_user(3333, db_path=TEST_DB)
    assert user_after_reject["balance"] == 20.0

def test_user_ban_status():
    database.register_user(4444, "Dave", "dave", db_path=TEST_DB)
    assert database.set_user_ban_status(4444, is_banned=True, db_path=TEST_DB) is True
    user = database.get_user(4444, db_path=TEST_DB)
    assert user["is_banned"] == 1

    assert database.set_user_ban_status(4444, is_banned=False, db_path=TEST_DB) is True
    user = database.get_user(4444, db_path=TEST_DB)
    assert user["is_banned"] == 0
