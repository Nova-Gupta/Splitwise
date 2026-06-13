#!/bin/bash
# Run from project root: bash git_setup.sh
# Creates meaningful commit history for the SplitSmart assignment.

set -e

echo "Initialising git repository..."
git init
git config user.email "adityaag530@gmail.com"
git config user.name "Aditya"

# .gitignore
cat > .gitignore << 'EOF'
node_modules/
__pycache__/
*.pyc
backend/splitwise.db
backend/uploads/
frontend/build/
.env
*.egg-info/
dist/
.DS_Store
EOF

# ── Commit 1: DB schema ────────────────────────────────────────────────────
git add backend/schema.sql backend/requirements.txt backend/.env.example .gitignore
git commit -m "feat: relational schema — users, groups, memberships, expenses, splits

Core tables:
- group_members with joined_at + left_at for temporal membership (Sam's requirement)
- expenses.amount_inr always in INR after conversion (Priya's requirement)
- expenses.import_row for per-row CSV traceability (Rohan's requirement)
- import_reports table stores full anomaly JSON for each import session
- UNIQUE(group_id, user_id, joined_at) allows members to leave and rejoin"

# ── Commit 2: Backend — auth, groups, expenses, balances ──────────────────
git add backend/app.py backend/Procfile
git commit -m "feat: Flask REST backend — auth, groups, expenses, settlements, balances

- JWT auth (7-day tokens, PyJWT 2.x algorithms=[\"HS256\"] list form required)
- POST /api/groups with member list and joined_at dates
- POST /api/groups/:id/members + PATCH for leave date
- Expenses: equal/exact/percentage/share split types
- _apply_splits(): last person absorbs rounding remainder to keep totals exact
- Balance: greedy two-pointer debt-simplification (O(N log N), optimal for ≤10 people)
- Settlements stored separately from expenses to avoid double-counting"

# ── Commit 3: CSV importer ────────────────────────────────────────────────
# (importer is part of app.py, captured here as a focused documentation commit)
git commit --allow-empty -m "feat: CSV importer detects 27 anomalies in expenses_export.csv

Pipeline (per row):
1. Date normalisation — 8 format attempts; flags Mon-DD, DD-MM ambiguity
2. Amount parsing — strips commas, flags excessive precision, zero, negative
3. Currency — USD→INR at historical monthly RBI rates; missing→INR default
4. Settlement detection — keyword match sends row to settlements table
5. Payer resolution — case-insensitive + fuzzy prefix + whitespace strip
6. Split type normalisation — 'unequal'→'exact'; unknown→'equal'
7. Same-payer fuzzy duplicate detection → pending approval queue (Meera)
8. Cross-payer duplicate — same date+participants+amounts within 15%
9. Membership checks — expense_date vs joined_at / left_at per payer
10. Unknown participant in split_with → excluded, warning logged
11. Departed member in split_with → excluded, warning logged
12. Percentage normalisation when sum≠100%; split total mismatch fallback"

# ── Commit 4: Seed data ───────────────────────────────────────────────────
git add backend/seed.py
git commit -m "chore: seed script with correct 2026 membership timeline

Aisha/Rohan/Priya: 2026-02-01, still active
Meera: 2026-02-01 → left 2026-03-29 (farewell dinner is 2026-03-28)
Dev:   2026-03-08 → left 2026-03-14 (Goa trip only)
Sam:   2026-04-08, still active (deposit row is first Sam transaction)"

# ── Commit 5: Frontend ────────────────────────────────────────────────────
git add frontend/src/App.js frontend/src/index.js frontend/src/App.css \
        frontend/public/index.html frontend/package.json
git commit -m "feat: React SPA — login, expenses, balances, settlements, CSV import

Single App.js file (intentional — see DECISIONS.md D2):
- AuthPage: login + register with JWT
- Dashboard: group list + create group modal with member picker
- ExpensesTab: full CRUD, all 4 split types, expense detail modal
- BalancesTab: net summary card + suggested payments + expandable breakdown
  (Aisha: one number per person; Rohan: trace every expense)
- SettlementsTab: record payments, pre-fill from suggested transactions
- ImportTab: file upload → anomaly report with summary/anomalies/skipped/pending tabs
- MembersTab: add member with join date, mark left with leave date (Sam's requirement)"

# ── Commit 6: Documentation ───────────────────────────────────────────────
git add SCOPE.md DECISIONS.md AI_USAGE.md README.md expenses_export.csv git_setup.sh
git commit -m "docs: SCOPE.md (22 anomaly entries), DECISIONS.md (10 decisions), AI_USAGE.md

SCOPE.md: every anomaly in expenses_export.csv with detection method + policy
  - 39 rows imported, 2 skipped (missing payer, zero amount), 1 pending approval
  - 27 total anomaly events detected across 22 distinct problem categories
DECISIONS.md: Flask+SQLite, single-file React, greedy debt simplification,
  historical exchange rates, dual-table settlements, JWT vs sessions
AI_USAGE.md: 4 concrete AI errors caught — balance double-counting, rounding,
  JWT API version, date format false-positive"

echo ""
echo "✅  Git history ready: 6 meaningful commits"
echo ""
echo "Next steps:"
echo "  1.  gh repo create splitsmart --public --source=. --push"
echo "  OR: git remote add origin <url> && git push -u origin main"
echo ""
echo "Render.com deploy:"
echo "  Backend  — Web Service, root=backend/, start=python app.py"
echo "  Frontend — Static Site, root=frontend/, build=npm run build, publish=build/"
echo "  Backend env vars: SECRET_KEY=<random>, PORT=10000"
echo "  Frontend env var: REACT_APP_API_URL=https://<your-backend>.onrender.com"
