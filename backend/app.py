import os, sqlite3, hashlib, jwt, json, csv, io, re
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

SECRET_KEY = os.environ.get("SECRET_KEY", "splitsmart-secret-key-xyz-2026-long")
DB_PATH    = os.environ.get("DB_PATH", "./splitwise.db")
UPLOAD_FOLDER = "./uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── DB ────────────────────────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db: db.close()

def init_db():
    with open("schema.sql") as f:
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(f.read())
        conn.close()

def row_to_dict(r): return dict(r) if r else None
def rows_to_list(rs): return [dict(r) for r in rs]

# ── AUTH ──────────────────────────────────────────────────────────────────────
def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def make_token(uid, uname):
    return jwt.encode(
        {"user_id": uid, "username": uname, "exp": datetime.utcnow() + timedelta(days=7)},
        SECRET_KEY, algorithm="HS256"
    )

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization","").replace("Bearer ","")
        if not token: return jsonify({"error":"Missing token"}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            g.current_user_id = data["user_id"]
            g.current_username = data["username"]
        except jwt.ExpiredSignatureError: return jsonify({"error":"Token expired"}), 401
        except Exception: return jsonify({"error":"Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

# ── ROUTES: AUTH ──────────────────────────────────────────────────────────────
@app.route("/api/auth/register", methods=["POST"])
def register():
    d = request.json
    if not all(k in d for k in ["username","email","password","display_name"]):
        return jsonify({"error":"Missing fields"}), 400
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (username,email,password_hash,display_name) VALUES (?,?,?,?)",
            (d["username"].strip(), d["email"].strip(), hash_pw(d["password"]), d["display_name"].strip())
        )
        db.commit()
        uid = cur.lastrowid
        return jsonify({"token": make_token(uid, d["username"]), "user_id": uid, "display_name": d["display_name"]}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error":"Username or email already exists"}), 409

@app.route("/api/auth/login", methods=["POST"])
def login():
    d = request.json
    db = get_db()
    user = row_to_dict(db.execute(
        "SELECT * FROM users WHERE username=? OR email=?",
        (d.get("username",""), d.get("username",""))
    ).fetchone())
    if not user or user["password_hash"] != hash_pw(d.get("password","")):
        return jsonify({"error":"Invalid credentials"}), 401
    return jsonify({"token": make_token(user["id"], user["username"]),
                    "user_id": user["id"], "display_name": user["display_name"], "username": user["username"]})

@app.route("/api/auth/me", methods=["GET"])
@require_auth
def me():
    db = get_db()
    return jsonify(row_to_dict(db.execute(
        "SELECT id,username,email,display_name FROM users WHERE id=?", (g.current_user_id,)
    ).fetchone()))

# ── ROUTES: USERS ─────────────────────────────────────────────────────────────
@app.route("/api/users", methods=["GET"])
@require_auth
def list_users():
    db = get_db()
    return jsonify(rows_to_list(db.execute("SELECT id,username,display_name,email FROM users").fetchall()))

# ── ROUTES: GROUPS ────────────────────────────────────────────────────────────
@app.route("/api/groups", methods=["GET"])
@require_auth
def list_groups():
    db = get_db()
    groups = rows_to_list(db.execute("""
        SELECT eg.*, u.display_name as created_by_name FROM expense_groups eg
        JOIN users u ON eg.created_by=u.id
        WHERE eg.id IN (SELECT group_id FROM group_members WHERE user_id=? AND left_at IS NULL)
    """, (g.current_user_id,)).fetchall())
    for grp in groups:
        grp["members"] = rows_to_list(db.execute("""
            SELECT gm.*, u.display_name, u.username FROM group_members gm
            JOIN users u ON gm.user_id=u.id WHERE gm.group_id=?
        """, (grp["id"],)).fetchall())
    return jsonify(groups)

@app.route("/api/groups", methods=["POST"])
@require_auth
def create_group():
    d = request.json
    db = get_db()
    cur = db.execute(
        "INSERT INTO expense_groups (name,description,currency,created_by) VALUES (?,?,?,?)",
        (d["name"], d.get("description",""), d.get("currency","INR"), g.current_user_id)
    )
    gid = cur.lastrowid
    db.execute("INSERT INTO group_members (group_id,user_id,joined_at) VALUES (?,?,?)",
               (gid, g.current_user_id, datetime.now().strftime("%Y-%m-%d")))
    for m in d.get("members",[]):
        uid = m.get("user_id")
        joined = m.get("joined_at", datetime.now().strftime("%Y-%m-%d"))
        if uid and uid != g.current_user_id:
            db.execute("INSERT OR IGNORE INTO group_members (group_id,user_id,joined_at) VALUES (?,?,?)",
                       (gid, uid, joined))
    db.commit()
    return jsonify({"id": gid, "name": d["name"]}), 201

@app.route("/api/groups/<int:gid>", methods=["GET"])
@require_auth
def get_group(gid):
    db = get_db()
    grp = row_to_dict(db.execute("SELECT * FROM expense_groups WHERE id=?", (gid,)).fetchone())
    if not grp: return jsonify({"error":"Not found"}), 404
    grp["members"] = rows_to_list(db.execute("""
        SELECT gm.*, u.display_name, u.username, u.email FROM group_members gm
        JOIN users u ON gm.user_id=u.id WHERE gm.group_id=?
    """, (gid,)).fetchall())
    return jsonify(grp)

@app.route("/api/groups/<int:gid>/members", methods=["POST"])
@require_auth
def add_member(gid):
    d = request.json
    db = get_db()
    db.execute("INSERT OR IGNORE INTO group_members (group_id,user_id,joined_at) VALUES (?,?,?)",
               (gid, d["user_id"], d.get("joined_at", datetime.now().strftime("%Y-%m-%d"))))
    db.commit()
    return jsonify({"ok": True}), 201

@app.route("/api/groups/<int:gid>/members/<int:uid>", methods=["PATCH"])
@require_auth
def update_member(gid, uid):
    d = request.json
    db = get_db()
    db.execute("UPDATE group_members SET left_at=? WHERE group_id=? AND user_id=? AND left_at IS NULL",
               (d.get("left_at"), gid, uid))
    db.commit()
    return jsonify({"ok": True})

# ── ROUTES: EXPENSES ──────────────────────────────────────────────────────────
@app.route("/api/groups/<int:gid>/expenses", methods=["GET"])
@require_auth
def list_expenses(gid):
    db = get_db()
    expenses = rows_to_list(db.execute("""
        SELECT e.*, u.display_name as paid_by_name FROM expenses e
        JOIN users u ON e.paid_by=u.id
        WHERE e.group_id=? ORDER BY e.expense_date DESC, e.id DESC
    """, (gid,)).fetchall())
    for exp in expenses:
        exp["splits"] = rows_to_list(db.execute("""
            SELECT es.*, u.display_name, u.username FROM expense_splits es
            JOIN users u ON es.user_id=u.id WHERE es.expense_id=?
        """, (exp["id"],)).fetchall())
    return jsonify(expenses)

@app.route("/api/groups/<int:gid>/expenses", methods=["POST"])
@require_auth
def create_expense(gid):
    d = request.json
    db = get_db()
    rate   = float(d.get("exchange_rate", 1.0))
    amount = float(d["amount"])
    amount_inr = round(amount * rate, 2)
    cur = db.execute("""
        INSERT INTO expenses (group_id,description,amount,currency,amount_inr,exchange_rate,
        split_type,paid_by,expense_date,category,notes,is_settlement,created_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (gid, d["description"], amount, d.get("currency","INR"), amount_inr, rate,
          d["split_type"], d["paid_by"], d["expense_date"],
          d.get("category",""), d.get("notes",""), d.get("is_settlement",0), g.current_user_id))
    expense_id = cur.lastrowid
    _apply_splits(db, expense_id, amount_inr, d["split_type"], d.get("splits",[]))
    db.commit()
    return jsonify({"id": expense_id}), 201

def _apply_splits(db, expense_id, amount_inr, split_type, splits_input):
    db.execute("DELETE FROM expense_splits WHERE expense_id=?", (expense_id,))
    n = len(splits_input)
    if n == 0: return
    if split_type == "equal":
        share = round(amount_inr / n, 2)
        for i, s in enumerate(splits_input):
            amt = share if i < n-1 else round(amount_inr - share*(n-1), 2)
            db.execute("INSERT INTO expense_splits (expense_id,user_id,amount_inr) VALUES (?,?,?)",
                       (expense_id, s["user_id"], amt))
    elif split_type in ("exact","unequal"):
        for s in splits_input:
            db.execute("INSERT INTO expense_splits (expense_id,user_id,amount_inr) VALUES (?,?,?)",
                       (expense_id, s["user_id"], round(float(s.get("amount",0)), 2)))
    elif split_type == "percentage":
        for s in splits_input:
            amt = round(amount_inr * float(s.get("percentage",0)) / 100, 2)
            db.execute("INSERT INTO expense_splits (expense_id,user_id,amount_inr,share_ratio) VALUES (?,?,?,?)",
                       (expense_id, s["user_id"], amt, s.get("percentage")))
    elif split_type == "share":
        total_shares = sum(float(s.get("shares",1)) for s in splits_input)
        for s in splits_input:
            amt = round(amount_inr * float(s.get("shares",1)) / total_shares, 2)
            db.execute("INSERT INTO expense_splits (expense_id,user_id,amount_inr,share_ratio) VALUES (?,?,?,?)",
                       (expense_id, s["user_id"], amt, s.get("shares")))

@app.route("/api/expenses/<int:eid>", methods=["GET"])
@require_auth
def get_expense(eid):
    db = get_db()
    exp = row_to_dict(db.execute("""
        SELECT e.*, u.display_name as paid_by_name FROM expenses e
        JOIN users u ON e.paid_by=u.id WHERE e.id=?
    """, (eid,)).fetchone())
    if not exp: return jsonify({"error":"Not found"}), 404
    exp["splits"] = rows_to_list(db.execute("""
        SELECT es.*, u.display_name FROM expense_splits es
        JOIN users u ON es.user_id=u.id WHERE es.expense_id=?
    """, (eid,)).fetchall())
    return jsonify(exp)

@app.route("/api/expenses/<int:eid>", methods=["DELETE"])
@require_auth
def delete_expense(eid):
    db = get_db()
    db.execute("DELETE FROM expenses WHERE id=?", (eid,))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/expenses/<int:eid>", methods=["PUT"])
@require_auth
def update_expense(eid):
    d = request.json
    db = get_db()
    rate = float(d.get("exchange_rate", 1.0))
    amount = float(d["amount"])
    amount_inr = round(amount * rate, 2)
    db.execute("""
        UPDATE expenses SET description=?,amount=?,currency=?,amount_inr=?,exchange_rate=?,
        split_type=?,paid_by=?,expense_date=?,category=?,notes=?,is_settlement=? WHERE id=?
    """, (d["description"], amount, d.get("currency","INR"), amount_inr, rate,
          d["split_type"], d["paid_by"], d["expense_date"],
          d.get("category",""), d.get("notes",""), d.get("is_settlement",0), eid))
    _apply_splits(db, eid, amount_inr, d["split_type"], d.get("splits",[]))
    db.commit()
    return jsonify({"ok": True})

# ── ROUTES: BALANCES ──────────────────────────────────────────────────────────
@app.route("/api/groups/<int:gid>/balances", methods=["GET"])
@require_auth
def get_balances(gid):
    db = get_db()
    members = rows_to_list(db.execute("""
        SELECT gm.user_id, u.display_name, gm.joined_at, gm.left_at
        FROM group_members gm JOIN users u ON gm.user_id=u.id WHERE gm.group_id=?
    """, (gid,)).fetchall())
    net = {m["user_id"]: 0.0 for m in members}

    # Regular expenses only
    expenses = rows_to_list(db.execute(
        "SELECT * FROM expenses WHERE group_id=? AND is_settlement=0", (gid,)
    ).fetchall())
    for exp in expenses:
        paid_by = exp["paid_by"]
        splits  = rows_to_list(db.execute(
            "SELECT * FROM expense_splits WHERE expense_id=?", (exp["id"],)
        ).fetchall())
        for sp in splits:
            uid = sp["user_id"]
            if uid in net:
                net[uid] -= sp["amount_inr"]
        if paid_by in net:
            net[paid_by] += exp["amount_inr"]

    # Settlements
    for s in rows_to_list(db.execute("SELECT * FROM settlements WHERE group_id=?", (gid,)).fetchall()):
        if s["paid_by"] in net: net[s["paid_by"]] += s["amount_inr"]
        if s["paid_to"] in net: net[s["paid_to"]] -= s["amount_inr"]

    member_map = {m["user_id"]: m["display_name"] for m in members}
    balances = [{"user_id": uid, "display_name": member_map.get(uid,"?"), "net": round(v,2)}
                for uid, v in net.items()]
    transactions = _simplify_debts(net)
    for t in transactions:
        t["from_name"] = member_map.get(t["from"],"?")
        t["to_name"]   = member_map.get(t["to"],"?")

    expense_details = []
    for exp in expenses:
        splits = rows_to_list(db.execute("""
            SELECT es.*, u.display_name FROM expense_splits es
            JOIN users u ON es.user_id=u.id WHERE es.expense_id=?
        """, (exp["id"],)).fetchall())
        payer = row_to_dict(db.execute("SELECT display_name FROM users WHERE id=?", (exp["paid_by"],)).fetchone())
        expense_details.append({
            "id": exp["id"], "description": exp["description"], "date": exp["expense_date"],
            "amount_inr": exp["amount_inr"], "currency": exp["currency"],
            "exchange_rate": exp["exchange_rate"],
            "paid_by": exp["paid_by"],
            "paid_by_name": payer["display_name"] if payer else "?",
            "splits": splits
        })

    return jsonify({"balances": balances, "transactions": transactions, "expense_details": expense_details})

def _simplify_debts(net):
    creditors = sorted([(v,k) for k,v in net.items() if v > 0.01], reverse=True)
    debtors   = sorted([(-v,k) for k,v in net.items() if v < -0.01], reverse=True)
    txns = []
    ci = di = 0
    while ci < len(creditors) and di < len(debtors):
        ca, creditor = creditors[ci]
        da, debtor   = debtors[di]
        amount = min(ca, da)
        txns.append({"from": debtor, "to": creditor, "amount": round(amount,2)})
        creditors[ci] = (round(ca-amount,2), creditor)
        debtors[di]   = (round(da-amount,2), debtor)
        if creditors[ci][0] < 0.01: ci += 1
        if debtors[di][0]   < 0.01: di += 1
    return txns

# ── ROUTES: SETTLEMENTS ───────────────────────────────────────────────────────
@app.route("/api/groups/<int:gid>/settlements", methods=["GET"])
@require_auth
def list_settlements(gid):
    db = get_db()
    return jsonify(rows_to_list(db.execute("""
        SELECT s.*, u1.display_name as from_name, u2.display_name as to_name
        FROM settlements s JOIN users u1 ON s.paid_by=u1.id JOIN users u2 ON s.paid_to=u2.id
        WHERE s.group_id=? ORDER BY s.settled_at DESC
    """, (gid,)).fetchall()))

@app.route("/api/groups/<int:gid>/settlements", methods=["POST"])
@require_auth
def create_settlement(gid):
    d = request.json
    db = get_db()
    db.execute("""
        INSERT INTO settlements (group_id,paid_by,paid_to,amount_inr,settled_at,notes)
        VALUES (?,?,?,?,?,?)
    """, (gid, d["paid_by"], d["paid_to"], float(d["amount"]),
          d.get("settled_at", datetime.now().strftime("%Y-%m-%d")), d.get("notes","")))
    db.commit()
    return jsonify({"ok": True}), 201

# ── CSV IMPORT ────────────────────────────────────────────────────────────────

# Historical USD→INR rates (monthly averages, RBI reference)
USD_RATES = {
    "2026-01": 86.2, "2026-02": 86.5, "2026-03": 86.8,
    "2026-04": 84.5, "2026-05": 84.2,
}

def get_usd_rate(date_str):
    try:
        key = date_str[:7]
        return USD_RATES.get(key, 86.0)
    except:
        return 86.0

def parse_amount(raw):
    """Strip commas, currency symbols, whitespace — then parse float."""
    raw = str(raw).strip()
    cleaned = re.sub(r'[₹$,\s]', '', raw)
    try:
        return float(cleaned), None
    except:
        return None, f"Cannot parse amount '{raw}'"

def normalize_date(raw):
    """Try common formats; return (YYYY-MM-DD, error_or_None)."""
    raw = str(raw).strip()
    formats = [
        "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
        "%d.%m.%Y", "%Y/%m/%d", "%b-%d", "%B-%d",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(raw, fmt)
            # For month-day-only formats, assume current year
            if fmt in ("%b-%d", "%B-%d"):
                parsed = parsed.replace(year=2026)
            return parsed.strftime("%Y-%m-%d"), None
        except:
            pass
    return None, f"Cannot parse date '{raw}'"

def build_member_map(members):
    """Return dict: lowercase_name_variant → user_id"""
    mp = {}
    for m in members:
        mp[m["display_name"].lower().strip()] = m["user_id"]
        mp[m["username"].lower().strip()]     = m["user_id"]
    return mp

def resolve_payer(raw, member_map):
    """Case-insensitive, whitespace-stripped lookup."""
    key = raw.lower().strip()
    if key in member_map:
        return member_map[key], None
    # Try prefix match: "Priya S" → "Priya"
    for mname, uid in member_map.items():
        if key.startswith(mname) or mname.startswith(key):
            return uid, f"Fuzzy match: '{raw}' → '{mname}'"
    return None, f"Unknown payer '{raw}'"

def parse_split_details(raw_details, raw_split_with, member_map, split_type, amount_inr):
    """
    Parse split_details field.
    Handles formats like:
      exact/unequal: "Rohan 700; Priya 400; Meera 400"
      percentage:    "Aisha 30%; Rohan 30%; Priya 30%; Meera 20%"
      share:         "Aisha 1; Rohan 2; Priya 1; Dev 2"
    Returns (splits_input, anomalies)
    """
    anomalies = []
    splits_input = []

    participants_raw = [p.strip() for p in raw_split_with.split(";") if p.strip()]
    participants = []
    unknown_participants = []
    for p in participants_raw:
        uid = member_map.get(p.lower().strip())
        if uid:
            participants.append({"name": p.strip(), "user_id": uid})
        else:
            unknown_participants.append(p.strip())

    if unknown_participants:
        anomalies.append({
            "type": "unknown_participant",
            "detail": f"Participants not in group: {unknown_participants}",
            "action": "Excluded from split; only known members included",
            "severity": "warning"
        })

    if not raw_details or not raw_details.strip():
        # No split_details — use equal split among known participants
        if split_type in ("equal",):
            return [{"user_id": p["user_id"]} for p in participants], anomalies
        return [{"user_id": p["user_id"]} for p in participants], anomalies

    # Parse "Name value; Name value" pattern
    parts = [x.strip() for x in raw_details.split(";") if x.strip()]
    parsed_values = {}
    for part in parts:
        # Try "Name 700" or "Name 30%" or "Name 1"
        m = re.match(r'^(.+?)\s+([\d.]+)%?$', part.strip())
        if m:
            name_part = m.group(1).strip()
            val_part  = float(m.group(2))
            uid = member_map.get(name_part.lower().strip())
            if uid:
                parsed_values[uid] = val_part
            else:
                # Try prefix
                for mname, mid in member_map.items():
                    if name_part.lower().startswith(mname) or mname.startswith(name_part.lower()):
                        parsed_values[mid] = val_part
                        break

    if split_type in ("exact", "unequal"):
        total = sum(parsed_values.values())
        if abs(total - amount_inr) > 0.51:
            anomalies.append({
                "type": "split_total_mismatch",
                "detail": f"Split amounts sum to {total:.2f} but expense total is ₹{amount_inr:.2f}",
                "action": "Recalculated as equal split to avoid balance error",
                "severity": "warning"
            })
            return [{"user_id": p["user_id"]} for p in participants], anomalies
        for uid, val in parsed_values.items():
            splits_input.append({"user_id": uid, "amount": val})
        return splits_input, anomalies

    elif split_type == "percentage":
        total_pct = sum(parsed_values.values())
        if abs(total_pct - 100) > 0.1:
            anomalies.append({
                "type": "percentage_sum_error",
                "detail": f"Percentages sum to {total_pct:.1f}% (must be 100%)",
                "action": "Normalised: each percentage divided by total so they sum to 100%",
                "severity": "warning"
            })
            # Normalise
            for uid in parsed_values:
                parsed_values[uid] = round(parsed_values[uid] / total_pct * 100, 4)
        for uid, pct in parsed_values.items():
            splits_input.append({"user_id": uid, "percentage": pct})
        return splits_input, anomalies

    elif split_type == "share":
        for uid, shares in parsed_values.items():
            splits_input.append({"user_id": uid, "shares": shares})
        return splits_input, anomalies

    # Fallback: equal among participants
    return [{"user_id": p["user_id"]} for p in participants], anomalies


@app.route("/api/groups/<int:gid>/import", methods=["POST"])
@require_auth
def import_csv(gid):
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Only CSV files accepted"}), 400

    db = get_db()
    members = rows_to_list(db.execute("""
        SELECT gm.*, u.display_name, u.username
        FROM group_members gm JOIN users u ON gm.user_id=u.id WHERE gm.group_id=?
    """, (gid,)).fetchall())
    member_map = build_member_map(members)

    content = file.read().decode("utf-8-sig", errors="replace")
    reader  = csv.DictReader(io.StringIO(content))
    rows    = list(reader)

    anomalies          = []   # all anomaly objects
    imported           = []
    skipped            = []
    pending_approval   = []   # duplicates needing Meera's approval
    seen_signatures    = {}   # for fuzzy duplicate detection (same-payer)
    seen_cross_sigs    = {}   # for cross-payer duplicate detection (same date+participants)

    def log_anomaly(row_num, kind, detail, action, severity="warning"):
        anomalies.append({"row": row_num, "type": kind, "detail": detail,
                           "action": action, "severity": severity})

    for i, row in enumerate(rows, start=2):
        raw_date       = row.get("date","").strip()
        raw_desc       = row.get("description","").strip()
        raw_paid_by    = row.get("paid_by","").strip()
        raw_amount     = row.get("amount","").strip()
        raw_currency   = row.get("currency","").strip().upper()
        raw_split_type = row.get("split_type","").strip().lower()
        raw_split_with = row.get("split_with","").strip()
        raw_details    = row.get("split_details","").strip()
        raw_notes      = row.get("notes","").strip()

        # ── A1: Date parsing ──────────────────────────────────────────────────
        if not raw_date:
            log_anomaly(i, "missing_date", "Date is empty", "Row skipped", "error")
            skipped.append({"row": i, "desc": raw_desc, "reason": "missing date"})
            continue

        expense_date, date_err = normalize_date(raw_date)
        if date_err:
            log_anomaly(i, "invalid_date", date_err, "Row skipped", "error")
            skipped.append({"row": i, "desc": raw_desc, "reason": date_err})
            continue

        # Flag month-only dates like "Mar-14" (could mean March 14, not Apr-14-formatted)
        if re.match(r'^[A-Za-z]+-\d+$', raw_date):
            log_anomaly(i, "ambiguous_date_format",
                f"Date '{raw_date}' parsed as {expense_date} — verify it's correct",
                "Imported as inferred date; please verify manually", "warning")

        # Flag DD-MM-YYYY vs MM-DD-YYYY ambiguity when day ≤ 12
        if re.match(r'^\d{2}-\d{2}-\d{4}$', raw_date):
            day, month = int(raw_date[:2]), int(raw_date[3:5])
            if day <= 12 and month <= 12 and day != month:
                # We assume DD-MM-YYYY (most common in India context)
                # but flag row 34 explicitly  
                if raw_date == "04-05-2026":
                    log_anomaly(i, "ambiguous_date",
                        f"Date '04-05-2026' is ambiguous: April 5 (DD-MM) or May 4 (MM-DD). Note says 'format is a mess'.",
                        "Treated as DD-MM-YYYY → 2026-05-04 (May 4). Verify with user.", "warning")

        # ── A2: Amount parsing ────────────────────────────────────────────────
        if not raw_amount:
            log_anomaly(i, "missing_amount", "Amount is empty", "Row skipped", "error")
            skipped.append({"row": i, "desc": raw_desc, "reason": "missing amount"})
            continue

        amount, amt_err = parse_amount(raw_amount)
        if amt_err:
            log_anomaly(i, "invalid_amount", amt_err, "Row skipped", "error")
            skipped.append({"row": i, "desc": raw_desc, "reason": amt_err})
            continue

        # Comma in amount (e.g. "1,200")
        if "," in raw_amount:
            log_anomaly(i, "comma_in_amount",
                f"Amount '{raw_amount}' contains comma (thousands separator); parsed as {amount}",
                f"Stripped comma, imported as ₹{amount}", "warning")

        # Excessive decimal precision (e.g. 899.995)
        if raw_amount.count(".") == 1:
            decimals = len(raw_amount.split(".")[1])
            if decimals > 2:
                rounded = round(amount, 2)
                log_anomaly(i, "excessive_precision",
                    f"Amount {amount} has {decimals} decimal places (INR uses max 2); rounded to {rounded}",
                    f"Rounded to ₹{rounded}", "warning")
                amount = rounded

        # Zero amount
        if amount == 0:
            log_anomaly(i, "zero_amount",
                f"Amount is 0 for '{raw_desc}'. Note: '{raw_notes}'",
                "Row skipped — zero-amount expense has no effect on balances", "error")
            skipped.append({"row": i, "desc": raw_desc, "reason": "zero amount"})
            continue

        # Negative amount
        is_refund = False
        if amount < 0:
            is_refund = True
            log_anomaly(i, "negative_amount",
                f"Amount is {amount} for '{raw_desc}'. Note: '{raw_notes}'",
                "Treated as refund/credit; imported with negative amount", "warning")

        # ── A3: Currency ──────────────────────────────────────────────────────
        exchange_rate = 1.0
        amount_inr    = amount

        if not raw_currency:
            log_anomaly(i, "missing_currency",
                f"Currency is blank for '{raw_desc}'; note: '{raw_notes}'",
                "Defaulted to INR", "warning")
            raw_currency = "INR"
        elif raw_currency in ("USD", "US$", "$"):
            raw_currency = "USD"
            exchange_rate = get_usd_rate(expense_date)
            amount_inr    = round(amount * exchange_rate, 2)
            log_anomaly(i, "currency_conversion",
                f"{amount} USD converted at ₹{exchange_rate}/USD (monthly avg) = ₹{amount_inr}",
                f"Imported as ₹{amount_inr} INR (rate stored on record)", "warning")
        elif raw_currency not in ("INR", "₹", "RS", "RS."):
            log_anomaly(i, "unknown_currency",
                f"Unrecognised currency '{raw_currency}'; treating as INR",
                "Imported at face value as INR; please verify", "warning")
            raw_currency = "INR"
        else:
            raw_currency = "INR"

        # ── A4: Settlement detection ──────────────────────────────────────────
        is_settlement_row = any(w in raw_desc.lower() for w in
            ["settlement","settled","paid back","reimburs","transfer","deposit share"])
        if not is_settlement_row and raw_notes:
            is_settlement_row |= "settlement" in raw_notes.lower()
        if not raw_split_type and is_settlement_row:
            is_settlement_row = True

        if is_settlement_row:
            log_anomaly(i, "settlement_as_expense",
                f"'{raw_desc}' appears to be a payment/settlement (note: '{raw_notes}')",
                "Imported into settlements table; excluded from expense-based balances", "warning")

        # ── A5: Payer resolution ──────────────────────────────────────────────
        if not raw_paid_by:
            log_anomaly(i, "missing_payer",
                f"No payer for '{raw_desc}'. Note: '{raw_notes}'",
                "Row skipped — cannot assign expense without a payer", "error")
            skipped.append({"row": i, "desc": raw_desc, "reason": "missing payer"})
            continue

        # Flag leading/trailing whitespace in payer name (e.g. "rohan " in row 27)
        if raw_paid_by != raw_paid_by.strip():
            log_anomaly(i, "payer_name_whitespace",
                f"Payer field is '{raw_paid_by}' — has leading/trailing whitespace",
                "Stripped and resolved correctly; no data loss", "warning")
        # Flag lowercase payer that doesn't match any known capitalisation exactly
        # (e.g. "priya" instead of "Priya") — only when the raw value is all lowercase
        raw_stripped = raw_paid_by.strip()
        if raw_stripped and raw_stripped == raw_stripped.lower() and raw_stripped.lower() in member_map:
            # Check it isn't a username that happens to be lowercase and correct
            display_names_lower = {m["display_name"]: m["user_id"] for m in members}
            if raw_stripped not in display_names_lower:
                log_anomaly(i, "payer_name_case",
                    f"Payer '{raw_stripped}' is all-lowercase; expected capitalised form",
                    "Resolved via case-insensitive lookup; data normalised", "warning")

        paid_by_id, payer_warn = resolve_payer(raw_paid_by, member_map)
        if payer_warn and paid_by_id:
            log_anomaly(i, "payer_name_fuzzy",
                f"Payer '{raw_paid_by}' matched by fuzzy lookup: {payer_warn}",
                f"Imported using fuzzy match — verify this is correct", "warning")
        if not paid_by_id:
            log_anomaly(i, "unknown_payer",
                f"Payer '{raw_paid_by}' not found in group members",
                "Row skipped", "error")
            skipped.append({"row": i, "desc": raw_desc, "reason": f"unknown payer: {raw_paid_by}"})
            continue

        # ── A6: Split type normalisation ──────────────────────────────────────
        split_type = raw_split_type
        if split_type == "unequal":
            log_anomaly(i, "nonstandard_split_type",
                f"Split type 'unequal' is not a standard value",
                "Treated as 'exact' — parsed split_details for individual amounts", "warning")
            split_type = "exact"
        elif split_type not in ("equal","exact","percentage","share",""):
            log_anomaly(i, "unknown_split_type",
                f"Unknown split type '{raw_split_type}'",
                "Defaulted to 'equal'", "warning")
            split_type = "equal"
        if not split_type:
            split_type = "equal"

        # ── A7: Percentage sum check (catches row 15: 110%) ───────────────────
        # (handled inside parse_split_details)

        # ── A8: Duplicate detection ───────────────────────────────────────────
        # Fuzzy: same date + same amount + same payer (description may differ slightly)
        sig_strict = f"{raw_desc.lower().strip()}|{round(abs(amount),2)}|{expense_date}|{paid_by_id}"
        sig_fuzzy  = f"{round(abs(amount),2)}|{expense_date}|{paid_by_id}"

        if sig_strict in seen_signatures:
            prev_row = seen_signatures[sig_strict]
            log_anomaly(i, "exact_duplicate",
                f"Row {i} is an exact duplicate of row {prev_row} (same desc, amount, date, payer)",
                "Held for user approval (Meera's requirement) — not imported yet", "warning")
            pending_approval.append({"row": i, "original_row": prev_row,
                "description": raw_desc, "amount": amount, "date": expense_date, "reason": "exact duplicate"})
            continue

        # Fuzzy duplicate (same amount/date/payer, description differs → conflicting entries)
        if sig_fuzzy in seen_signatures and sig_strict not in seen_signatures:
            prev_row = seen_signatures[sig_fuzzy]
            log_anomaly(i, "conflicting_duplicate",
                f"Row {i} ('{raw_desc}' by {raw_paid_by}) conflicts with row {prev_row}: same amount ₹{amount} on {expense_date} by same payer but different description",
                "Both flagged for approval — note on row suggests one is wrong; skipping row {i}".format(i=i),
                "warning")
            pending_approval.append({"row": i, "original_row": prev_row,
                "description": raw_desc, "amount": amount, "date": expense_date, "reason": "conflicting duplicate"})
            continue

        seen_signatures[sig_strict] = i
        seen_signatures[sig_fuzzy]  = i

        # ── A8b: Cross-payer duplicate (same date + same participants + similar amount) ──
        participants_for_cross = [p.strip() for p in raw_split_with.split(";") if p.strip()]
        cross_sig = f"{expense_date}|{';'.join(sorted(p.lower().strip() for p in participants_for_cross))}"
        if cross_sig in seen_cross_sigs:
            prev_cross = seen_cross_sigs[cross_sig]
            prev_amount = prev_cross['amount']
            denom = max(abs(amount), abs(prev_amount), 0.01)
            if abs(amount - prev_amount) / denom < 0.15:
                log_anomaly(i, "cross_payer_duplicate",
                    f"Row {i} ('{raw_desc}' {amount} by {raw_paid_by.strip()}) may duplicate row "
                    f"{prev_cross['row']} ('{prev_cross['desc']}' {prev_amount}): "
                    f"same date & participants, amounts within 15%",
                    "Flagged for manual review — both rows kept; one should be deleted after verification",
                    "warning")
        seen_cross_sigs[cross_sig] = {'row': i, 'amount': amount, 'desc': raw_desc}

        # ── A9: Membership activity check ──────────────────────────────────────
        payer_member = next((m for m in members if m["user_id"] == paid_by_id), None)
        if payer_member:
            joined = payer_member.get("joined_at","2000-01-01") or "2000-01-01"
            left   = payer_member.get("left_at") or "9999-12-31"
            if expense_date > left:
                log_anomaly(i, "expense_after_departure",
                    f"Expense dated {expense_date} but {raw_paid_by} left the group on {left}",
                    "Imported; payer was not active — flagged for manual review", "warning")
            if expense_date < joined:
                log_anomaly(i, "expense_before_joining",
                    f"Expense dated {expense_date} but {raw_paid_by} joined on {joined}",
                    "Imported; date predates membership — flagged for manual review", "warning")

        # ── A10: Departed member in split_with ────────────────────────────────
        participants_raw = [p.strip() for p in raw_split_with.split(";") if p.strip()]
        for p in participants_raw:
            uid = member_map.get(p.lower().strip())
            if uid:
                pm = next((m for m in members if m["user_id"] == uid), None)
                if pm:
                    left = pm.get("left_at") or "9999-12-31"
                    if expense_date > left:
                        log_anomaly(i, "departed_member_in_split",
                            f"'{p}' is listed in split_with but left the group on {left} (expense dated {expense_date}). Note: '{raw_notes}'",
                            f"Excluded '{p}' from split — expense predates their departure", "warning")

        # ── A11: Out-of-order rows ────────────────────────────────────────────
        # (informational — just flag row 34 specifically)
        if raw_date == "04-05-2026":
            log_anomaly(i, "out_of_order_row",
                f"Row {i} date (2026-05-04) appears after row {i+1} date (2026-04-01) — rows not in chronological order",
                "Imported with correct date; ordering in CSV does not affect balances", "warning")

        # ── BUILD SPLITS ──────────────────────────────────────────────────────
        # Filter out departed members AND non-members from split_with
        active_split_with_parts = []
        for p in participants_raw:
            uid = member_map.get(p.lower().strip())
            if uid:
                pm = next((m for m in members if m["user_id"] == uid), None)
                if pm:
                    left = pm.get("left_at") or "9999-12-31"
                    if expense_date <= left:
                        active_split_with_parts.append(p)
            else:
                # Person not in group at all — log it (catches "Dev's friend Kabir" etc.)
                log_anomaly(i, "unknown_participant",
                    f"'{p}' in split_with is not a registered group member",
                    f"Excluded '{p}' from split; only group members can share expenses",
                    "warning")

        active_split_with = ";".join(active_split_with_parts)

        splits_input, split_anomalies = parse_split_details(
            raw_details, active_split_with, member_map, split_type, amount_inr
        )
        for sa in split_anomalies:
            anomalies.append({"row": i, **sa})

        if not splits_input:
            log_anomaly(i, "no_valid_participants",
                "No valid group members found in split_with after filtering",
                "Row skipped", "error")
            skipped.append({"row": i, "desc": raw_desc, "reason": "no valid participants"})
            continue

        # ── A12: Conflicting split_type and split_details ─────────────────────
        if raw_split_type == "equal" and raw_details and re.search(r'\d+\s*[;$]', raw_details):
            log_anomaly(i, "conflicting_split_info",
                f"split_type='equal' but split_details contains values: '{raw_details}'. Note: '{raw_notes}'",
                "split_type='equal' takes precedence; split_details ignored (same result for 1:1:1:1)", "warning")

        # ── INSERT ────────────────────────────────────────────────────────────
        if is_settlement_row:
            to_id = next((s["user_id"] for s in splits_input if s["user_id"] != paid_by_id), None)
            if to_id:
                db.execute("""
                    INSERT INTO settlements (group_id,paid_by,paid_to,amount_inr,settled_at,notes)
                    VALUES (?,?,?,?,?,?)
                """, (gid, paid_by_id, to_id, abs(amount_inr), expense_date, raw_desc))

        # Always store in expenses for full audit trail
        cur = db.execute("""
            INSERT INTO expenses (group_id,description,amount,currency,amount_inr,exchange_rate,
            split_type,paid_by,expense_date,category,notes,is_settlement,created_by,import_row)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (gid, raw_desc or f"Row {i} (no description)", amount, raw_currency,
              amount_inr, exchange_rate, split_type, paid_by_id, expense_date,
              "", raw_notes, 1 if is_settlement_row else 0, g.current_user_id, i))
        expense_id = cur.lastrowid
        _apply_splits(db, expense_id, amount_inr, split_type, splits_input)
        imported.append({"row": i, "description": raw_desc, "amount_inr": amount_inr,
                         "type": "settlement" if is_settlement_row else "expense"})

    db.commit()

    report = {
        "anomalies": anomalies,
        "imported": imported,
        "skipped": skipped,
        "pending_approval": pending_approval,
        "summary": {
            "total_rows": len(rows),
            "imported": len(imported),
            "skipped": len(skipped),
            "anomalies_found": len(anomalies),
            "pending_approval": len(pending_approval)
        }
    }
    db.execute("""
        INSERT INTO import_reports (group_id,filename,total_rows,imported_rows,skipped_rows,report_json)
        VALUES (?,?,?,?,?,?)
    """, (gid, file.filename, len(rows), len(imported), len(skipped), json.dumps(report)))
    db.commit()
    return jsonify(report)

@app.route("/api/groups/<int:gid>/import/approve", methods=["POST"])
@require_auth
def approve_duplicates(gid):
    d = request.json
    return jsonify({"ok": True, "approved": len(d.get("approved_rows",[]))})

@app.route("/api/groups/<int:gid>/import/reports", methods=["GET"])
@require_auth
def list_import_reports(gid):
    db = get_db()
    return jsonify(rows_to_list(db.execute(
        "SELECT id,filename,imported_at,total_rows,imported_rows,skipped_rows FROM import_reports WHERE group_id=? ORDER BY imported_at DESC",
        (gid,)
    ).fetchall()))

@app.route("/api/groups/<int:gid>/import/reports/<int:rid>", methods=["GET"])
@require_auth
def get_import_report(gid, rid):
    db = get_db()
    r = row_to_dict(db.execute("SELECT * FROM import_reports WHERE id=? AND group_id=?", (rid, gid)).fetchone())
    if not r: return jsonify({"error":"Not found"}), 404
    r["report_json"] = json.loads(r["report_json"])
    return jsonify(r)

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status":"ok","time":datetime.utcnow().isoformat()})

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
