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
    assert database.register_user(1111, "Alice", "alice", db_path=TEST_DB) is True
    assert database.register_user(1111, "Alice", "alice", db_path=TEST_DB) is False
    assert database.register_user(2222, "Bob", "bob", referred_by=1111, db_path=TEST_DB) is True

    referee = database.get_user(2222, db_path=TEST_DB)
    assert referee["referred_by"] == 1111

    reward_res = database.reward_referrer_if_pending(2222, db_path=TEST_DB)
    assert reward_res == (1111, 0.5)

    referrer = database.get_user(1111, db_path=TEST_DB)
    assert referrer["balance"] == 0.5
    assert referrer["referrals_count"] == 1

def test_captcha_verification():
    database.register_user(5555, "Eve", "eve", db_path=TEST_DB)
    u = database.get_user(5555, db_path=TEST_DB)
    assert u["captcha_verified"] == 0

    database.set_captcha_verified(5555, db_path=TEST_DB)
    u_after = database.get_user(5555, db_path=TEST_DB)
    assert u_after["captcha_verified"] == 1

def test_daily_bonus_flow():
    database.register_user(6666, "Frank", "frank", db_path=TEST_DB)
    assert database.can_claim_daily_bonus(6666, db_path=TEST_DB) is True

    claimed = database.claim_daily_bonus(6666, 0.10, db_path=TEST_DB)
    assert claimed is True

    u = database.get_user(6666, db_path=TEST_DB)
    assert u["balance"] == 0.10

    assert database.can_claim_daily_bonus(6666, db_path=TEST_DB) is False

def test_gift_codes_system():
    database.register_user(7777, "George", "george", db_path=TEST_DB)
    assert database.create_gift_code("GIFT50", 0.50, max_uses=2, db_path=TEST_DB) is True

    # Redeem code
    success, msg, amount = database.redeem_gift_code(7777, "GIFT50", db_path=TEST_DB)
    assert success is True
    assert amount == 0.50

    # User tries to redeem twice -> blocked
    success2, msg2, amount2 = database.redeem_gift_code(7777, "GIFT50", db_path=TEST_DB)
    assert success2 is False

def test_micro_tasks_system():
    database.register_user(8888, "Hannah", "hannah", db_path=TEST_DB)
    assert database.add_task("Sub Channel Task", 0.20, "https://t.me/example", db_path=TEST_DB) is True

    tasks = database.get_available_tasks_for_user(8888, db_path=TEST_DB)
    assert len(tasks) == 1
    t_id = tasks[0]["id"]

    success, msg, amount = database.complete_task(8888, t_id, db_path=TEST_DB)
    assert success is True
    assert amount == 0.20

    # Check completed task no longer listed as available
    avail = database.get_available_tasks_for_user(8888, db_path=TEST_DB)
    assert len(avail) == 0

def test_leaderboard():
    database.register_user(101, "User1", "u1", db_path=TEST_DB)
    database.register_user(102, "User2", "u2", db_path=TEST_DB)

    database.register_user(201, "Ref1", "r1", referred_by=101, db_path=TEST_DB)
    database.reward_referrer_if_pending(201, db_path=TEST_DB)
    database.register_user(202, "Ref2", "r2", referred_by=101, db_path=TEST_DB)
    database.reward_referrer_if_pending(202, db_path=TEST_DB)

    top = database.get_top_referrers(10, db_path=TEST_DB)
    assert len(top) >= 2
    assert top[0]["user_id"] == 101
    assert top[0]["referrals_count"] == 2

def test_settings_management():
    database.set_setting("referral_reward", "1.5", db_path=TEST_DB)
    assert database.get_setting("referral_reward", db_path=TEST_DB) == "1.5"

    database.set_setting("min_withdrawal", "10.0", db_path=TEST_DB)
    assert database.get_setting("min_withdrawal", db_path=TEST_DB) == "10.0"

    database.set_setting("proof_channel_id", "@proofch", db_path=TEST_DB)
    assert database.get_setting("proof_channel_id", db_path=TEST_DB) == "@proofch"

def test_withdrawal_workflow():
    database.register_user(3333, "Charlie", "charlie", db_path=TEST_DB)
    database.update_user_balance(3333, 20.0, db_path=TEST_DB)

    w_invalid = database.create_withdrawal_request(3333, "USDT", "0x123...", 50.0, db_path=TEST_DB)
    assert w_invalid is None

    w_id = database.create_withdrawal_request(3333, "USDT", "0x123...", 10.0, db_path=TEST_DB)
    assert w_id is not None

    user = database.get_user(3333, db_path=TEST_DB)
    assert user["balance"] == 10.0

    rejected_w = database.process_withdrawal_request(w_id, approve=False, db_path=TEST_DB)
    assert rejected_w["status"] == "rejected"

    user_after_reject = database.get_user(3333, db_path=TEST_DB)
    assert user_after_reject["balance"] == 20.0
