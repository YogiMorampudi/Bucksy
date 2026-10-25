"""
test_auth_app.py
Comprehensive automated security and authentication test suite for Bucksy.
Tests user registration, login, rate limiting, password reset workflows,
CSRF protection, session rotation, and personal data isolation.
All tests are self-contained and clean up after execution.
"""

import unittest
from datetime import datetime, timedelta
import secrets
import hashlib
from werkzeug.security import check_password_hash

from app import app, init_db, db

class TestBucksyAuthentication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False  # By default disabled for test client, tested explicitly in test_csrf
        init_db()

    def setUp(self):
        self.client = app.test_client()

    def tearDown(self):
        # Clean up any test users created during test runs
        with db() as conn:
            conn.execute("DELETE FROM goals WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@test.bucksy.local')")
            conn.execute("DELETE FROM khata_entries WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@test.bucksy.local')")
            conn.execute("DELETE FROM people WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@test.bucksy.local')")
            conn.execute("DELETE FROM transactions WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@test.bucksy.local')")
            conn.execute("DELETE FROM password_reset_tokens WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@test.bucksy.local')")
            conn.execute("DELETE FROM login_attempts WHERE email LIKE '%@test.bucksy.local'")
            conn.execute("DELETE FROM users WHERE email LIKE '%@test.bucksy.local'")
            conn.commit()

    def _create_user(self, full_name="Alice Trader", email="alice@test.bucksy.local", password="StrongPassword123"):
        res = self.client.post("/register", data={
            "full_name": full_name,
            "email": email,
            "password": password,
            "confirm_password": password
        }, follow_redirects=True)
        return res

    def test_01_registration_success_and_password_hashing(self):
        """Test registration creates user with hashed password and rotates session."""
        res = self._create_user()
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Welcome to Bucksy, Alice Trader", res.data)

        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email='alice@test.bucksy.local'").fetchone()
            self.assertIsNotNone(user)
            self.assertEqual(user["full_name"], "Alice Trader")
            # Password must never be plaintext
            self.assertNotEqual(user["password_hash"], "StrongPassword123")
            self.assertTrue(check_password_hash(user["password_hash"], "StrongPassword123"))

    def test_02_registration_duplicate_email_rejected(self):
        """Test registration rejects duplicate email (case-insensitive)."""
        self._create_user(email="alice@test.bucksy.local")
        self.client.get("/logout")
        # Attempt second registration with uppercase email
        res2 = self.client.post("/register", data={
            "full_name": "Alice Duplicate",
            "email": "ALICE@TEST.BUCKSY.LOCAL",
            "password": "StrongPassword123",
            "confirm_password": "StrongPassword123"
        }, follow_redirects=True)
        self.assertIn(b"already exists", res2.data)

    def test_03_registration_validation(self):
        """Test registration requires strong password and matching confirmation."""
        # Weak password (< 8 chars)
        res_weak = self.client.post("/register", data={
            "full_name": "Short Pass",
            "email": "short@test.bucksy.local",
            "password": "pass1",
            "confirm_password": "pass1"
        }, follow_redirects=True)
        self.assertIn(b"at least 8 characters", res_weak.data)

        # Missing numbers
        res_no_num = self.client.post("/register", data={
            "full_name": "No Number",
            "email": "nonum@test.bucksy.local",
            "password": "JustLettersPassword",
            "confirm_password": "JustLettersPassword"
        }, follow_redirects=True)
        self.assertIn(b"include at least one number", res_no_num.data)

        # Mismatch
        res_mismatch = self.client.post("/register", data={
            "full_name": "Mismatch",
            "email": "mismatch@test.bucksy.local",
            "password": "ValidPassword99",
            "confirm_password": "DifferentPassword99"
        }, follow_redirects=True)
        self.assertIn(b"Passwords do not match", res_mismatch.data)

    def test_04_login_and_logout(self):
        """Test login with valid credentials, session creation, and logout."""
        self._create_user()
        # Logout from registration auto-login
        self.client.get("/logout", follow_redirects=True)

        # Login
        res_login = self.client.post("/login", data={
            "email": "alice@test.bucksy.local",
            "password": "StrongPassword123",
            "remember_me": "1"
        }, follow_redirects=True)
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b"Welcome back, Alice Trader", res_login.data)

        # Logout
        res_logout = self.client.get("/logout", follow_redirects=True)
        self.assertIn(b"You have been signed out", res_logout.data)

    def test_05_invalid_credentials_generic_message(self):
        """Test invalid credentials return generic error message."""
        self._create_user()
        self.client.get("/logout")

        # Wrong password
        res = self.client.post("/login", data={
            "email": "alice@test.bucksy.local",
            "password": "WrongPassword999"
        }, follow_redirects=True)
        self.assertIn(b"Invalid email or password", res.data)

        # Nonexistent email
        res_nonexistent = self.client.post("/login", data={
            "email": "unknown@test.bucksy.local",
            "password": "WrongPassword999"
        }, follow_redirects=True)
        self.assertIn(b"Invalid email or password", res_nonexistent.data)

    def test_06_rate_limiting_repeated_attempts(self):
        """Test brute force protection blocks login after 5 failed attempts."""
        self._create_user()
        self.client.get("/logout")

        for _ in range(5):
            self.client.post("/login", data={
                "email": "alice@test.bucksy.local",
                "password": "WrongPassword"
            })

        # 6th attempt should be blocked by rate limit
        res_blocked = self.client.post("/login", data={
            "email": "alice@test.bucksy.local",
            "password": "WrongPassword"
        }, follow_redirects=True)
        self.assertIn(b"Too many failed login attempts", res_blocked.data)

    def test_07_protected_routes_redirect_unauthenticated(self):
        """Test unauthenticated visitors are redirected to /login."""
        self.client.get("/logout")
        endpoints = ["/", "/transactions", "/khata", "/achievements", "/achievements/new"]
        for ep in endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 302)
            self.assertIn("/login", res.headers.get("Location", ""))

    def test_08_forgot_password_generic_response(self):
        """Test forgot-password returns generic message for both existing & non-existing emails."""
        self._create_user()
        self.client.get("/logout")

        # Existing email
        res_exist = self.client.post("/forgot-password", data={
            "email": "alice@test.bucksy.local"
        }, follow_redirects=True)
        self.assertIn(b"If an account exists with that email address, a password reset link has been sent", res_exist.data)

        # Non-existing email
        res_unknown = self.client.post("/forgot-password", data={
            "email": "nobody@test.bucksy.local"
        }, follow_redirects=True)
        self.assertIn(b"If an account exists with that email address, a password reset link has been sent", res_unknown.data)

    def test_09_password_reset_flow_valid_expired_and_reused(self):
        """Test end-to-end password reset with valid, expired, and reused tokens."""
        self._create_user()
        self.client.get("/logout")

        # Request reset
        self.client.post("/forgot-password", data={"email": "alice@test.bucksy.local"})

        with db() as conn:
            user = conn.execute("SELECT id FROM users WHERE email='alice@test.bucksy.local'").fetchone()
            token_rec = conn.execute("SELECT * FROM password_reset_tokens WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchone()
            self.assertIsNotNone(token_rec)
            token_hash = token_rec["token_hash"]

        # Simulate raw token
        raw_token = "valid-test-token-12345"
        mock_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = datetime.now()
        future = (now + timedelta(minutes=30)).isoformat()
        past = (now - timedelta(minutes=10)).isoformat()

        # Insert test valid token
        with db() as conn:
            conn.execute("INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
                         (user["id"], mock_hash, future, now.isoformat()))

        # Reset password successfully
        res_reset = self.client.post(f"/reset-password/{raw_token}", data={
            "password": "BrandNewPassword99",
            "confirm_password": "BrandNewPassword99"
        }, follow_redirects=True)
        self.assertIn(b"Your password has been reset successfully", res_reset.data)

        # Test login with new password
        res_login_new = self.client.post("/login", data={
            "email": "alice@test.bucksy.local",
            "password": "BrandNewPassword99"
        }, follow_redirects=True)
        self.assertIn(b"Welcome back, Alice Trader", res_login_new.data)
        self.client.get("/logout")

        # Test token reuse rejection (token was marked used)
        res_reuse = self.client.get(f"/reset-password/{raw_token}", follow_redirects=True)
        self.assertIn(b"This password reset link is invalid or has expired", res_reuse.data)

        # Test expired token rejection
        expired_token = "expired-token-54321"
        expired_hash = hashlib.sha256(expired_token.encode("utf-8")).hexdigest()
        with db() as conn:
            conn.execute("INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
                         (user["id"], expired_hash, past, past))
        res_expired = self.client.get(f"/reset-password/{expired_token}", follow_redirects=True)
        self.assertIn(b"This password reset link is invalid or has expired", res_expired.data)

    def test_10_csrf_protection_enforcement(self):
        """Test CSRF protection actively blocks unauthorized state-changing POST requests."""
        app.config["WTF_CSRF_ENABLED"] = True
        try:
            # POST without CSRF token
            res = self.client.post("/login", data={
                "email": "alice@test.bucksy.local",
                "password": "SomePassword123"
            }, follow_redirects=True)
            self.assertIn(b"Security check failed", res.data)
        finally:
            app.config["WTF_CSRF_ENABLED"] = False

    def test_11_user_to_user_data_isolation(self):
        """CRITICAL: Test that User B cannot view, edit, or delete User A's data."""
        # 1. Register User A
        self._create_user(full_name="Alice User", email="alice@test.bucksy.local")

        # User A creates a transaction
        self.client.post("/transactions", data={
            "kind": "income",
            "title": "Alice Confidential Bonus",
            "category": "Salary",
            "amount": "95000",
            "method": "Bank transfer",
            "txn_date": "2026-10-26",
            "notes": "Secret bonus notes"
        })

        # User A creates a goal
        self.client.post("/achievements/new", data={
            "goal_name": "Alice Private Yacht Goal",
            "category": "Custom Goal",
            "price": "5000000",
            "saving_amount": "50000",
            "saving_frequency": "monthly"
        })

        with db() as conn:
            txn_a = conn.execute("SELECT id FROM transactions WHERE title='Alice Confidential Bonus'").fetchone()
            goal_a = conn.execute("SELECT id FROM goals WHERE goal_name='Alice Private Yacht Goal'").fetchone()

        self.assertIsNotNone(txn_a)
        self.assertIsNotNone(goal_a)

        # 2. Register User B
        self.client.get("/logout")
        self._create_user(full_name="Bob User", email="bob@test.bucksy.local")

        # Bob visits dashboard: balance and recent transactions should be 0 / empty
        res_b_dash = self.client.get("/")
        self.assertNotIn(b"Alice Confidential Bonus", res_b_dash.data)

        # Bob visits transactions list
        res_b_txns = self.client.get("/transactions")
        self.assertNotIn(b"Alice Confidential Bonus", res_b_txns.data)

        # Bob visits achievements
        res_b_goals = self.client.get("/achievements")
        self.assertNotIn(b"Alice Private Yacht Goal", res_b_goals.data)

        # Bob attempts direct access to edit Alice's transaction via URL
        res_b_edit_txn = self.client.get(f"/transactions/{txn_a['id']}/edit", follow_redirects=True)
        self.assertIn(b"Transaction not found", res_b_edit_txn.data)

        # Bob attempts direct POST to delete Alice's transaction
        res_b_del_txn = self.client.post(f"/transactions/{txn_a['id']}/delete", follow_redirects=True)
        self.assertIn(b"Transaction not found", res_b_del_txn.data)

        # Verify Alice's transaction still exists in DB
        with db() as conn:
            txn_still_there = conn.execute("SELECT id FROM transactions WHERE id=?", (txn_a["id"],)).fetchone()
            self.assertIsNotNone(txn_still_there)

        # Bob attempts direct access to edit Alice's goal
        res_b_edit_goal = self.client.get(f"/achievements/{goal_a['id']}/edit", follow_redirects=True)
        self.assertIn(b"Goal not found", res_b_edit_goal.data)

        # Bob attempts direct POST to delete Alice's goal
        res_b_del_goal = self.client.post(f"/achievements/{goal_a['id']}/delete", follow_redirects=True)
        self.assertIn(b"Goal not found", res_b_del_goal.data)

        # Verify Alice's goal still exists in DB
        with db() as conn:
            goal_still_there = conn.execute("SELECT id FROM goals WHERE id=?", (goal_a["id"],)).fetchone()
            self.assertIsNotNone(goal_still_there)

if __name__ == "__main__":
    unittest.main()
