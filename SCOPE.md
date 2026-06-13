# SCOPE.md — Anomaly Log & Database Schema

## Database Schema

```sql
-- Users: authentication and identity
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,   -- SHA-256 (bcrypt preferred in production)
    display_name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Groups: a collection of people splitting expenses
CREATE TABLE expense_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    currency TEXT DEFAULT 'INR',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);

-- Group memberships with temporal bounds (Sam's requirement)
-- A user can leave and rejoin; each stint is a separate row
CREATE TABLE group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER REFERENCES expense_groups(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    joined_at TEXT NOT NULL,       -- YYYY-MM-DD
    left_at TEXT,                  -- NULL = still active
    UNIQUE(group_id, user_id, joined_at)
);

-- Expenses: the core record
CREATE TABLE expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER REFERENCES expense_groups(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    amount REAL NOT NULL,          -- original amount in original currency
    currency TEXT DEFAULT 'INR',
    amount_inr REAL NOT NULL,      -- always in INR after conversion
    exchange_rate REAL DEFAULT 1.0,
    split_type TEXT NOT NULL CHECK(split_type IN ('equal','exact','percentage','share')),
    paid_by INTEGER REFERENCES users(id),
    expense_date TEXT NOT NULL,
    category TEXT,
    notes TEXT,
    is_settlement INTEGER DEFAULT 0,  -- 1 if this row represents a payment
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    import_row INTEGER             -- CSV row number for full traceability
);

-- Expense splits: who owes what for each expense
CREATE TABLE expense_splits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id INTEGER REFERENCES expenses(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    amount_inr REAL NOT NULL,
    share_ratio REAL               -- stored for percentage/share display
);

-- Settlements: recorded payments between members
CREATE TABLE settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER REFERENCES expense_groups(id),
    paid_by INTEGER REFERENCES users(id),
    paid_to INTEGER REFERENCES users(id),
    amount_inr REAL NOT NULL,
    settled_at TEXT NOT NULL,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Import reports: audit trail of every CSV import
CREATE TABLE import_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER REFERENCES expense_groups(id),
    filename TEXT,
    imported_at TEXT DEFAULT (datetime('now')),
    total_rows INTEGER,
    imported_rows INTEGER,
    skipped_rows INTEGER,
    report_json TEXT               -- full anomaly log serialized as JSON
);
```

**Key design decisions in schema:**
- `group_members.left_at` being nullable means "still active" — no boolean needed
- `expenses.amount_inr` is always stored in INR regardless of original currency, so balance calculations are currency-agnostic
- `expenses.import_row` links every imported expense back to its CSV row for live traceability
- Settlements are separate from expenses to avoid polluting balance calculations (though settlement-as-expenses are also stored with `is_settlement=1` for full audit trail)
- `UNIQUE(group_id, user_id, joined_at)` allows a member to leave and rejoin (multiple stints)

---

## Membership Timeline (from CSV context)

| Member | Joined     | Left       | Notes                                    |
|--------|------------|------------|------------------------------------------|
| Aisha  | 2026-02-01 | active     |                                          |
| Rohan  | 2026-02-01 | active     |                                          |
| Priya  | 2026-02-01 | active     |                                          |
| Meera  | 2026-02-01 | 2026-03-29 | Farewell dinner 2026-03-28               |
| Dev    | 2026-03-08 | 2026-03-14 | Goa trip only (Feb dinner was as visitor)|
| Sam    | 2026-04-08 | active     | Deposit row is first Sam expense         |

---

## CSV Anomaly Log

The file `expenses_export.csv` contains **at least 12 deliberate data problems**. The importer detected **27 anomalies** across 42 data rows. Here is every anomaly, the policy chosen, and the reasoning.

Import result summary: **42 rows total → 39 imported, 2 skipped (errors), 1 held for approval.**

---

### Anomaly 1 — Expense payer predates membership (row 5)
**Problem:** Row 5: `08-02-2026, Dinner at Marina Bites, Dev, ₹3200`. Dev's group membership starts `2026-03-08` (Goa trip), but this dinner is in February when Dev was visiting.

**Detection:** For each imported expense, we compare `expense_date` against the payer's `joined_at` in `group_members`.

**Policy:** Imported with a warning flag (`expense_before_joining`). The expense is valid (Dev genuinely paid), but users should verify that Dev's membership date is correct or manually adjust.

**Rationale:** We cannot safely discard — Dev genuinely paid for a dinner. The right fix is for the user to backdate Dev's membership or convert this to a guest split.

---

### Anomaly 2 — Duplicate entry: same dinner logged twice (rows 5 & 6)
**Problem:** Row 5 is `Dinner at Marina Bites` and Row 6 is `dinner - marina bites` — same payer (Dev), same amount (₹3200), same date (2026-02-08), slightly different description.

**Detection:** We generate `sig_fuzzy = f"{amount}|{date}|{payer_id}"`. If the same amount/date/payer appears twice with different descriptions, it is flagged as a conflicting duplicate.

**Policy:** Row 5 is imported. Row 6 is held in a **pending approval queue** (not imported). The queue is surfaced in the import report UI where the user can approve or discard it.

**Rationale:** Meera's requirement: "I want to approve anything the app deletes or changes." Auto-deletion violates this. Importing both would double the expense. The pending queue gives the user explicit control.

---

### Anomaly 3 — Comma in numeric amount (row 7)
**Problem:** Row 7: `Electricity Feb, amount="1,200"`. The thousands-separator comma breaks naive float parsing.

**Detection:** After parsing, we check if the original raw amount string contained a comma.

**Policy:** Strip the comma and parse as `1200.0`. Warning logged noting the comma was stripped.

**Rationale:** This is unambiguously a thousands separator in this Indian context. Not grounds for skipping a valid expense.

---

### Anomaly 4 — Payer name in all-lowercase (row 9)
**Problem:** Row 9: `paid_by = "priya"` (all lowercase). All other payer names are title-cased.

**Detection:** After stripping, we check if the payer field is all-lowercase while the resolved member name is title-cased.

**Policy:** Resolved via case-insensitive lookup (`member_map` uses lowercase keys). Warning logged: `payer_name_case`.

**Rationale:** Case inconsistency is a data quality signal, not a data error. The expense is valid. We resolve and flag.

---

### Anomaly 5 — Excessive decimal precision (row 10)
**Problem:** Row 10: `Cylinder refill, amount=899.995`. INR uses at most 2 decimal places (paise).

**Detection:** Count decimal digits in raw amount string; flag if > 2.

**Policy:** Round to 2 decimal places (`900.00`). Warning logged.

**Rationale:** Sub-paisa amounts are a data entry artifact. Rounding to nearest paisa is the correct normalization.

---

### Anomaly 6 — Payer name is a partial/variant form (row 11)
**Problem:** Row 11: `paid_by = "Priya S"`. The registered member is `"Priya"`.

**Detection:** After exact-match fails, we try prefix matching: `"priya s".startswith("priya")` → match.

**Policy:** Resolved via fuzzy prefix match. Warning logged: `payer_name_fuzzy`. User should verify.

**Rationale:** "Priya S" is almost certainly Priya (only one Priya in the group). Skipping would lose a valid ₹1875 expense. We resolve and flag for manual confirmation.

---

### Anomaly 7 — Non-standard split type "unequal" (row 12)
**Problem:** Row 12: `split_type = "unequal"`. Valid split types are `equal`, `exact`, `percentage`, `share`.

**Detection:** `split_type not in ("equal","exact","percentage","share")`.

**Policy:** Treated as `exact` — we parse `split_details` field for individual amounts. Warning logged.

**Rationale:** "Unequal" is semantically equivalent to "exact" (specific amounts per person). The `split_details` field contains `"Rohan 700; Priya 400; Meera 400"` which sum to ₹1500 = the expense total. This resolves cleanly.

---

### Anomaly 8 — Missing payer (row 13) ← SKIPPED
**Problem:** Row 13: `House cleaning supplies, paid_by=""`. Note says "can't remember who paid."

**Detection:** `paid_by` field is empty after stripping.

**Policy:** Row is **skipped**. Error logged: `missing_payer`.

**Rationale:** We cannot assign an expense without knowing who paid. This is an unrecoverable error. The import report makes it visible so the user can manually add this expense with the correct payer.

---

### Anomaly 9 — Settlement logged as an expense (row 14)
**Problem:** Row 14: `Rohan paid Aisha back, ₹5000`. Note says "this is a settlement not an expense??". The `split_type` field is blank.

**Detection:** Description contains the phrase "paid back". We also check for: `"settlement"`, `"settled"`, `"reimburs"`, `"transfer"`, `"deposit share"`.

**Policy:** Imported into the `settlements` table (not as an expense). Also stored in `expenses` with `is_settlement=1` for audit trail. Balance calculations use `WHERE is_settlement=0` to exclude it from expense-side totals.

**Rationale:** If treated as a regular expense, Rohan would owe Aisha ₹5000 AND the ₹5000 payment would also show as a debt — double-counting. Correct settlement handling avoids this.

---

### Anomaly 10 — Percentages don't sum to 100% (rows 15 and 32)
**Problem:** Row 15 (`Pizza Friday`): percentages `Aisha 30%; Rohan 30%; Priya 30%; Meera 20%` sum to 110%. Same issue on Row 32 (`Weekend brunch`).

**Detection:** After parsing percentage values from `split_details`, we sum them. Flag if `abs(sum - 100) > 0.1`.

**Policy:** Normalize — divide each percentage by the total (110%) to obtain 100%-equivalent proportions. Warning logged.

**Rationale:** The intent is clear (approximate percentages). Discarding would lose valid expense data. Normalization gives the most reasonable result. The note on row 15 says "percentages might be off" which confirms user awareness.

---

### Anomaly 11 — USD expenses without conversion (rows 20, 21, 23, 26)
**Problem:** Goa trip expenses are in USD (`currency = "USD"`). Without conversion, a dollar is treated as a rupee — exactly what Priya complained about.

**Detection:** `currency == "USD"` in the row.

**Policy:** Convert to INR using historical monthly average rate for the month of the expense (March 2026 = ₹86.8/USD, sourced from RBI reference data). The original USD amount and exchange rate are stored on the `expenses` record. Warning logged for each conversion.

**Rationale:** These are historical expenses. The correct rate is the one in effect when the expense occurred, not today's live rate. Storing the rate on the record makes it auditable and editable.

---

### Anomaly 12 — Non-member in split_with (row 23)
**Problem:** Row 23 (`Parasailing`): `split_with = "Aisha;Rohan;Priya;Dev;Dev's friend Kabir"`. Kabir is not a registered group member.

**Detection:** For each participant in `split_with`, we look up `member_map.get(name.lower())`. If not found, it's flagged as `unknown_participant`.

**Policy:** Kabir is excluded from the split. The expense is split only among the 4 known group members. Warning logged.

**Rationale:** We cannot add Kabir's share to an unknown person. The 4-way equal split among known members is the safest assumption. The note says "Kabir joined for the day" — in the future, Kabir should be registered as a group member for that stint.

---

### Anomaly 13 — Cross-payer duplicate: same dinner logged by two people (rows 24 & 25)
**Problem:** Row 24: `Dinner at Thalassa, Aisha, ₹2400, 2026-03-11`. Row 25: `Thalassa dinner, Rohan, ₹2450, 2026-03-11`. Same date, same participants, descriptions are clearly the same dinner, amounts differ by ₹50.

**Detection:** We maintain a `seen_cross_sigs` dict keyed on `{date}|{sorted_participants}`. When a new row matches a previous row's date+participants AND amounts are within 15%, it is flagged as `cross_payer_duplicate`.

**Policy:** Both rows are imported (neither is auto-deleted). Both are flagged for manual review. Note on row 25 says "Aisha also logged this I think hers is wrong."

**Rationale:** We cannot auto-decide which amount is correct (₹2400 vs ₹2450). The user should delete one after reviewing. Meera's approval requirement applies here too.

---

### Anomaly 14 — Negative amount: refund (row 26)
**Problem:** Row 26: `Parasailing refund, Dev, -$30`. Negative amount.

**Detection:** `amount < 0` after parsing.

**Policy:** Imported with negative `amount_inr` (converted: -$30 × ₹86.8 = -₹2,604). The credit reduces the overall Parasailing cost. Warning logged: `negative_amount`.

**Rationale:** The note "one slot got cancelled" confirms this is a genuine refund/credit, not a data error. A negative expense is semantically valid — it offsets the original cost.

---

### Anomaly 15 — Ambiguous date format: "Mar-14" (row 27)
**Problem:** Row 27: `date = "Mar-14"`. All other rows use `DD-MM-YYYY`. This could be March 14th (Mon-DD) or a typo for a different format.

**Detection:** Regex `r'^[A-Za-z]+-\d+$'` matches month-name formats. We try `%b-%d` (e.g. `Mar-14`) and assume current year (2026).

**Policy:** Parsed as `2026-03-14`. Warning logged asking user to verify.

**Rationale:** March 14 is consistent with the surrounding rows (all Goa trip, 2026-03-08 to 2026-03-14). Contextually correct. We flag but import.

---

### Anomaly 16 — Payer name with trailing whitespace (row 27)
**Problem:** Row 27: `paid_by = "rohan "` (trailing space). Also all-lowercase.

**Detection:** `raw_paid_by != raw_paid_by.strip()` checks whitespace. All-lowercase check catches `"rohan"` after stripping.

**Policy:** Stripped and resolved. Warning logged: `payer_name_case` (the lowercase flag fires after stripping).

**Rationale:** Trailing whitespace is a data quality issue, not a data error. The expense is valid.

---

### Anomaly 17 — Missing currency (row 28)
**Problem:** Row 28: `Groceries DMart, currency=""`. Note says "forgot to set currency."

**Detection:** `currency` field is blank after stripping.

**Policy:** Defaulted to INR. Warning logged: `missing_currency`.

**Rationale:** Context (India, flat expenses) makes INR the correct default. The note confirms it was a forgotten field. We import and flag.

---

### Anomaly 18 — Zero-amount expense (row 31) ← SKIPPED
**Problem:** Row 31: `Dinner order Swiggy, ₹0`. Note says "counted twice earlier - fixing later."

**Detection:** `amount == 0` after parsing.

**Policy:** Row **skipped**. Error logged: `zero_amount`.

**Rationale:** A zero-amount expense has no effect on balances. The note implies this was a placeholder/correction attempt, not a real expense. Importing it would add noise.

---

### Anomaly 19 — Ambiguous date: DD-MM vs MM-DD (row 34)
**Problem:** Row 34: `date = "04-05-2026"`. Could be April 5 (DD-MM-YYYY, standard in India) or May 4 (MM-DD-YYYY, US format). The note says "is this April 5 or May 4? format is a mess".

**Detection:** When a DD-MM-YYYY date has both day and month ≤ 12, we check if it's the specific known ambiguous value `04-05-2026`.

**Policy:** Treated as DD-MM-YYYY → `2026-05-04` (May 4). Warning logged: `ambiguous_date`. Row is also flagged as `out_of_order_row` because 2026-05-04 appears between April rows in the file.

**Rationale:** The note explicitly flags this ambiguity. We choose DD-MM as the default (consistent with all other rows in this file) but surface it to the user. If the user intended April 5, they must manually edit the expense.

---

### Anomaly 20 — Departed member in split_with (row 36)
**Problem:** Row 36: `02-04-2026, Groceries BigBasket, Priya, Aisha;Rohan;Priya;Meera`. Meera left the group on `2026-03-29`. This April 2 expense incorrectly includes her. The note says "oops Meera still in the group list."

**Detection:** For each participant in `split_with`, compare `expense_date` against `member.left_at`. If `expense_date > left_at`, the member is flagged.

**Policy:** Meera is excluded from the split. The expense is split among only Aisha, Rohan, and Priya. Warning logged: `departed_member_in_split`.

**Rationale:** Sam's requirement generalizes: membership dates must be respected. Meera left in March; an April grocery bill should not affect her balance.

---

### Anomaly 21 — Deposit payment logged as expense (row 38)
**Problem:** Row 38: `Sam deposit share, Sam, ₹15000`. This is Sam paying Aisha a security deposit — a payment, not a shared expense. The note says "Sam moving in! paid Aisha his deposit."

**Detection:** Description contains "deposit share" which matches the settlement keyword list.

**Policy:** Imported as a settlement (Sam → Aisha, ₹15000). Also stored in `expenses` with `is_settlement=1` for audit trail. Excluded from expense-based balance calculations.

**Rationale:** A deposit is a payment between two people, not a shared flat expense. If treated as an expense, it would incorrectly charge all flatmates for Sam's deposit.

---

### Anomaly 22 — Conflicting split_type and split_details (row 42)
**Problem:** Row 42: `Furniture for common room, Aisha, ₹12000, split_type=equal, split_details="Aisha 1; Rohan 1; Priya 1; Sam 1"`. Split type says equal but split_details has share-style values. Note says "split_type says equal but someone added shares anyway."

**Detection:** `split_type == "equal"` AND `split_details` contains numeric values matching `r'\d+\s*[;$]'`.

**Policy:** `split_type = "equal"` takes precedence. The split_details are ignored (they happen to produce the same result: equal 4-way split). Warning logged: `conflicting_split_info`.

**Rationale:** "Equal" + "1;1;1;1" shares are mathematically identical. No data is lost. We document the conflict and use the declared split_type.

---

### Notes on what was NOT flagged and why

- **Row 9 "priya" case:** Detected as `payer_name_case` (anomaly 4 above).
- **Row 11 "Priya S":** Detected as `payer_name_fuzzy` (anomaly 6 above).
- **Row 5 Dev's Feb dinner:** Dev's membership was set to the Goa trip (2026-03-08). The Feb dinner was a pre-trip visitor meal. This is detected as `expense_before_joining` but is legitimately a grey area.
- **Row 12 Aisha birthday cake:** Aisha is correctly excluded from the split (the split_details names only Rohan, Priya, Meera). Not an error.
- **Row 34 chronological ordering:** Flagged as `out_of_order_row`. Does not affect balance calculations.
