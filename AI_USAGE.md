# AI_USAGE.md — AI Tool Usage Log

## Tools Used
- **Claude (Anthropic, claude-sonnet-4-6)** — Primary development collaborator for architecture, code generation, documentation drafts, and debugging.

---

## Key Prompts Used

### 1. Initial architecture
> "I'm building a shared expenses app in Python/Flask with SQLite. The core challenge is a messy CSV import with at least 12 deliberate data problems. Design a schema that supports: group membership with join/leave dates, multi-currency expenses stored in INR, exact/equal/percentage/share splits, and a full anomaly report on CSV import."

### 2. Balance calculation
> "Implement a debt simplification algorithm in Python. Given a dict of {user_id: net_balance} where positive means 'owed money' and negative means 'owes money', return the minimum number of transactions to settle all debts."

### 3. CSV anomaly detection
> "Write a Flask route that ingests a CSV of shared expenses, detects at least: duplicates (same description+amount+date+payer), negative amounts, invalid amounts, unknown payers, settlement rows disguised as expenses, currency conversion issues, dates where payer wasn't yet a group member. For each, surface a structured anomaly object with row, type, detail, action, severity."

### 4. React balance UI
> "Build a React component for a balances tab that shows: (1) the current user's net balance highlighted, (2) a list of suggested payments to settle all debts, (3) a collapsible per-expense breakdown so users can trace exactly which expenses contribute to their balance."

---

## Cases Where AI Produced Something Wrong

### Case 1: Balance calculation double-counted settlements

**What the AI generated:**
The initial balance calculation in `get_balances()` summed ALL expenses including those with `is_settlement=1`. Since settlement rows also appear in the `settlements` table, the effect was double-counted — a ₹1500 settlement between Aisha and Meera subtracted ₹1500 from Aisha's balance twice.

**How I caught it:**
I manually traced the balance for the 3-row test case:
- Aisha paid ₹1500 to Rohan (expense)
- Rohan paid Aisha back ₹1500 (settlement, also stored as expense with is_settlement=1)
- Expected: net zero. Actual: Aisha was shown as being owed ₹1500.

**What I changed:**
Added `WHERE is_settlement=0` to the expenses query in `get_balances()`:
```python
expenses = db.execute(
    "SELECT * FROM expenses WHERE group_id=? AND is_settlement=0", (gid,)
).fetchall()
```
Then settlements are applied separately from the `settlements` table. No double-counting.

---

### Case 2: Split rounding left totals mismatched

**What the AI generated:**
The initial `_apply_splits()` for equal splits used `round(amount/n, 2)` for every person, including the last. For ₹100 split 3 ways: ₹33.33 × 3 = ₹99.99, not ₹100.00. The ₹0.01 disappeared silently.

**How I caught it:**
Testing the balance for a ₹2400 grocery split among 4 people:
- Expected each person to owe ₹600.00
- Actual: split table showed ₹599.99 × 4 = ₹2399.96 total, not ₹2400
- The payer was "owed" ₹2400 but only ₹2399.96 was distributed. Net: payer was permanently +₹0.04 over their balance.

**What I changed:**
Last person gets remainder:
```python
for i, s in enumerate(splits_input):
    amt = share if i < n-1 else round(amount_inr - share*(n-1), 2)
    db.execute("INSERT INTO expense_splits ...")
```
This matches how Splitwise and similar apps handle it.

---

### Case 3: JWT decode used wrong parameter name

**What the AI generated:**
```python
data = jwt.decode(token, SECRET_KEY, algorithms="HS256")  # string, not list
```

**How I caught it:**
The server threw `TypeError: 'str' object is not iterable` on every protected route during testing. Immediately visible in the Flask error log.

**What I changed:**
```python
data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])  # must be a list
```
The PyJWT 2.x API requires `algorithms` to be a list, not a string. This was a subtle API version difference the AI had wrong.

---

### Case 4: Date format detection false-positive

**What the AI generated:**
The initial date normalizer tried formats in this order: `%Y-%m-%d`, `%d/%m/%Y`, `%m/%d/%Y`. For `03/01/2024`, it successfully parsed as `%d/%m/%Y` → March 1st. But for `01/03/2024` it also matched `%d/%m/%Y` → January 3rd. For a US-format date (January 3rd, 2024), this would be wrong.

**How I caught it:**
Reviewing the anomaly log for the test CSV, the date `03/01/2024` parsed as `2024-03-01` which is correct (Rent March). But I noticed that `%d/%m/%Y` and `%m/%d/%Y` are ambiguous for dates where both day and month are ≤ 12.

**What I changed:**
Added a warning log for any date that could be ambiguous between D/M/Y and M/D/Y interpretations:
```python
if fmt in ("%d/%m/%Y", "%m/%d/%Y"):
    day = datetime.strptime(raw, fmt).day
    month = datetime.strptime(raw, fmt).month
    if day <= 12:
        log_anomaly(i, "ambiguous_date", 
                   f"Date '{raw}' is ambiguous between D/M/Y and M/D/Y",
                   "Interpreted as D/M/Y (day-first); verify manually")
```
Documented this in SCOPE.md as a known limitation.

---

## Overall Assessment

The AI was most useful for:
- Boilerplate Flask routing and SQLite patterns
- The debt simplification algorithm (correct after rounding fix)
- React component structure and CSS layout
- Documentation structure

The AI required correction for:
- Double-counting logic bugs in balance calculation (subtle business logic)
- Rounding precision in split calculation
- PyJWT API version-specific syntax
- Date format ambiguity handling

**Pattern observed:** The AI produces structurally correct code quickly but makes errors in edge cases involving: floating-point precision, API version differences, and business logic involving multiple data sources that must be reconciled. These are exactly the kinds of bugs that appear in production and require human review to catch.
