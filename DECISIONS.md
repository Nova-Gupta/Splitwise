# DECISIONS.md — Engineering & Product Decision Log

Each entry covers: the decision, options considered, what we chose, and why.

---

## D1 — Tech stack: Flask + SQLite vs Node/Express + PostgreSQL

**Context:** Need a relational database and a REST backend, deployable in 2 days.

**Options:**
1. Node.js + Express + PostgreSQL (or SQLite with better-sqlite3)
2. Python + Flask + SQLite
3. Django + PostgreSQL

**Decision:** Python + Flask + SQLite.

**Reasoning:**
- `better-sqlite3` requires native compilation (`node-gyp`) which fails in many CI/sandbox environments. This was the first thing we hit.
- SQLite is a relational DB (the requirement says "relational DBs only"), and for a flat of 6 people with ~50 expenses, it's more than adequate. SQLite with WAL mode handles concurrent reads well.
- Flask is minimal and explicit — every route is readable without framework magic, which makes the "walk through any line in the repo" evaluation easy to handle.
- Django would have been faster to scaffold but harder to explain at the line level.

**Tradeoff:** SQLite doesn't scale to multiple servers, but that's irrelevant here.

---

## D2 — Single-file React vs multi-component file structure

**Context:** Frontend needs to be a working React SPA, understandable end-to-end.

**Options:**
1. Standard CRA structure: separate files per component
2. Single `App.js` with all components

**Decision:** Single `App.js` file.

**Reasoning:**
- The evaluation explicitly says "point at any line and ask why it exists." A single file means no context-switching between files during a live session.
- All logic is visible in one scroll. The interviewer asking "how does the balance calculation reach the UI?" can trace it without jumping files.
- For a project with ~800 lines of UI code, file organization overhead outweighs the benefits.

**Tradeoff:** Not the pattern for a production codebase. If asked, I'll acknowledge this and explain the real-world alternative.

---

## D3 — Balance calculation: debt simplification algorithm

**Context:** With N people, the naive approach produces N×(N-1) possible transactions. We need to minimize payments.

**Options:**
1. Show raw net balances only (no suggested transactions)
2. Greedy min-cash-flow algorithm
3. Full LP optimization

**Decision:** Greedy two-pointer algorithm on sorted creditors and debtors.

**Reasoning:**
- The greedy approach runs in O(N log N) and produces near-optimal results for small groups (≤10 people). For our 6-person flat, it is optimal.
- LP optimization is overkill and adds a dependency.
- Showing only raw balances (who owes +/- how much) addresses Aisha's requirement ("one number per person") but doesn't show the settlement path. The greedy algorithm gives both.
- Rohan's requirement ("see exactly which expenses make that up") is handled by the expense breakdown endpoint, not the simplification algorithm.

**How it works:**
```python
creditors = sorted people who are owed money, descending
debtors = sorted people who owe money, descending
while creditors and debtors both have people:
    take the largest creditor and largest debtor
    settle min(what creditor is owed, what debtor owes)
    advance whichever list is exhausted
```

---

## D4 — Currency conversion: hardcoded rates vs live API

**Context:** Priya's requirement is that dollar amounts must be properly converted. The CSV has USD expenses from a Feb-Apr 2024 trip.

**Options:**
1. Live exchange rate API (forex.com, openexchangerates.org)
2. Hardcoded historical monthly averages
3. Ask the user to input the rate at import time

**Decision:** Hardcoded historical monthly averages, with the rate stored on each expense record.

**Reasoning:**
- These are historical expenses from Feb-Apr 2024. The correct rate is the rate that was in effect then, not today's rate. A live API would give the wrong number.
- Monthly averages from RBI reference data (Feb 2024: ₹83.1, Mar: ₹83.4, Apr: ₹83.7) are appropriate for flatmate expense tracking — per-day rates would imply false precision.
- Asking the user to input rates during import adds friction and risk of error.
- The rate is stored on `expenses.exchange_rate`, so it's transparent and editable.

**Tradeoff:** If currency is EURO or GBP, we don't have a rate. We import at 1:1 and flag it (see SCOPE.md Anomaly 9).

---

## D5 — Settlement handling: separate table vs expense flag

**Context:** Some CSV rows are payments between people (settlements), not shared expenses. We need to handle them without inflating balances.

**Options:**
1. Discard settlement rows during import
2. Store in `expenses` table with an `is_settlement` flag, exclude from balance calcs
3. Store in a separate `settlements` table only
4. Store in both (option 2 + 3)

**Decision:** Store in both tables (option 4).

**Reasoning:**
- The `expenses` table with `is_settlement=1` preserves the full import audit trail. Rohan can trace "row 11 of the CSV became expense #11 in our DB."
- The `settlements` table is the source of truth for balance calculation — clean and unambiguous.
- Balance query: `SELECT * FROM expenses WHERE is_settlement=0` and `SELECT * FROM settlements`. No ambiguity.
- Discarding settlements entirely would lose data the user might want to review.

---

## D6 — Membership timeline: join/leave dates

**Context:** Sam's requirement: expenses before they joined should not affect their balance.

**Options:**
1. Boolean `is_active` flag per member
2. `joined_at` and `left_at` dates per membership row
3. History table with events

**Decision:** `joined_at` + `left_at` on `group_members` with a `UNIQUE(group_id, user_id, joined_at)` constraint.

**Reasoning:**
- A boolean can't encode "left in March, rejoined in June." The unique constraint on `(group_id, user_id, joined_at)` allows multiple membership stints.
- The `left_at IS NULL` pattern for "still active" is idiomatic SQL and simple to query.
- Balance calculation can check `expense_date BETWEEN joined_at AND COALESCE(left_at, '9999-12-31')` for any member.
- A separate events table would be more flexible but adds complexity without benefit for this scale.

---

## D7 — Duplicate detection policy (Meera's requirement)

**Context:** The CSV has at least one duplicate entry. Meera wants to approve anything before it's deleted or changed.

**Options:**
1. Auto-delete duplicates, log which ones
2. Import both, warn the user
3. Hold duplicates in a pending queue, require explicit approval

**Decision:** Option 3 — pending approval queue.

**Reasoning:**
- Meera's exact words: "I want to approve anything the app deletes or changes." Auto-delete violates this directly.
- Importing both inflates balances silently — a "silent guess" which the assignment says is a failing answer.
- The pending queue surface in the import report shows: row number, what it duplicates, the data. One button imports it, one discards it. Meera has full control.

**Implementation:** Pending rows are stored in the import report JSON. A `/import/approve` endpoint accepts row numbers to import.

---

## D8 — Rounding: which person absorbs the leftover cent?

**Context:** Equal split of ₹100 among 3 people = ₹33.333... per person.

**Options:**
1. Round each to ₹33.33, last person gets ₹33.34
2. Round each to ₹33.33, discard the ₹0.01
3. Round each to ₹33.33, last person gets ₹33.34

**Decision:** Option 1/3 (same): last person in the list absorbs any rounding remainder.

**Reasoning:**
- Total must equal the original amount exactly. Discarding ₹0.01 creates a ₹0.01 imbalance that accumulates.
- "Last person absorbs remainder" is the standard approach (used by Splitwise, Tricount, etc.).
- We use: `share = round(total/n, 2)` for first n-1 people, `last_share = total - share*(n-1)`.
- This is documented in `_apply_splits()` in `app.py` and can be shown and modified live.

---

## D9 — Authentication: JWT vs sessions

**Context:** Need user authentication for a 6-person app.

**Options:**
1. Server-side sessions (cookie + session store)
2. JWT (stateless, stored in localStorage)

**Decision:** JWT stored in localStorage.

**Reasoning:**
- Stateless: Flask backend doesn't need a session store. Works with SQLite and any deployment.
- Simple to implement and reason about: the token contains `user_id` and `username`, signed with a secret.
- For a flat of 6 people with no public exposure, the localStorage XSS risk is acceptable. Production would use httpOnly cookies.
- Tokens expire after 7 days.

**Tradeoff:** No server-side revocation. If a token is compromised, it's valid until expiry. Acceptable for this context.

---

## D10 — Import: what to do with rows where payer is unknown

**Context:** A CSV row might name a payer who isn't in the group (typo, different name format, someone who never registered).

**Options:**
1. Skip the row, log error
2. Create a placeholder user
3. Assign to a catch-all "unknown" user

**Decision:** Skip the row, log a clear error.

**Reasoning:**
- We cannot safely assign an expense without knowing who paid. Creating a placeholder user would create orphaned data with no way to resolve it.
- The error message includes the raw payer name so the user can see exactly what wasn't recognized: `"Payer 'Dev' not found in group members"`.
- The fix is simple: add Dev to the group members list and reimport.
- A "silent guess" (option 2 or 3) is explicitly called out as a failing answer in the assignment.
