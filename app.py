
import os
import sqlite3
import secrets
import string
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-before-deployment")

DB_PATH = os.environ.get("DB_PATH", "hostel.db")
FMT = "%Y-%m-%dT%H:%M"


def connect():
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            room TEXT,
            pw TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            type TEXT NOT NULL,
            dest TEXT NOT NULL,
            reason TEXT NOT NULL,
            from_dt TEXT NOT NULL,
            to_dt TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            code TEXT UNIQUE,
            remark TEXT DEFAULT '',
            out_at TEXT,
            in_at TEXT
        );
        """)

        for uid, name, role in [
            ("w1", "Warden", "warden"),
            ("g1", "Gate Guard", "guard")
        ]:
            exists = db.execute(
                "SELECT id FROM users WHERE id=?", (uid,)
            ).fetchone()

            if not exists:
                db.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                    (uid, name, role, "-", generate_password_hash("1234"))
                )


init_db()


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    with connect() as db:
        return db.execute(
            "SELECT id, name, role, room FROM users WHERE id=?", (uid,)
        ).fetchone()


def login_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("index"))
            if roles and user["role"] not in roles:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def new_code(db):
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if not db.execute(
            "SELECT id FROM requests WHERE code=?", (code,)
        ).fetchone():
            return code


@app.route("/", methods=["GET", "POST"])
def index():
    if current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        action = request.form.get("action")

        with connect() as db:
            if action == "register":
                uid = request.form.get("user_id", "").strip()
                name = request.form.get("name", "").strip()
                room = request.form.get("room", "").strip()
                password = request.form.get("password", "")

                if not all([uid, name, room, password]):
                    flash("Please complete all registration fields.")
                elif len(password) < 8:
                    flash("Use a password with at least 8 characters.")
                elif db.execute(
                    "SELECT id FROM users WHERE id=?", (uid,)
                ).fetchone():
                    flash("That student ID is already registered.")
                else:
                    db.execute(
                        "INSERT INTO users VALUES (?, ?, 'student', ?, ?)",
                        (uid, name, room, generate_password_hash(password))
                    )
                    flash("Registration successful. Please log in.")

            elif action == "login":
                uid = request.form.get("user_id", "").strip()
                password = request.form.get("password", "")
                user = db.execute(
                    "SELECT * FROM users WHERE id=?", (uid,)
                ).fetchone()

                if user and check_password_hash(user["pw"], password):
                    session.clear()
                    session["uid"] = user["id"]
                    return redirect(url_for("dashboard"))

                flash("Invalid user ID or password.")

    return render_template("index.html")


@app.route("/dashboard")
@login_required()
def dashboard():
    user = current_user()

    with connect() as db:
        if user["role"] == "student":
            rows = db.execute(
                "SELECT * FROM requests WHERE student_id=? ORDER BY id DESC",
                (user["id"],)
            ).fetchall()
        else:
            rows = db.execute("""
                SELECT requests.*, users.name, users.room
                FROM requests JOIN users ON users.id=requests.student_id
                ORDER BY requests.id DESC
            """).fetchall()

    now = datetime.now()
    requests_data = []

    for row in rows:
        item = dict(row)
        item["overdue"] = (
            item["status"] == "Out"
            and now > datetime.strptime(item["to_dt"], FMT)
        )
        requests_data.append(item)

    return render_template(
        "dashboard.html", user=user, requests=requests_data, now=now
    )


@app.route("/apply", methods=["POST"])
@login_required("student")
def apply():
    kind = request.form.get("type", "")
    dest = request.form.get("dest", "").strip()
    reason = request.form.get("reason", "").strip()
    start = request.form.get("from_dt", "")
    end = request.form.get("to_dt", "")

    try:
        start_dt = datetime.strptime(start, FMT)
        end_dt = datetime.strptime(end, FMT)
    except ValueError:
        flash("Please enter valid leaving and return times.")
        return redirect(url_for("dashboard"))

    if kind not in ("Outpass", "Home Leave") or not dest or not reason:
        flash("Please complete all request fields.")
    elif end_dt <= start_dt:
        flash("Return time must be after leaving time.")
    elif kind == "Outpass" and (end_dt - start_dt).total_seconds() > 12 * 3600:
        flash("An outpass cannot exceed 12 hours.")
    elif start_dt < datetime.now().replace(second=0, microsecond=0):
        flash("Leaving time cannot be in the past.")
    else:
        with connect() as db:
            code = new_code(db)
            db.execute("""
                INSERT INTO requests
                (student_id, type, dest, reason, from_dt, to_dt, code)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session["uid"], kind, dest, reason,
                start, end, code
            ))
        flash("Request submitted for warden approval.")

    return redirect(url_for("dashboard"))


@app.route("/decision/<int:rid>", methods=["POST"])
@login_required("warden")
def decision(rid):
    action = request.form.get("action")
    remark = request.form.get("remark", "").strip()

    if action not in ("Approved", "Rejected"):
        abort(400)

    with connect() as db:
        cur = db.execute("""
            UPDATE requests SET status=?, remark=?
            WHERE id=? AND status='Pending'
        """, (action, remark, rid))

        if cur.rowcount:
            flash(f"Request {action.lower()} successfully.")
        else:
            flash("Request not found or already processed.")

    return redirect(url_for("dashboard"))


@app.route("/gate", methods=["POST"])
@login_required("guard")
def gate():
    code = request.form.get("code", "").strip().upper()
    now = datetime.now()

    with connect() as db:
        row = db.execute(
            "SELECT * FROM requests WHERE code=?", (code,)
        ).fetchone()

        if not row:
            flash("Invalid gate code.")
        elif row["status"] == "Approved":
            start = datetime.strptime(row["from_dt"], FMT)
            end = datetime.strptime(row["to_dt"], FMT)

            if not start <= now <= end:
                flash("Exit denied: outside the approved time window.")
            else:
                db.execute("""
                    UPDATE requests SET status='Out', out_at=?
                    WHERE id=? AND status='Approved'
                """, (now.strftime(FMT), row["id"]))
                flash("Student checked out.")
        elif row["status"] == "Out":
            db.execute("""
                UPDATE requests SET status='Returned', in_at=?
                WHERE id=? AND status='Out'
            """, (now.strftime(FMT), row["id"]))
            if now > datetime.strptime(row["to_dt"], FMT):
                flash("Student checked in. LATE RETURN.")
            else:
                flash("Student checked in successfully.")
        else:
            flash("This pass is not approved or is already closed.")

    return redirect(url_for("dashboard"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
