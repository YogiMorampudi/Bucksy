import os
import re
import csv
import io
import secrets
import hashlib
from functools import wraps
from pathlib import Path
from datetime import date, datetime, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    Response, jsonify, session, g, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

from achievements_engine import (
    calculate_savings_plan,
    generate_saving_scenarios,
    search_product_prices
)
from db_adapter import db, init_db

app = Flask(__name__)

# Security & Session Configuration
app.secret_key = os.environ.get("BUCKSY_SECRET_KEY") or os.environ.get("SECRET_KEY") or "bucksy-secure-session-secret-key-prod-random-9a7f"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("FLASK_ENV") == "production" or os.environ.get("BUCKSY_FORCE_HTTPS") == "1"
)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)


# ── CSRF & Security Helpers ──────────────────────────────────────────────────
def get_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

def is_valid_email(email):
    return bool(email and EMAIL_REGEX.match(email.strip()))

def validate_password_strength(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isalpha() for c in password):
        return False, "Password must include at least one letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must include at least one number."
    return True, ""

def check_rate_limit(email, ip_address, max_attempts=5, window_minutes=15):
    cutoff = (datetime.now() - timedelta(minutes=window_minutes)).isoformat()
    with db() as conn:
        count = conn.execute("""
            SELECT COUNT(*) FROM login_attempts
            WHERE (email = ? OR ip_address = ?) AND success = 0 AND attempted_at >= ?
        """, (email.lower().strip(), ip_address, cutoff)).fetchone()[0]
        return count >= max_attempts

def record_login_attempt(email, ip_address, success):
    with db() as conn:
        conn.execute("""
            INSERT INTO login_attempts (email, ip_address, attempted_at, success)
            VALUES (?, ?, ?, ?)
        """, (email.lower().strip(), ip_address, datetime.now().isoformat(), 1 if success else 0))

def clear_rate_limit(email):
    with db() as conn:
        conn.execute("DELETE FROM login_attempts WHERE email = ?", (email.lower().strip(),))

@app.before_request
def load_user():
    g.current_user = None
    user_id = session.get("user_id")
    if user_id:
        try:
            with db() as conn:
                user = conn.execute("SELECT id, full_name, email, created_at, updated_at FROM users WHERE id=?", (user_id,)).fetchone()
                if user:
                    g.current_user = dict(user)
                else:
                    # User was genuinely deleted from DB
                    session.clear()
        except Exception:
            # Temporary DB lock or connection error - don't clear session prematurely
            pass

@app.before_request
def verify_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # Exempt during tests if CSRF is turned off
        if app.config.get("WTF_CSRF_ENABLED") is False:
            return
        # Exempt internal JSON APIs if needed
        if request.path.startswith("/api/"):
            return
        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        session_token = session.get("_csrf_token")
        if not token or not session_token or not secrets.compare_digest(str(token), str(session_token)):
            flash("Security check failed (CSRF token missing or invalid). Please try again.", "error")
            return redirect(request.referrer or url_for("dashboard"))

@app.context_processor
def inject_context():
    legacy_count = 0
    if g.get("current_user"):
        with db() as conn:
            legacy_count = conn.execute("SELECT COUNT(*) FROM transactions WHERE user_id IS NULL").fetchone()[0]
    return {
        "csrf_token": get_csrf_token,
        "current_user": g.get("current_user"),
        "legacy_unclaimed_count": legacy_count
    }

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.get("current_user"):
            flash("Please sign in to access this page.", "error")
            next_url = request.full_path if request.method == "GET" and not request.path.startswith("/api/") else url_for("dashboard")
            return redirect(url_for("login", next=next_url))
        return f(*args, **kwargs)
    return decorated_function

@app.template_filter("inr")
def inr(value):
    try:
        return "\u20b9{:,.2f}".format(float(value or 0)).replace(".00", "")
    except (TypeError, ValueError):
        return "\u20b90"

# ── Authentication Routes ─────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if g.get("current_user"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name or not email or not password or not confirm_password:
            flash("All fields are required.", "error")
            return render_template("register.html", full_name=full_name, email=email)

        if not is_valid_email(email):
            flash("Please enter a valid email address.", "error")
            return render_template("register.html", full_name=full_name, email=email)

        valid_pw, pw_err = validate_password_strength(password)
        if not valid_pw:
            flash(pw_err, "error")
            return render_template("register.html", full_name=full_name, email=email)

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("register.html", full_name=full_name, email=email)

        with db() as conn:
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                flash("An account with this email address already exists.", "error")
                return render_template("register.html", full_name=full_name, email=email)

            pw_hash = generate_password_hash(password)
            now = datetime.now().isoformat()
            cur = conn.execute("""
                INSERT INTO users (full_name, email, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (full_name, email, pw_hash, now, now))
            new_user_id = cur.lastrowid

        # Rotate session and log in immediately
        session.clear()
        session["user_id"] = new_user_id
        session["_csrf_token"] = secrets.token_hex(32)
        flash(f"Account created successfully! Welcome to Bucksy, {full_name}.", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if g.get("current_user"):
        return redirect(url_for("dashboard"))

    next_page = request.args.get("next") or ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember_me = bool(request.form.get("remember_me"))
        ip_addr = request.remote_addr or "127.0.0.1"

        if not email or not password:
            flash("Please provide both email and password.", "error")
            return render_template("login.html", email=email, next=next_page)

        if check_rate_limit(email, ip_addr):
            flash("Too many failed login attempts. Please wait 15 minutes before trying again.", "error")
            return render_template("login.html", email=email, next=next_page)

        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            record_login_attempt(email, ip_addr, success=False)
            flash("Invalid email or password.", "error")
            return render_template("login.html", email=email, next=next_page)

        # Successful authentication: record and clear attempts
        record_login_attempt(email, ip_addr, success=True)
        clear_rate_limit(email)

        # Session rotation to prevent session fixation attacks
        session.clear()
        session["user_id"] = user["id"]
        session["_csrf_token"] = secrets.token_hex(32)
        session.permanent = remember_me

        flash(f"Welcome back, {user['full_name']}!", "success")
        if next_page and next_page.startswith("/") and not next_page.startswith("//"):
            return redirect(next_page)
        return redirect(url_for("dashboard"))

    return render_template("login.html", next=next_page)

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if g.get("current_user"):
        return redirect(url_for("dashboard"))

    dev_reset_link = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email or not is_valid_email(email):
            flash("Please enter a valid email address.", "error")
            return render_template("forgot_password.html", email=email)

        with db() as conn:
            user = conn.execute("SELECT id, full_name FROM users WHERE email = ?", (email,)).fetchone()
            if user:
                raw_token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
                expires_at = (datetime.now() + timedelta(minutes=30)).isoformat()
                now = datetime.now().isoformat()

                conn.execute("""
                    INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at)
                    VALUES (?, ?, ?, ?)
                """, (user["id"], token_hash, expires_at, now))

                reset_url = url_for("reset_password", token=raw_token, _external=True)
                print(f"\n[BUCKSY DEV NOTICE] Password reset link for {email}: {reset_url}\n")

                # Local development workflow when email service is not configured
                if app.debug or app.config.get("TESTING"):
                    dev_reset_link = reset_url

        # Generic response that never reveals if an email exists
        flash("If an account exists with that email address, a password reset link has been sent.", "success")
        return render_template("forgot_password.html", email=email, dev_reset_link=dev_reset_link)

    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if g.get("current_user"):
        return redirect(url_for("dashboard"))

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now_iso = datetime.now().isoformat()

    with db() as conn:
        token_record = conn.execute("""
            SELECT prt.*, u.email FROM password_reset_tokens prt
            JOIN users u ON u.id = prt.user_id
            WHERE prt.token_hash = ? AND prt.used_at IS NULL AND prt.expires_at > ?
        """, (token_hash, now_iso)).fetchone()

    if not token_record:
        flash("This password reset link is invalid or has expired.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        valid_pw, pw_err = validate_password_strength(new_password)
        if not valid_pw:
            flash(pw_err, "error")
            return render_template("reset_password.html", token=token)

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html", token=token)

        new_hash = generate_password_hash(new_password)
        now_ts = datetime.now().isoformat()

        with db() as conn:
            # Invalidate the token immediately
            conn.execute("UPDATE password_reset_tokens SET used_at = ? WHERE id = ?", (now_ts, token_record["id"]))
            # Update password
            conn.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?", (new_hash, now_ts, token_record["user_id"]))

        # Invalidate existing sessions
        session.clear()
        flash("Your password has been reset successfully. Please sign in with your new password.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)

@app.route("/claim-legacy-data", methods=["POST"])
@login_required
def claim_legacy_data():
    user_id = g.current_user["id"]
    with db() as conn:
        t_count = conn.execute("UPDATE transactions SET user_id = ? WHERE user_id IS NULL", (user_id,)).rowcount
        p_count = conn.execute("UPDATE people SET user_id = ? WHERE user_id IS NULL", (user_id,)).rowcount
        k_count = conn.execute("UPDATE khata_entries SET user_id = ? WHERE user_id IS NULL", (user_id,)).rowcount
    flash(f"Successfully linked {t_count} transaction(s) and {p_count} Khata contact(s) to your account.", "success")
    return redirect(url_for("dashboard"))

# ── Dashboard (Protected & User-Isolated) ──────────────────────────────────────
@app.route("/")
@login_required
def dashboard():
    user_id = g.current_user["id"]
    month_filter = request.args.get("month", "")
    with db() as conn:
        income = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE kind='income' AND user_id=?", (user_id,)
        ).fetchone()[0]
        expenses = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE kind='expense' AND user_id=?", (user_id,)
        ).fetchone()[0]
        lent = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM khata_entries WHERE direction='given' AND user_id=?", (user_id,)
        ).fetchone()[0]
        received_back = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM khata_entries WHERE direction='received' AND user_id=?", (user_id,)
        ).fetchone()[0]
        borrowed = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM khata_entries WHERE direction='borrowed' AND user_id=?", (user_id,)
        ).fetchone()[0]
        repaid = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM khata_entries WHERE direction='repaid' AND user_id=?", (user_id,)
        ).fetchone()[0]
        people_count = conn.execute(
            "SELECT COUNT(*) FROM people WHERE user_id=?", (user_id,)
        ).fetchone()[0]

        # Monthly income vs expenses for chart (last 6 months for current user)
        monthly_rows = conn.execute("""
            SELECT strftime('%Y-%m', txn_date) AS month,
                   SUM(CASE WHEN kind='income' THEN amount ELSE 0 END) AS income,
                   SUM(CASE WHEN kind='expense' THEN amount ELSE 0 END) AS expenses
            FROM transactions
            WHERE user_id = ?
            GROUP BY month
            ORDER BY month DESC
            LIMIT 6
        """, (user_id,)).fetchall()
        monthly_data = list(reversed(monthly_rows))

        # Category-wise expenses for doughnut chart
        category_rows = conn.execute("""
            SELECT category, SUM(amount) AS total
            FROM transactions WHERE kind='expense' AND user_id = ?
            GROUP BY category ORDER BY total DESC LIMIT 8
        """, (user_id,)).fetchall()

        # Recent transactions (with optional month filter)
        if month_filter:
            recent = conn.execute("""
                SELECT * FROM transactions
                WHERE user_id = ? AND strftime('%Y-%m', txn_date) = ?
                ORDER BY txn_date DESC, id DESC LIMIT 10
            """, (user_id, month_filter)).fetchall()
            m_income = conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE kind='income' AND user_id=? AND strftime('%Y-%m',txn_date)=?",
                (user_id, month_filter)
            ).fetchone()[0]
            m_expenses = conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE kind='expense' AND user_id=? AND strftime('%Y-%m',txn_date)=?",
                (user_id, month_filter)
            ).fetchone()[0]
        else:
            recent = conn.execute(
                "SELECT * FROM transactions WHERE user_id=? ORDER BY txn_date DESC, id DESC LIMIT 10", (user_id,)
            ).fetchall()
            m_income = income
            m_expenses = expenses

        months_avail = conn.execute("""
            SELECT DISTINCT strftime('%Y-%m', txn_date) AS m FROM transactions WHERE user_id=? ORDER BY m DESC
        """, (user_id,)).fetchall()

    balance = income - expenses - lent + received_back + borrowed - repaid
    total_receivable = max(lent - received_back, 0)
    total_payable = max(borrowed - repaid, 0)
    savings_rate = round((m_income - m_expenses) / m_income * 100, 1) if m_income > 0 else 0

    return render_template(
        "dashboard.html",
        income=income, expenses=expenses, balance=balance,
        receivable=total_receivable, payable=total_payable,
        recent=recent, people_count=people_count,
        monthly_data=monthly_data, category_rows=category_rows,
        m_income=m_income, m_expenses=m_expenses,
        savings_rate=savings_rate,
        month_filter=month_filter,
        months_avail=[r["m"] for r in months_avail],
        today=date.today().isoformat()
    )

# ── Transactions (Protected & User-Isolated) ──────────────────────────────────
CATEGORIES = ["Food", "Transport", "Bills", "Shopping", "Salary", "Freelance",
              "Health", "Entertainment", "Education", "Rent", "Other"]
METHODS = ["Cash", "UPI", "Bank transfer", "Card", "Other"]

@app.route("/transactions", methods=["GET", "POST"])
@login_required
def transactions():
    user_id = g.current_user["id"]
    if request.method == "POST":
        kind = request.form.get("kind", "")
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "Other").strip() or "Other"
        method = request.form.get("method", "Cash")
        txn_date = request.form.get("txn_date") or date.today().isoformat()
        notes = request.form.get("notes", "").strip()
        try:
            amount = float(request.form.get("amount", "0"))
            if kind not in ("income", "expense") or not title or amount <= 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid type, title, and amount greater than zero.", "error")
            return redirect(url_for("transactions"))

        with db() as conn:
            conn.execute("""
                INSERT INTO transactions(user_id,kind,title,category,amount,method,txn_date,notes)
                VALUES(?,?,?,?,?,?,?,?)
            """, (user_id, kind, title, category, amount, method, txn_date, notes))
        flash("Transaction saved.", "success")
        return redirect(url_for("transactions"))

    search = request.args.get("q", "").strip()
    kind_filter = request.args.get("kind", "")
    cat_filter = request.args.get("category", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = "SELECT * FROM transactions WHERE user_id = ?"
    params = [user_id]
    if search:
        query += " AND (title LIKE ? OR category LIKE ? OR notes LIKE ?)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if kind_filter in ("income", "expense"):
        query += " AND kind=?"
        params.append(kind_filter)
    if cat_filter:
        query += " AND category=?"
        params.append(cat_filter)
    if date_from:
        query += " AND txn_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND txn_date <= ?"
        params.append(date_to)
    query += " ORDER BY txn_date DESC, id DESC"

    with db() as conn:
        rows = conn.execute(query, params).fetchall()

    return render_template(
        "transactions.html",
        rows=rows, search=search, today=date.today().isoformat(),
        kind_filter=kind_filter, cat_filter=cat_filter,
        date_from=date_from, date_to=date_to,
        categories=CATEGORIES
    )

@app.route("/transactions/<int:txn_id>/edit", methods=["GET", "POST"])
@login_required
def edit_transaction(txn_id):
    user_id = g.current_user["id"]
    with db() as conn:
        txn = conn.execute("SELECT * FROM transactions WHERE id=? AND user_id=?", (txn_id, user_id)).fetchone()
        if not txn:
            flash("Transaction not found.", "error")
            return redirect(url_for("transactions"))

        if request.method == "POST":
            kind = request.form.get("kind", "")
            title = request.form.get("title", "").strip()
            category = request.form.get("category", "Other").strip() or "Other"
            method = request.form.get("method", "Cash")
            txn_date = request.form.get("txn_date") or date.today().isoformat()
            notes = request.form.get("notes", "").strip()
            try:
                amount = float(request.form.get("amount", "0"))
                if kind not in ("income", "expense") or not title or amount <= 0:
                    raise ValueError
            except ValueError:
                flash("Enter a valid type, title, and amount greater than zero.", "error")
                return redirect(url_for("edit_transaction", txn_id=txn_id))

            conn.execute("""
                UPDATE transactions SET kind=?,title=?,category=?,amount=?,method=?,txn_date=?,notes=?
                WHERE id=? AND user_id=?
            """, (kind, title, category, amount, method, txn_date, notes, txn_id, user_id))
            flash("Transaction updated.", "success")
            return redirect(url_for("transactions"))

    return render_template("edit_transaction.html", txn=txn, categories=CATEGORIES,
                           methods=METHODS, today=date.today().isoformat())

@app.route("/transactions/<int:txn_id>/delete", methods=["POST"])
@login_required
def delete_transaction(txn_id):
    user_id = g.current_user["id"]
    with db() as conn:
        exists = conn.execute("SELECT id FROM transactions WHERE id=? AND user_id=?", (txn_id, user_id)).fetchone()
        if not exists:
            flash("Transaction not found.", "error")
        else:
            conn.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (txn_id, user_id))
            flash("Transaction deleted.", "success")
    return redirect(url_for("transactions"))

@app.route("/transactions/export")
@login_required
def export_transactions():
    user_id = g.current_user["id"]
    search = request.args.get("q", "").strip()
    kind_filter = request.args.get("kind", "")
    cat_filter = request.args.get("category", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = "SELECT * FROM transactions WHERE user_id = ?"
    params = [user_id]
    if search:
        query += " AND (title LIKE ? OR category LIKE ? OR notes LIKE ?)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if kind_filter in ("income", "expense"):
        query += " AND kind=?"
        params.append(kind_filter)
    if cat_filter:
        query += " AND category=?"
        params.append(cat_filter)
    if date_from:
        query += " AND txn_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND txn_date <= ?"
        params.append(date_to)
    query += " ORDER BY txn_date DESC, id DESC"

    with db() as conn:
        rows = conn.execute(query, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Type", "Title", "Category", "Amount (INR)", "Method", "Date", "Notes"])
    for r in rows:
        writer.writerow([r["id"], r["kind"], r["title"], r["category"],
                         r["amount"], r["method"], r["txn_date"], r["notes"]])
    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=bucksy_transactions_{date.today().isoformat()}.csv"}
    )

# ── Khata Book (Protected & User-Isolated) ────────────────────────────────────
@app.route("/khata", methods=["GET", "POST"])
@login_required
def khata():
    user_id = g.current_user["id"]
    if request.method == "POST":
        action = request.form.get("action")
        with db() as conn:
            if action == "person":
                name = request.form.get("name", "").strip()
                phone = request.form.get("phone", "").strip()
                notes = request.form.get("notes", "").strip()
                if not name:
                    flash("Person name is required.", "error")
                else:
                    conn.execute("INSERT INTO people(user_id,name,phone,notes,created_at) VALUES(?,?,?,?,?)",
                                 (user_id, name, phone, notes, date.today().isoformat()))
                    flash("Person added to Khata Book.", "success")
            elif action == "entry":
                try:
                    person_id = int(request.form.get("person_id", "0"))
                    direction = request.form.get("direction", "")
                    amount = float(request.form.get("amount", "0"))
                    entry_date = request.form.get("entry_date") or date.today().isoformat()
                    note = request.form.get("note", "").strip()
                    # Verify person belongs to this user
                    exists = conn.execute("SELECT id FROM people WHERE id=? AND user_id=?", (person_id, user_id)).fetchone()
                    if not exists or direction not in ("given", "received", "borrowed", "repaid") or amount <= 0:
                        raise ValueError
                    conn.execute("""
                        INSERT INTO khata_entries(user_id,person_id,direction,amount,entry_date,note)
                        VALUES(?,?,?,?,?,?)
                    """, (user_id, person_id, direction, amount, entry_date, note))
                    flash("Khata entry saved.", "success")
                except ValueError:
                    flash("Choose a valid person and enter an amount greater than zero.", "error")
        return redirect(url_for("khata"))

    with db() as conn:
        people = conn.execute("SELECT * FROM people WHERE user_id=? ORDER BY name COLLATE NOCASE", (user_id,)).fetchall()
        entries = conn.execute("""
            SELECT k.*, p.name FROM khata_entries k
            JOIN people p ON p.id=k.person_id
            WHERE k.user_id=? AND p.user_id=?
            ORDER BY k.entry_date DESC, k.id DESC LIMIT 30
        """, (user_id, user_id)).fetchall()
        summaries = conn.execute("""
            SELECT p.*,
                COALESCE(SUM(CASE WHEN k.direction='given' THEN k.amount
                                  WHEN k.direction='received' THEN -k.amount ELSE 0 END),0) AS receivable,
                COALESCE(SUM(CASE WHEN k.direction='borrowed' THEN k.amount
                                  WHEN k.direction='repaid' THEN -k.amount ELSE 0 END),0) AS payable
            FROM people p
            LEFT JOIN khata_entries k ON k.person_id=p.id AND k.user_id=?
            WHERE p.user_id=?
            GROUP BY p.id ORDER BY p.name COLLATE NOCASE
        """, (user_id, user_id)).fetchall()

    return render_template("khata.html", people=people, entries=entries, summaries=summaries,
                           today=date.today().isoformat())

# ── Person Detail (Protected & User-Isolated) ──────────────────────────────────
@app.route("/people/<int:person_id>")
@login_required
def person_detail(person_id):
    user_id = g.current_user["id"]
    with db() as conn:
        person = conn.execute("SELECT * FROM people WHERE id=? AND user_id=?", (person_id, user_id)).fetchone()
        if not person:
            flash("Person not found.", "error")
            return redirect(url_for("khata"))
        entries = conn.execute(
            "SELECT * FROM khata_entries WHERE person_id=? AND user_id=? ORDER BY entry_date DESC,id DESC",
            (person_id, user_id)
        ).fetchall()

    receivable = sum(e["amount"] if e["direction"] == "given" else -e["amount"] if e["direction"] == "received" else 0 for e in entries)
    payable = sum(e["amount"] if e["direction"] == "borrowed" else -e["amount"] if e["direction"] == "repaid" else 0 for e in entries)
    return render_template("person.html", person=person, entries=entries,
                           receivable=max(receivable, 0), payable=max(payable, 0))

# ── Achievement Calculator (Protected & User-Isolated) ────────────────────────
GOAL_CATEGORIES = [
    "Smartphones",
    "Vehicles & Bikes",
    "Cars & Vehicles",
    "Laptops & Computing",
    "Gaming Consoles",
    "Travel & Vacation",
    "Education",
    "Home & Living",
    "Custom Goal"
]

@app.route("/achievements")
@login_required
def achievements():
    user_id = g.current_user["id"]
    sort = request.args.get("sort", "recent")
    status_filter = request.args.get("status", "all")
    cat_filter = request.args.get("cat", "")

    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM goals WHERE user_id=? ORDER BY created_at DESC, id DESC", (user_id,)
        ).fetchall()

    today_dt = date.today()
    all_goals = []

    for r in rows:
        g_item = dict(r)
        price = float(g_item.get("price") or 0)
        extra = float(g_item.get("extra_costs") or 0)
        saved = float(g_item.get("current_savings") or 0)
        saving_amt = float(g_item.get("saving_amount") or 0)
        freq = g_item.get("saving_frequency") or "daily"

        plan = calculate_savings_plan(
            target_price=price,
            current_savings=saved,
            extra_costs=extra,
            saving_amount=saving_amt,
            saving_frequency=freq,
            start_date=today_dt
        )
        g_item["total_target"] = round(price + extra, 2)
        g_item["remaining_amount"] = plan["remaining_amount"]
        g_item["progress_pct"] = plan["progress_pct"]
        g_item["days_required"] = plan["days_required"]
        g_item["weeks_required"] = plan["weeks_required"]
        g_item["months_required"] = plan["months_required"]
        g_item["estimated_date"] = plan["estimated_date"]
        g_item["is_achieved"] = (g_item.get("status") == "achieved") or plan["is_achieved"]
        g_item["scenarios"] = generate_saving_scenarios(price, saved, extra, today_dt)
        all_goals.append(g_item)

    # Dashboard Metrics across all user goals
    total_goals_count = len(all_goals)
    total_target_value = sum(g_item["total_target"] for g_item in all_goals)
    total_saved_value = sum(g_item["current_savings"] for g_item in all_goals)
    total_remaining_value = sum(g_item["remaining_amount"] for g_item in all_goals)
    completed_goals_count = sum(1 for g_item in all_goals if g_item["is_achieved"])

    upcoming_dates = [g_item["estimated_date"] for g_item in all_goals if not g_item["is_achieved"] and g_item.get("estimated_date")]
    earliest_date = min(upcoming_dates) if upcoming_dates else None

    # Filter by status
    filtered = all_goals
    if status_filter == "active":
        filtered = [g_item for g_item in filtered if not g_item["is_achieved"]]
    elif status_filter == "achieved":
        filtered = [g_item for g_item in filtered if g_item["is_achieved"]]

    # Filter by category
    if cat_filter:
        filtered = [g_item for g_item in filtered if g_item.get("category") == cat_filter]

    # Sort goals
    priority_order = {"High": 1, "Medium": 2, "Low": 3}
    if sort == "date":
        filtered.sort(key=lambda x: (x["is_achieved"], x["estimated_date"] or "9999-99-99"))
    elif sort == "priority":
        filtered.sort(key=lambda x: priority_order.get(x.get("priority", "Medium"), 4))
    elif sort == "remaining":
        filtered.sort(key=lambda x: x["remaining_amount"])
    elif sort == "recent":
        filtered.sort(key=lambda x: (x.get("created_at") or "", x.get("id") or 0), reverse=True)

    return render_template(
        "achievements.html",
        goals=filtered,
        total_goals=total_goals_count,
        total_target=total_target_value,
        total_saved=total_saved_value,
        total_remaining=total_remaining_value,
        completed_count=completed_goals_count,
        earliest_date=earliest_date,
        categories=GOAL_CATEGORIES,
        sort=sort,
        status_filter=status_filter,
        cat_filter=cat_filter,
        today=today_dt.isoformat()
    )

@app.route("/achievements/new", methods=["GET", "POST"])
@login_required
def new_goal():
    user_id = g.current_user["id"]
    if request.method == "POST":
        goal_name = request.form.get("goal_name", "").strip()
        category = request.form.get("category", "Custom Goal").strip() or "Custom Goal"
        product_model = request.form.get("product_model", "").strip()
        product_source = request.form.get("product_source", "").strip() or "User entered price"
        price_checked_at = request.form.get("price_checked_at", "").strip() or datetime.now().isoformat()
        target_date = request.form.get("target_date", "").strip()
        image_url = request.form.get("image_url", "").strip()
        notes = request.form.get("notes", "").strip()
        saving_frequency = request.form.get("saving_frequency", "daily").strip().lower()
        priority = request.form.get("priority", "Medium").strip()

        if saving_frequency not in ("daily", "weekly", "monthly"):
            saving_frequency = "daily"
        if priority not in ("High", "Medium", "Low"):
            priority = "Medium"

        try:
            price = float(request.form.get("price", "0"))
            extra_costs = max(0.0, float(request.form.get("extra_costs", "0") or 0))
            current_savings = max(0.0, float(request.form.get("current_savings", "0") or 0))
            saving_amount = float(request.form.get("saving_amount", "0"))

            if not goal_name:
                raise ValueError("Goal name is required.")
            if price <= 0:
                raise ValueError("Target price must be greater than ₹0.")
            if saving_amount <= 0:
                raise ValueError("Saving contribution must be greater than ₹0.")
        except ValueError as e:
            flash(str(e) if str(e) else "Please enter valid numeric amounts.", "error")
            return redirect(url_for("new_goal"))

        status = "achieved" if current_savings >= (price + extra_costs) else "active"
        now = datetime.now().isoformat()

        with db() as conn:
            conn.execute("""
                INSERT INTO goals (
                    user_id, goal_name, category, product_model, price, extra_costs,
                    current_savings, saving_amount, saving_frequency, priority,
                    product_source, price_checked_at, target_date, image_url,
                    notes, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, goal_name, category, product_model, round(price, 2), round(extra_costs, 2),
                round(current_savings, 2), round(saving_amount, 2), saving_frequency, priority,
                product_source, price_checked_at, target_date, image_url,
                notes, status, now, now
            ))
        flash(f"Goal '{goal_name}' created successfully!", "success")
        return redirect(url_for("achievements"))

    prefill = {
        "name": request.args.get("name", ""),
        "model": request.args.get("model", ""),
        "price": request.args.get("price", ""),
        "category": request.args.get("category", ""),
        "source": request.args.get("source", ""),
        "image": request.args.get("image", "")
    }
    return render_template(
        "new_goal.html",
        categories=GOAL_CATEGORIES,
        prefill=prefill,
        today=date.today().isoformat()
    )

@app.route("/achievements/<int:goal_id>/edit", methods=["GET", "POST"])
@login_required
def edit_goal(goal_id):
    user_id = g.current_user["id"]
    with db() as conn:
        goal = conn.execute("SELECT * FROM goals WHERE id=? AND user_id=?", (goal_id, user_id)).fetchone()
        if not goal:
            flash("Goal not found.", "error")
            return redirect(url_for("achievements"))

        if request.method == "POST":
            goal_name = request.form.get("goal_name", "").strip()
            category = request.form.get("category", "Custom Goal").strip() or "Custom Goal"
            product_model = request.form.get("product_model", "").strip()
            product_source = request.form.get("product_source", "").strip() or goal["product_source"] or "User entered price"
            target_date = request.form.get("target_date", "").strip()
            image_url = request.form.get("image_url", "").strip()
            notes = request.form.get("notes", "").strip()
            saving_frequency = request.form.get("saving_frequency", "daily").strip().lower()
            priority = request.form.get("priority", "Medium").strip()
            status_input = request.form.get("status", goal["status"]).strip()

            if saving_frequency not in ("daily", "weekly", "monthly"):
                saving_frequency = "daily"
            if priority not in ("High", "Medium", "Low"):
                priority = "Medium"
            if status_input not in ("active", "achieved", "cancelled"):
                status_input = "active"

            try:
                price = float(request.form.get("price", "0"))
                extra_costs = max(0.0, float(request.form.get("extra_costs", "0") or 0))
                current_savings = max(0.0, float(request.form.get("current_savings", "0") or 0))
                saving_amount = float(request.form.get("saving_amount", "0"))

                if not goal_name:
                    raise ValueError("Goal name is required.")
                if price <= 0:
                    raise ValueError("Target price must be greater than ₹0.")
                if saving_amount <= 0:
                    raise ValueError("Saving contribution must be greater than ₹0.")
            except ValueError as e:
                flash(str(e) if str(e) else "Please enter valid numeric amounts.", "error")
                return redirect(url_for("edit_goal", goal_id=goal_id))

            if current_savings >= (price + extra_costs):
                status_input = "achieved"

            now = datetime.now().isoformat()
            conn.execute("""
                UPDATE goals SET
                    goal_name=?, category=?, product_model=?, price=?, extra_costs=?,
                    current_savings=?, saving_amount=?, saving_frequency=?, priority=?,
                    product_source=?, target_date=?, image_url=?, notes=?,
                    status=?, updated_at=?
                WHERE id=? AND user_id=?
            """, (
                goal_name, category, product_model, round(price, 2), round(extra_costs, 2),
                round(current_savings, 2), round(saving_amount, 2), saving_frequency, priority,
                product_source, target_date, image_url, notes,
                status_input, now, goal_id, user_id
            ))
            flash(f"Goal '{goal_name}' updated successfully.", "success")
            return redirect(url_for("achievements"))

    return render_template(
        "edit_goal.html",
        goal=goal,
        categories=GOAL_CATEGORIES,
        today=date.today().isoformat()
    )

@app.route("/achievements/<int:goal_id>/delete", methods=["POST"])
@login_required
def delete_goal(goal_id):
    user_id = g.current_user["id"]
    with db() as conn:
        exists = conn.execute("SELECT id FROM goals WHERE id=? AND user_id=?", (goal_id, user_id)).fetchone()
        if not exists:
            flash("Goal not found.", "error")
        else:
            conn.execute("DELETE FROM goals WHERE id=? AND user_id=?", (goal_id, user_id))
            flash("Goal deleted successfully.", "success")
    return redirect(url_for("achievements"))

@app.route("/achievements/<int:goal_id>/status", methods=["POST"])
@login_required
def toggle_goal_status(goal_id):
    user_id = g.current_user["id"]
    with db() as conn:
        goal = conn.execute("SELECT * FROM goals WHERE id=? AND user_id=?", (goal_id, user_id)).fetchone()
        if not goal:
            flash("Goal not found.", "error")
        else:
            new_status = "active" if goal["status"] == "achieved" else "achieved"
            now = datetime.now().isoformat()
            conn.execute("UPDATE goals SET status=?, updated_at=? WHERE id=? AND user_id=?", (new_status, now, goal_id, user_id))
            flash(f"Goal status updated to {new_status.title()}.", "success")
    return redirect(url_for("achievements"))

@app.route("/achievements/<int:goal_id>/add_savings", methods=["POST"])
@login_required
def add_goal_savings(goal_id):
    user_id = g.current_user["id"]
    try:
        deposit = float(request.form.get("deposit_amount", "0"))
        if deposit <= 0:
            raise ValueError
    except ValueError:
        flash("Enter a valid deposit amount greater than zero.", "error")
        return redirect(url_for("achievements"))

    with db() as conn:
        goal = conn.execute("SELECT * FROM goals WHERE id=? AND user_id=?", (goal_id, user_id)).fetchone()
        if not goal:
            flash("Goal not found.", "error")
            return redirect(url_for("achievements"))

        new_savings = round(goal["current_savings"] + deposit, 2)
        total_target = round(goal["price"] + goal["extra_costs"], 2)
        status = "achieved" if new_savings >= total_target else goal["status"]
        now = datetime.now().isoformat()

        conn.execute("UPDATE goals SET current_savings=?, status=?, updated_at=? WHERE id=? AND user_id=?",
                     (new_savings, status, now, goal_id, user_id))

        if status == "achieved" and goal["status"] != "achieved":
            flash(f"🎉 Congratulations! You reached your goal '{goal['goal_name']}'!", "success")
        else:
            flash(f"Saved {inr(deposit)} toward '{goal['goal_name']}'. New total: {inr(new_savings)}.", "success")

    return redirect(url_for("achievements"))

# ── APIs ──────────────────────────────────────────────────────────────────────
@app.route("/api/product-search")
def api_product_search():
    q = request.args.get("q", "").strip()
    results = search_product_prices(q)
    return jsonify(results)

@app.route("/api/calculate-savings", methods=["POST"])
def api_calculate_savings():
    data = request.get_json(silent=True) or request.form
    try:
        target_price = float(data.get("target_price") or 0)
        current_savings = float(data.get("current_savings") or 0)
        extra_costs = float(data.get("extra_costs") or 0)
        saving_amount = float(data.get("saving_amount") or 0)
        saving_frequency = data.get("saving_frequency", "daily")
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid numerical parameters"}), 400

    plan = calculate_savings_plan(
        target_price=target_price,
        current_savings=current_savings,
        extra_costs=extra_costs,
        saving_amount=saving_amount,
        saving_frequency=saving_frequency
    )
    scenarios = generate_saving_scenarios(
        target_price=target_price,
        current_savings=current_savings,
        extra_costs=extra_costs
    )
@app.route("/health")
def health_check():
    import db_adapter
    status = {
        "use_postgres": db_adapter.USE_POSTGRES,
        "database_url_configured": bool(db_adapter.DATABASE_URL),
        "database_url_prefix": db_adapter.DATABASE_URL[:20] + "..." if db_adapter.DATABASE_URL else "",
        "backend": "unknown",
        "error": None
    }
    try:
        with db() as conn:
            if db_adapter.USE_POSTGRES:
                row = conn.execute("SELECT 1").fetchone()
                status["backend"] = "PostgreSQL" if row else "PostgreSQL (no rows)"
            else:
                row = conn.execute("SELECT sqlite_version()").fetchone()
                status["backend"] = f"SQLite ({row[0]})"
    except Exception as e:
        status["error"] = str(e)
    return jsonify(status)

# ── Database Initialisation (runs on import for Vercel, and on __main__ for local)
try:
    init_db()
except Exception as e:
    import logging
    logging.exception("Top-level init_db encountered an issue: %s", e)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

