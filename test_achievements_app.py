"""
test_achievements_app.py
Comprehensive automated test suite for Bucksy Achievement Calculator.
All tests are self-contained.
"""

import unittest
from app import app, init_db, db
from achievements_engine import calculate_savings_plan, add_calendar_months, search_product_prices
from datetime import date
import json

class TestAchievementCalculator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        init_db()
        with db() as conn:
            # Create a dedicated test user
            cur = conn.execute("""
                INSERT OR IGNORE INTO users (full_name, email, password_hash, created_at, updated_at)
                VALUES ('Achievement Tester', 'achievement_test@bucksy.local', 'dummyhash', datetime('now'), datetime('now'))
            """)
            user = conn.execute("SELECT id FROM users WHERE email='achievement_test@bucksy.local'").fetchone()
            cls.user_id = user["id"]
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        with db() as conn:
            conn.execute("DELETE FROM goals WHERE user_id=?", (cls.user_id,))
            conn.execute("DELETE FROM users WHERE id=?", (cls.user_id,))
            conn.commit()

    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user_id

    def test_01_existing_endpoints_preserved(self):
        """Verify existing Bucksy features still work seamlessly."""
        res_dash = self.client.get("/")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b"Overview", res_dash.data)

        res_txns = self.client.get("/transactions")
        self.assertEqual(res_txns.status_code, 200)
        self.assertIn(b"Transactions", res_txns.data)

        res_khata = self.client.get("/khata")
        self.assertEqual(res_khata.status_code, 200)
        self.assertIn(b"Khata Book", res_khata.data)

    def test_02_achievements_dashboard_view(self):
        """Verify achievements page renders with metrics and simulator."""
        res = self.client.get("/achievements")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Achievement Calculator", res.data)
        self.assertIn(b"Interactive Savings Simulator", res.data)

    def test_03_create_goal_daily_plan(self):
        """Test creating a ₹80,000 target with ₹10,000 savings and ₹100/day contributions."""
        res_post = self.client.post("/achievements/new", data={
            "goal_name": "Test iPhone 17 Target",
            "category": "Smartphones",
            "product_model": "128GB",
            "price": "80000",
            "extra_costs": "0",
            "current_savings": "10000",
            "saving_amount": "100",
            "saving_frequency": "daily",
            "priority": "High",
            "product_source": "Apple Store India MRP",
            "target_date": "",
            "notes": "Freelance side gig"
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertIn(b"created successfully", res_post.data)
        self.assertIn(b"Test iPhone 17 Target", res_post.data)

    def test_04_create_goal_extra_costs_vehicle(self):
        """Test vehicle goal with on-road price extra costs."""
        res_post = self.client.post("/achievements/new", data={
            "goal_name": "Test Royal Enfield Hunter 350",
            "category": "Vehicles & Bikes",
            "product_model": "Dapper Series",
            "price": "169656",
            "extra_costs": "26144",
            "current_savings": "50000",
            "saving_amount": "500",
            "saving_frequency": "daily",
            "priority": "High",
            "product_source": "Royal Enfield Official India",
            "target_date": "",
            "notes": "Includes RTO and Insurance"
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)

        with db() as conn:
            goal = conn.execute("SELECT * FROM goals WHERE goal_name='Test Royal Enfield Hunter 350'").fetchone()
            self.assertIsNotNone(goal)
            total = goal["price"] + goal["extra_costs"]
            self.assertEqual(total, 195800.0)

    def test_05_add_savings_deposit(self):
        """Test depositing savings toward an existing goal."""
        with db() as conn:
            goal = conn.execute("SELECT * FROM goals WHERE goal_name='Test iPhone 17 Target'").fetchone()
            if not goal:
                conn.execute("""INSERT INTO goals (goal_name, price, saving_amount, saving_frequency, status, created_at, updated_at)
                                VALUES ('Test iPhone 17 Target', 80000, 100, 'daily', 'active', '2026-10-26', '2026-10-26')""")
                goal = conn.execute("SELECT * FROM goals WHERE goal_name='Test iPhone 17 Target'").fetchone()
            goal_id = goal["id"]

        res = self.client.post(f"/achievements/{goal_id}/add_savings", data={
            "deposit_amount": "5000"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with db() as conn:
            updated = conn.execute("SELECT current_savings FROM goals WHERE id=?", (goal_id,)).fetchone()
            self.assertTrue(updated["current_savings"] >= 5000.0)

    def test_06_goal_achievement_auto_status(self):
        """Test that reaching the target automatically marks goal as achieved."""
        with db() as conn:
            goal = conn.execute("SELECT * FROM goals WHERE goal_name='Test iPhone 17 Target'").fetchone()
            goal_id = goal["id"]
            price = goal["price"] + goal["extra_costs"]
            needed = price - goal["current_savings"]

        res = self.client.post(f"/achievements/{goal_id}/add_savings", data={
            "deposit_amount": str(needed)
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with db() as conn:
            updated = conn.execute("SELECT status FROM goals WHERE id=?", (goal_id,)).fetchone()
            self.assertEqual(updated["status"], "achieved")

    def test_07_edit_and_toggle_goal(self):
        """Test editing goal properties and toggling status."""
        with db() as conn:
            goal = conn.execute("SELECT * FROM goals WHERE goal_name='Test Royal Enfield Hunter 350'").fetchone()
            goal_id = goal["id"]

        res_edit = self.client.post(f"/achievements/{goal_id}/edit", data={
            "goal_name": "Test Royal Enfield Hunter 350 Custom",
            "category": "Vehicles & Bikes",
            "product_model": "Dapper Ash",
            "price": "169656",
            "extra_costs": "26144",
            "current_savings": "50000",
            "saving_amount": "1000",
            "saving_frequency": "daily",
            "priority": "High",
            "status": "active",
            "product_source": "Royal Enfield",
            "target_date": "",
            "notes": "Increased pace"
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        self.assertIn(b"updated successfully", res_edit.data)

        # Toggle status
        res_toggle = self.client.post(f"/achievements/{goal_id}/status", follow_redirects=True)
        self.assertEqual(res_toggle.status_code, 200)

    def test_08_delete_goal(self):
        """Test deleting a goal."""
        with db() as conn:
            goal = conn.execute("SELECT * FROM goals WHERE goal_name='Test iPhone 17 Target'").fetchone()
            goal_id = goal["id"]

        res_del = self.client.post(f"/achievements/{goal_id}/delete", follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIn(b"Goal deleted successfully", res_del.data)

    def test_09_api_product_search(self):
        """Test product lookup API endpoint with vehicles, electronics, and fallback."""
        res_bike = self.client.get("/api/product-search?q=Hunter+350")
        self.assertEqual(res_bike.status_code, 200)
        data_bike = json.loads(res_bike.data)
        self.assertTrue(len(data_bike["results"]) > 0)
        variants = data_bike["results"][0]["variants"]
        self.assertTrue(any("on_road_price" in v for v in variants))

        res_swift = self.client.get("/api/product-search?q=Swift")
        self.assertEqual(res_swift.status_code, 200)
        data_swift = json.loads(res_swift.data)
        self.assertTrue(len(data_swift["results"]) > 0)

        res_mac = self.client.get("/api/product-search?q=MacBook+Air")
        self.assertEqual(res_mac.status_code, 200)
        data_mac = json.loads(res_mac.data)
        self.assertTrue(len(data_mac["results"]) > 0)

        res_unknown = self.client.get("/api/product-search?q=NonExistentGadgetXYZ")
        self.assertEqual(res_unknown.status_code, 200)
        data_unknown = json.loads(res_unknown.data)
        self.assertEqual(len(data_unknown["results"]), 0)
        self.assertIn("manual_entry_required", data_unknown["source_type"])

    def test_10_api_calculate_savings(self):
        """Test JSON savings calculation and scenario API."""
        payload = {
            "target_price": 80000,
            "current_savings": 10000,
            "extra_costs": 0,
            "saving_amount": 100,
            "saving_frequency": "daily"
        }
        res = self.client.post("/api/calculate-savings", json=payload)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data["plan"]["remaining_amount"], 70000.0)
        self.assertEqual(data["plan"]["days_required"], 700)
        self.assertEqual(len(data["scenarios"]), 8)

    def test_11_input_validation(self):
        """Verify invalid or zero saving contributions are rejected."""
        res1 = self.client.post("/achievements/new", data={
            "goal_name": "Zero Saving Test",
            "price": "50000",
            "saving_amount": "0"
        }, follow_redirects=True)
        self.assertIn(b"must be greater than", res1.data)

        res2 = self.client.post("/achievements/new", data={
            "goal_name": "Zero Price Test",
            "price": "0",
            "saving_amount": "100"
        }, follow_redirects=True)
        self.assertIn(b"must be greater than", res2.data)

        res3 = self.client.post("/achievements/new", data={
            "goal_name": "",
            "price": "50000",
            "saving_amount": "100"
        }, follow_redirects=True)
        self.assertIn(b"Goal name is required", res3.data)

if __name__ == "__main__":
    unittest.main()
