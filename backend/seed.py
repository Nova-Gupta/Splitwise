#!/usr/bin/env python3
"""Seed demo users and the flat group with correct 2026 membership dates."""
import sqlite3, hashlib, os

DB = os.environ.get("DB_PATH", "./splitwise.db")

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

# Create schema first (idempotent — uses IF NOT EXISTS) so seed works standalone
with open("schema.sql") as f:
    _conn = sqlite3.connect(DB)
    _conn.executescript(f.read())
    _conn.close()

conn = sqlite3.connect(DB)

users = [
    ("aisha","aisha@flat.com","Aisha"),
    ("rohan","rohan@flat.com","Rohan"),
    ("priya","priya@flat.com","Priya"),
    ("meera","meera@flat.com","Meera"),
    ("sam","sam@flat.com","Sam"),
    ("dev","dev@flat.com","Dev"),
]
user_ids = {}
for username, email, display in users:
    ex = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if ex:
        user_ids[username] = ex[0]
    else:
        cur = conn.execute(
            "INSERT INTO users (username,email,password_hash,display_name) VALUES (?,?,?,?)",
            (username, email, hash_pw("pass123"), display)
        )
        user_ids[username] = cur.lastrowid
    print(f"  {username} → id={user_ids[username]}")

ex = conn.execute("SELECT id FROM expense_groups WHERE name='Flat Expenses'").fetchone()
if ex:
    gid = ex[0]
else:
    cur = conn.execute(
        "INSERT INTO expense_groups (name,description,currency,created_by) VALUES (?,?,?,?)",
        ("Flat Expenses","Our shared flat","INR",user_ids["aisha"])
    )
    gid = cur.lastrowid
print(f"Group id={gid}")

# Membership timeline matching actual CSV
# Aisha/Rohan/Priya: Feb 2026 onwards, still active
# Meera: Feb 2026, left 2026-03-29 (farewell dinner is 28-03)
# Dev: joined for Goa trip 08-03, left 14-03 (airport cab row is last Dev expense)
# Sam: joined 08-04-2026 (deposit row is first Sam expense)
memberships = [
    ("aisha","2026-02-01", None),
    ("rohan","2026-02-01", None),
    ("priya","2026-02-01", None),
    ("meera","2026-02-01","2026-03-29"),
    ("dev",  "2026-03-08","2026-03-14"),
    ("sam",  "2026-04-08", None),
]
for username, joined, left in memberships:
    uid = user_ids[username]
    ex = conn.execute(
        "SELECT id FROM group_members WHERE group_id=? AND user_id=? AND joined_at=?",
        (gid, uid, joined)
    ).fetchone()
    if not ex:
        conn.execute(
            "INSERT INTO group_members (group_id,user_id,joined_at,left_at) VALUES (?,?,?,?)",
            (gid, uid, joined, left)
        )
    print(f"  {username}: joined={joined}, left={left or 'active'}")

conn.commit()
conn.close()
print(f"\n✅ Done. Group ID={gid}. Password for all: pass123")
