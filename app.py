"""
Smart Hostel Outpass & Home Leave System - interactive version
Takes all data from the user via input(). Works on OnlineGDB, Programiz,
Replit, Colab (Python 3). Data lives in memory for the session.

Built-in staff logins: warden -> w1 / 1234 ; guard -> g1 / 1234
Students register themselves from the main menu.
"""
import sqlite3
import random
import string
from datetime import datetime, timedelta

FMT = "%Y-%m-%d %H:%M"
conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
conn.executescript("""
CREATE TABLE users(id TEXT PRIMARY KEY, name TEXT, role TEXT, room TEXT, pw TEXT);
CREATE TABLE requests(
    id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, type TEXT, dest TEXT,
    reason TEXT, from_dt TEXT, to_dt TEXT, status TEXT DEFAULT 'Pending',
    code TEXT, remark TEXT, out_at TEXT, in_at TEXT);
""")
conn.executemany("INSERT INTO users VALUES(?,?,?,?,?)", [
    ("w1", "Warden", "warden", None, "1234"),
    ("g1", "Gate Guard", "guard", None, "1234")])


# ---------- input helpers ----------
def ask(prompt, required=True):
    while True:
        v = input(prompt).strip()
        if v or not required:
            return v
        print("  This field is required.")


def ask_int(prompt, lo, hi):
    while True:
        v = input(prompt).strip()
        if v.isdigit() and lo <= int(v) <= hi:
            return int(v)
        print(f"  Enter a number between {lo} and {hi}.")


def ask_dt(prompt, allow_now=False):
    hint = " or press Enter for NOW" if allow_now else ""
    while True:
        v = input(f"{prompt} (YYYY-MM-DD HH:MM{hint}): ").strip()
        if not v and allow_now:
            return datetime.now().replace(second=0, microsecond=0)
        try:
            return datetime.strptime(v, FMT)
        except ValueError:
            print("  Invalid format. Example: 2026-10-20 18:30")


def fmt(d):
    return d.strftime(FMT)


def parse(s):
    return datetime.strptime(s, FMT)


def name_of(uid):
    return conn.execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()[0]


# ---------- display ----------
def show(where="1=1", params=()):
    rows = conn.execute(f"SELECT * FROM requests WHERE {where} ORDER BY id DESC", params).fetchall()
    if not rows:
        print("  (none)")
    for r in rows:
        flag = ""
        if r["status"] == "Out" and datetime.now() > parse(r["to_dt"]):
            flag = "  ** OVERDUE **"
        elif r["in_at"] and parse(r["in_at"]) > parse(r["to_dt"]):
            flag = "  ** LATE RETURN **"
        print(f"\n  #{r['id']} {r['type']} | {name_of(r['student_id'])} | {r['dest']}")
        print(f"     {r['from_dt']} -> {r['to_dt']} | Status: {r['status']}{flag}")
        print(f"     Reason: {r['reason']}")
        if r["remark"]:
            print(f"     Warden remark: {r['remark']}")
        if r["out_at"]:
            print(f"     Out: {r['out_at']}   In: {r['in_at'] or '-'}")


# ---------- registration ----------
def register():
    print("\n--- Student Registration ---")
    while True:
        uid = ask("Choose a User ID: ")
        if conn.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
            print("  ID already taken.")
        else:
            break
    conn.execute("INSERT INTO users VALUES(?,?,?,?,?)",
                 (uid, ask("Full name: "), "student", ask("Room no.: "), ask("Password: ")))
    conn.commit()
    print("Registered! You can now log in.")


def login():
    uid, pw = ask("User ID: "), ask("Password: ")
    u = conn.execute("SELECT * FROM users WHERE id=? AND pw=?", (uid, pw)).fetchone()
    if not u:
        print("Invalid ID or password.")
    return u


# ---------- student ----------
def apply_request(u):
    print("\n--- New Request ---")
    kind = "Outpass" if ask_int("1) Outpass  2) Home Leave : ", 1, 2) == 1 else "Home Leave"
    dest = ask("Destination: ")
    reason = ask("Reason: ")
    start = ask_dt("Leaving at", allow_now=True)
    if kind == "Outpass":
        end = start + timedelta(hours=ask_int("Hours you will be out (1-12): ", 1, 12))
    else:
        while True:
            end = ask_dt("Returning by")
            if end > start:
                break
            print("  Return time must be after leaving time.")
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    cur = conn.execute("""INSERT INTO requests(student_id,type,dest,reason,from_dt,to_dt,code)
                          VALUES(?,?,?,?,?,?,?)""", (u["id"], kind, dest, reason, fmt(start), fmt(end), code))
    conn.commit()
    print(f"Request #{cur.lastrowid} submitted ({fmt(start)} -> {fmt(end)}). Waiting for warden.")


def student_menu(u):
    while True:
        print(f"\n[Student: {u['name']} | Room {u['room']}]")
        c = ask_int("1) Apply  2) My requests  3) My gate codes  0) Logout : ", 0, 3)
        if c == 1:
            apply_request(u)
        elif c == 2:
            show("student_id=?", (u["id"],))
        elif c == 3:
            rows = conn.execute("SELECT * FROM requests WHERE student_id=? AND status IN('Approved','Out')",
                                (u["id"],)).fetchall()
            for r in rows:
                print(f"  #{r['id']} {r['dest']}  ->  CODE: {r['code']}  ({r['status']})")
            if not rows:
                print("  No approved passes yet.")
        else:
            return


# ---------- warden ----------
def warden_menu(u):
    while True:
        print(f"\n[Warden: {u['name']}]")
        c = ask_int("1) Pending  2) All requests  3) Currently out  4) Stats  0) Logout : ", 0, 4)
        if c == 1:
            show("status='Pending'")
            ids = [r["id"] for r in conn.execute("SELECT id FROM requests WHERE status='Pending'")]
            if ids:
                rid = ask("\nRequest ID to act on (Enter to skip): ", required=False)
                if rid.isdigit() and int(rid) in ids:
                    approve = ask_int("1) Approve  2) Reject : ", 1, 2) == 1
                    remark = ask("Remark (optional): ", required=False)
                    conn.execute("UPDATE requests SET status=?, remark=? WHERE id=?",
                                 ("Approved" if approve else "Rejected", remark, int(rid)))
                    conn.commit()
                    print(f"Request #{rid} {'approved' if approve else 'rejected'}.")
        elif c == 2:
            show()
        elif c == 3:
            show("status='Out'")
        elif c == 4:
            for s in ("Pending", "Approved", "Out", "Returned", "Rejected"):
                n = conn.execute("SELECT COUNT(*) FROM requests WHERE status=?", (s,)).fetchone()[0]
                print(f"  {s:<9}: {n}")
        else:
            return


# ---------- guard ----------
def guard_menu(u):
    while True:
        print(f"\n[Guard: {u['name']}]")
        c = ask_int("1) Scan pass code  2) Students outside  0) Logout : ", 0, 2)
        if c == 1:
            code = ask("Enter pass code: ").upper()
            r = conn.execute("SELECT * FROM requests WHERE code=? AND status IN('Approved','Out')",
                             (code,)).fetchone()
            if not r:
                print("Invalid or unapproved code.")
                continue
            t, who = datetime.now(), name_of(r["student_id"])
            if r["status"] == "Approved":
                if not (parse(r["from_dt"]) <= t <= parse(r["to_dt"])):
                    print(f"Outside permitted window ({r['from_dt']} -> {r['to_dt']}). Exit denied.")
                    continue
                conn.execute("UPDATE requests SET status='Out', out_at=? WHERE id=?", (fmt(t), r["id"]))
                print(f"{who} checked OUT -> {r['dest']}")
            else:
                conn.execute("UPDATE requests SET status='Returned', in_at=? WHERE id=?", (fmt(t), r["id"]))
                print(f"{who} checked IN" + (" (LATE RETURN)" if t > parse(r["to_dt"]) else ""))
            conn.commit()
        elif c == 2:
            show("status='Out'")
        else:
            return


# ---------- main ----------
def main():
    menus = {"student": student_menu, "warden": warden_menu, "guard": guard_menu}
    print("=== Smart Hostel Outpass & Home Leave System ===")
    print("Staff logins: warden w1/1234, guard g1/1234. Students: register first.")
    while True:
        c = ask_int("\n1) Register (student)  2) Login  0) Exit : ", 0, 2)
        if c == 1:
            register()
        elif c == 2:
            u = login()
            if u:
                menus[u["role"]](u)
        else:
            print("Goodbye!")
            break


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print("\nExited.")
