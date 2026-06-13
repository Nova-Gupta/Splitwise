import React, { useState, useEffect, useCallback, useRef } from 'react';
import './App.css';

const API = process.env.REACT_APP_API_URL || '';

// ─── API HELPER ───────────────────────────────────────────────────────────────
function useApi() {
  const token = localStorage.getItem('token');
  const headers = { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const call = async (method, path, body, isForm) => {
    const opts = { method, headers: isForm ? { Authorization: `Bearer ${token}` } : headers };
    if (body && !isForm) opts.body = JSON.stringify(body);
    if (isForm) opts.body = body;
    const res = await fetch(`${API}/api${path}`, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  };
  return {
    get: (p) => call('GET', p),
    post: (p, b) => call('POST', p, b),
    put: (p, b) => call('PUT', p, b),
    patch: (p, b) => call('PATCH', p, b),
    del: (p) => call('DELETE', p),
    upload: (p, form) => call('POST', p, form, true),
  };
}

// ─── AUTH CONTEXT ─────────────────────────────────────────────────────────────
function App() {
  const [user, setUser] = useState(null);
  const [page, setPage] = useState('login');
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [subPage, setSubPage] = useState('expenses');
  const [loading, setLoading] = useState(true);
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    localStorage.setItem('theme', dark ? 'dark' : 'light');
  }, [dark]);

  useEffect(() => {
    const saved = localStorage.getItem('user');
    if (saved) { setUser(JSON.parse(saved)); setPage('dashboard'); }
    setLoading(false);
  }, []);

  const toggleDark = () => setDark(d => !d);

  const login = (userData, token) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(userData));
    setUser(userData);
    setPage('dashboard');
  };

  const logout = () => {
    localStorage.clear();
    setUser(null);
    setPage('login');
    setSelectedGroup(null);
  };

  if (loading) return <div className="loading-screen"><div className="spinner"/></div>;

  if (!user) return <AuthPage onLogin={login} dark={dark} toggleDark={toggleDark} />;
  if (!selectedGroup) return <Dashboard user={user} onSelectGroup={(g) => { setSelectedGroup(g); setPage('group'); setSubPage('expenses'); }} onLogout={logout} dark={dark} toggleDark={toggleDark} />;
  return <GroupPage user={user} group={selectedGroup} subPage={subPage} onSubPage={setSubPage} onBack={() => setSelectedGroup(null)} onLogout={logout} dark={dark} toggleDark={toggleDark} />;
}

// ─── AUTH PAGE ────────────────────────────────────────────────────────────────
function AuthPage({ onLogin, dark, toggleDark }) {
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({ username: '', email: '', password: '', display_name: '' });
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const api = useApi();

  const submit = async (e) => {
    e.preventDefault(); setErr(''); setLoading(true);
    try {
      const data = mode === 'login'
        ? await api.post('/auth/login', { username: form.username, password: form.password })
        : await api.post('/auth/register', form);
      onLogin({ user_id: data.user_id, display_name: data.display_name, username: data.username || form.username }, data.token);
    } catch (e) { setErr(e.message); }
    setLoading(false);
  };

  return (
    <div className="auth-container">
      <div className="auth-panel-left">
        <div className="auth-brand">
          <div className="auth-brand-logo">💸</div>
          <div className="auth-brand-name">SplitSmart</div>
          <div className="auth-brand-sub">Split expenses fairly. No drama.</div>
          <div className="auth-feature"><div className="auth-feature-dot"/><span className="auth-feature-text">Track shared flat expenses with fair splits</span></div>
          <div className="auth-feature"><div className="auth-feature-dot"/><span className="auth-feature-text">Multi-currency support with historical rates</span></div>
          <div className="auth-feature"><div className="auth-feature-dot"/><span className="auth-feature-text">Smart CSV import with anomaly detection</span></div>
          <div className="auth-feature"><div className="auth-feature-dot"/><span className="auth-feature-text">Membership-aware balance calculations</span></div>
        </div>
      </div>
      <div className="auth-panel-right">
        <div className="auth-card">
          <div className="auth-card-top">
            <div>
              <h1 className="auth-title">{mode === 'login' ? 'Welcome back' : 'Create account'}</h1>
              <p className="auth-sub">{mode === 'login' ? 'Sign in to your account' : 'Join your group'}</p>
            </div>
            <button className="dark-toggle" onClick={toggleDark} title="Toggle dark mode">{dark ? '☀️' : '🌙'}</button>
          </div>
          <div className="tab-row">
            <button className={`tab-btn ${mode==='login'?'active':''}`} onClick={() => setMode('login')}>Sign in</button>
            <button className={`tab-btn ${mode==='register'?'active':''}`} onClick={() => setMode('register')}>Register</button>
          </div>
          <form onSubmit={submit} className="auth-form">
            {mode === 'register' && <>
              <input placeholder="Display name" value={form.display_name} onChange={e => setForm({...form, display_name: e.target.value})} required />
              <input placeholder="Email" type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} required />
            </>}
            <input placeholder="Username" value={form.username} onChange={e => setForm({...form, username: e.target.value})} required />
            <input placeholder="Password" type="password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} required />
            {err && <div className="error-msg">{err}</div>}
            <button type="submit" className="btn-primary" disabled={loading}>{loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
          </form>
          <div className="demo-creds">
            <strong>Demo accounts:</strong> aisha, rohan, priya, meera, sam — password: <strong>pass123</strong>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── DASHBOARD ────────────────────────────────────────────────────────────────
function Dashboard({ user, onSelectGroup, onLogout, dark, toggleDark }) {
  const [groups, setGroups] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [allUsers, setAllUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const api = useApi();

  const load = useCallback(async () => {
    try {
      const [g, u] = await Promise.all([api.get('/groups'), api.get('/users')]);
      setGroups(g); setAllUsers(u);
    } catch {}
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, []);

  return (
    <div className="page">
      <header className="topbar">
        <div className="topbar-left">
          <span className="logo-icon">💸</span>
          <span className="logo-text">SplitSmart</span>
        </div>
        <div className="topbar-right">
          <span className="user-name">👤 {user.display_name}</span>
          <button className="dark-toggle" onClick={toggleDark} title="Toggle dark mode">{dark ? '☀️' : '🌙'}</button>
          <button className="btn-ghost" onClick={onLogout}>Sign out</button>
        </div>
      </header>
      <main className="main-content">
        <div className="page-header">
          <h2>Your groups</h2>
          <button className="btn-primary" onClick={() => setShowCreate(true)}>+ New group</button>
        </div>
        {loading ? <Spinner/> : groups.length === 0
          ? <EmptyState icon="🏠" title="No groups yet" desc="Create a group to start splitting expenses." />
          : <div className="group-grid">
              {groups.map(g => <GroupCard key={g.id} group={g} onClick={() => onSelectGroup(g)} />)}
            </div>
        }
      </main>
      {showCreate && <CreateGroupModal allUsers={allUsers} currentUser={user} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
    </div>
  );
}

function GroupCard({ group, onClick }) {
  const activeMembers = group.members?.filter(m => !m.left_at) || [];
  return (
    <div className="group-card" onClick={onClick}>
      <div className="group-card-icon">🏠</div>
      <div className="group-card-body">
        <h3>{group.name}</h3>
        <p className="group-card-meta">{activeMembers.length} active member{activeMembers.length !== 1 ? 's' : ''}</p>
        {group.description && <p className="group-card-desc">{group.description}</p>}
      </div>
    </div>
  );
}

function CreateGroupModal({ allUsers, currentUser, onClose, onCreated }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [members, setMembers] = useState([]);
  const [err, setErr] = useState('');
  const api = useApi();

  const toggle = (uid) => {
    if (uid === currentUser.user_id) return;
    setMembers(prev => prev.includes(uid) ? prev.filter(x=>x!==uid) : [...prev, uid]);
  };

  const submit = async () => {
    if (!name.trim()) { setErr('Group name required'); return; }
    try {
      await api.post('/groups', { name, description: desc, members: members.map(uid => ({ user_id: uid })) });
      onCreated();
    } catch(e) { setErr(e.message); }
  };

  return (
    <Modal title="Create group" onClose={onClose}>
      <input placeholder="Group name" value={name} onChange={e=>setName(e.target.value)} className="modal-input" />
      <input placeholder="Description (optional)" value={desc} onChange={e=>setDesc(e.target.value)} className="modal-input" />
      <p className="field-label">Add members</p>
      <div className="member-list">
        {allUsers.map(u => (
          <label key={u.id} className={`member-chip ${members.includes(u.id)||u.id===currentUser.user_id?'selected':''}`}>
            <input type="checkbox" checked={members.includes(u.id)||u.id===currentUser.user_id} onChange={()=>toggle(u.id)} style={{display:'none'}}/>
            {u.display_name} {u.id===currentUser.user_id && '(you)'}
          </label>
        ))}
      </div>
      {err && <div className="error-msg">{err}</div>}
      <div className="modal-actions">
        <button className="btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={submit}>Create group</button>
      </div>
    </Modal>
  );
}

// ─── GROUP PAGE ───────────────────────────────────────────────────────────────
function GroupPage({ user, group, subPage, onSubPage, onBack, onLogout, dark, toggleDark }) {
  const [groupData, setGroupData] = useState(group);
  const api = useApi();

  const reload = useCallback(async () => {
    try { const g = await api.get(`/groups/${group.id}`); setGroupData(g); } catch {}
  }, [group.id]);
  useEffect(() => { reload(); }, []);

  const tabs = [
    { key: 'expenses', label: '💰 Expenses' },
    { key: 'balances', label: '⚖️ Balances' },
    { key: 'settlements', label: '✅ Settlements' },
    { key: 'import', label: '📁 Import' },
    { key: 'members', label: '👥 Members' },
  ];

  return (
    <div className="page">
      <header className="topbar">
        <div className="topbar-left">
          <button className="btn-ghost back-btn" onClick={onBack}>← Groups</button>
          <span className="group-title">{groupData.name}</span>
        </div>
        <div className="topbar-right">
          <span className="user-name">👤 {user.display_name}</span>
          <button className="dark-toggle" onClick={toggleDark} title="Toggle dark mode">{dark ? '☀️' : '🌙'}</button>
          <button className="btn-ghost" onClick={onLogout}>Sign out</button>
        </div>
      </header>
      <nav className="sub-nav">
        {tabs.map(t => <button key={t.key} className={`sub-nav-btn ${subPage===t.key?'active':''}`} onClick={()=>onSubPage(t.key)}>{t.label}</button>)}
      </nav>
      <main className="main-content">
        {subPage === 'expenses' && <ExpensesTab group={groupData} user={user} onReload={reload} />}
        {subPage === 'balances' && <BalancesTab group={groupData} user={user} />}
        {subPage === 'settlements' && <SettlementsTab group={groupData} user={user} />}
        {subPage === 'import' && <ImportTab group={groupData} user={user} onReload={reload} />}
        {subPage === 'members' && <MembersTab group={groupData} user={user} onReload={reload} />}
      </main>
    </div>
  );
}

// ─── EXPENSES TAB ─────────────────────────────────────────────────────────────
function ExpensesTab({ group, user, onReload }) {
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editExp, setEditExp] = useState(null);
  const [detailExp, setDetailExp] = useState(null);
  const api = useApi();

  const load = useCallback(async () => {
    try { const e = await api.get(`/groups/${group.id}/expenses`); setExpenses(e); }
    catch {} setLoading(false);
  }, [group.id]);
  useEffect(() => { load(); }, []);

  const del = async (id) => {
    if (!window.confirm('Delete this expense?')) return;
    try { await api.del(`/expenses/${id}`); load(); } catch(e) { alert(e.message); }
  };

  return (
    <div>
      <div className="tab-header">
        <h3>Expenses</h3>
        <button className="btn-primary" onClick={()=>setShowAdd(true)}>+ Add expense</button>
      </div>
      {loading ? <Spinner/> : expenses.length === 0
        ? <EmptyState icon="💸" title="No expenses yet" desc="Add your first shared expense." />
        : <div className="expense-list">
            {expenses.map(e => (
              <div key={e.id} className={`expense-row ${e.is_settlement?'settlement-row':''}`}>
                <div className="expense-main" onClick={()=>setDetailExp(e)} style={{cursor:'pointer'}}>
                  <div className="expense-desc">
                    {e.is_settlement && <span className="badge badge-success">Settlement</span>}
                    {e.import_row && <span className="badge badge-info" title={`CSV row ${e.import_row}`}>CSV</span>}
                    <span>{e.description}</span>
                  </div>
                  <div className="expense-meta">
                    <span>{e.paid_by_name} paid</span>
                    <span className="dot">·</span>
                    <span>{e.expense_date}</span>
                    {e.currency !== 'INR' && <span className="dot">·</span>}
                    {e.currency !== 'INR' && <span className="fx-badge">{e.currency} @ {e.exchange_rate}</span>}
                  </div>
                </div>
                <div className="expense-amount">
                  <span className="amount">₹{e.amount_inr.toFixed(2)}</span>
                  <div className="expense-actions">
                    <button className="icon-btn" onClick={()=>setEditExp(e)} title="Edit">✏️</button>
                    <button className="icon-btn danger" onClick={()=>del(e.id)} title="Delete">🗑️</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
      }
      {(showAdd || editExp) && (
        <ExpenseModal
          group={group} user={user}
          expense={editExp}
          onClose={()=>{ setShowAdd(false); setEditExp(null); }}
          onSaved={()=>{ setShowAdd(false); setEditExp(null); load(); }}
        />
      )}
      {detailExp && <ExpenseDetailModal expense={detailExp} onClose={()=>setDetailExp(null)} />}
    </div>
  );
}

function ExpenseDetailModal({ expense, onClose }) {
  return (
    <Modal title="Expense details" onClose={onClose}>
      <table className="detail-table">
        <tbody>
          <tr><td>Description</td><td>{expense.description}</td></tr>
          <tr><td>Date</td><td>{expense.expense_date}</td></tr>
          <tr><td>Paid by</td><td>{expense.paid_by_name}</td></tr>
          <tr><td>Amount</td><td>₹{expense.amount_inr?.toFixed(2)}</td></tr>
          {expense.currency !== 'INR' && <>
            <tr><td>Original</td><td>{expense.currency} {expense.amount?.toFixed(2)}</td></tr>
            <tr><td>Rate</td><td>1 {expense.currency} = ₹{expense.exchange_rate}</td></tr>
          </>}
          <tr><td>Split type</td><td>{expense.split_type}</td></tr>
          {expense.category && <tr><td>Category</td><td>{expense.category}</td></tr>}
          {expense.import_row && <tr><td>CSV row</td><td>{expense.import_row}</td></tr>}
        </tbody>
      </table>
      <p className="field-label" style={{marginTop:'1rem'}}>Split breakdown</p>
      <div className="split-list">
        {expense.splits?.map(s => (
          <div key={s.user_id} className="split-row">
            <span>{s.display_name}</span>
            <span>₹{s.amount_inr?.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </Modal>
  );
}

function ExpenseModal({ group, user, expense, onClose, onSaved }) {
  const activeMembers = group.members?.filter(m => !m.left_at) || group.members || [];
  const api = useApi();
  const [form, setForm] = useState({
    description: expense?.description || '',
    amount: expense?.amount || '',
    currency: expense?.currency || 'INR',
    exchange_rate: expense?.exchange_rate || '',
    split_type: expense?.split_type || 'equal',
    paid_by: expense?.paid_by || (user?.user_id),
    expense_date: expense?.expense_date || new Date().toISOString().split('T')[0],
    category: expense?.category || '',
    notes: expense?.notes || '',
    is_settlement: expense?.is_settlement || 0,
  });
  const [splits, setSplits] = useState(() => {
    if (expense?.splits) return expense.splits.map(s => ({ user_id: s.user_id, display_name: s.display_name, amount: s.amount_inr, percentage: s.share_ratio || '', shares: s.share_ratio || 1 }));
    return activeMembers.map(m => ({ user_id: m.user_id, display_name: m.display_name, amount: 0, percentage: (100/activeMembers.length).toFixed(1), shares: 1 }));
  });
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);

  const updateSplit = (uid, field, val) => {
    setSplits(prev => prev.map(s => s.user_id === uid ? { ...s, [field]: val } : s));
  };

  const buildSplitsInput = () => {
    if (form.split_type === 'equal') return splits.map(s => ({ user_id: s.user_id }));
    if (form.split_type === 'exact') return splits.map(s => ({ user_id: s.user_id, amount: parseFloat(s.amount)||0 }));
    if (form.split_type === 'percentage') return splits.map(s => ({ user_id: s.user_id, percentage: parseFloat(s.percentage)||0 }));
    if (form.split_type === 'share') return splits.map(s => ({ user_id: s.user_id, shares: parseFloat(s.shares)||1 }));
    return [];
  };

  const submit = async () => {
    setErr(''); setLoading(true);
    try {
      const payload = {
        ...form,
        amount: parseFloat(form.amount),
        exchange_rate: form.currency === 'USD' ? (parseFloat(form.exchange_rate)||83.5) : 1.0,
        splits: buildSplitsInput(),
      };
      if (expense) await api.put(`/expenses/${expense.id}`, payload);
      else await api.post(`/groups/${group.id}/expenses`, payload);
      onSaved();
    } catch(e) { setErr(e.message); }
    setLoading(false);
  };

  const totalSplit = form.split_type === 'exact' ? splits.reduce((a,s)=>a+parseFloat(s.amount||0),0) : null;
  const totalPct = form.split_type === 'percentage' ? splits.reduce((a,s)=>a+parseFloat(s.percentage||0),0) : null;

  return (
    <Modal title={expense ? 'Edit expense' : 'Add expense'} onClose={onClose} wide>
      <div className="form-grid">
        <label className="form-field full">
          <span>Description</span>
          <input value={form.description} onChange={e=>setForm({...form,description:e.target.value})} placeholder="e.g. Groceries" required />
        </label>
        <label className="form-field">
          <span>Amount</span>
          <input type="number" step="0.01" min="0" value={form.amount} onChange={e=>setForm({...form,amount:e.target.value})} placeholder="0.00" required />
        </label>
        <label className="form-field">
          <span>Currency</span>
          <select value={form.currency} onChange={e=>setForm({...form,currency:e.target.value})}>
            <option value="INR">INR ₹</option>
            <option value="USD">USD $</option>
          </select>
        </label>
        {form.currency === 'USD' && (
          <label className="form-field">
            <span>Rate (1 USD = ₹)</span>
            <input type="number" step="0.01" value={form.exchange_rate} onChange={e=>setForm({...form,exchange_rate:e.target.value})} placeholder="83.50" />
          </label>
        )}
        <label className="form-field">
          <span>Paid by</span>
          <select value={form.paid_by} onChange={e=>setForm({...form,paid_by:parseInt(e.target.value)})}>
            {activeMembers.map(m => <option key={m.user_id} value={m.user_id}>{m.display_name}</option>)}
          </select>
        </label>
        <label className="form-field">
          <span>Date</span>
          <input type="date" value={form.expense_date} onChange={e=>setForm({...form,expense_date:e.target.value})} />
        </label>
        <label className="form-field">
          <span>Split type</span>
          <select value={form.split_type} onChange={e=>setForm({...form,split_type:e.target.value})}>
            <option value="equal">Equal</option>
            <option value="exact">Exact amounts</option>
            <option value="percentage">Percentage</option>
            <option value="share">By shares</option>
          </select>
        </label>
        <label className="form-field">
          <span>Category</span>
          <select value={form.category} onChange={e=>setForm({...form,category:e.target.value})}>
            {['','food','rent','utilities','entertainment','travel','household','other'].map(c => <option key={c} value={c}>{c||'— none —'}</option>)}
          </select>
        </label>
        <label className="form-field full">
          <span>Notes</span>
          <input value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})} placeholder="Optional notes" />
        </label>
        <label className="form-field">
          <span><input type="checkbox" checked={!!form.is_settlement} onChange={e=>setForm({...form,is_settlement:e.target.checked?1:0})} /> Mark as settlement</span>
        </label>
      </div>

      <div style={{marginTop:'1rem'}}>
        <p className="field-label">Split among</p>
        {totalPct !== null && Math.abs(totalPct - 100) > 0.1 && <div className="warn-msg">Percentages sum to {totalPct.toFixed(1)}% (must be 100%)</div>}
        {totalSplit !== null && form.amount && Math.abs(totalSplit - parseFloat(form.amount)) > 0.5 && <div className="warn-msg">Split total ₹{totalSplit.toFixed(2)} ≠ expense ₹{parseFloat(form.amount).toFixed(2)}</div>}
        <div className="split-editor">
          {splits.map(s => (
            <div key={s.user_id} className="split-edit-row">
              <span className="split-name">{s.display_name}</span>
              {form.split_type === 'equal' && <span className="split-hint">Equal share</span>}
              {form.split_type === 'exact' && <input type="number" step="0.01" value={s.amount} onChange={e=>updateSplit(s.user_id,'amount',e.target.value)} placeholder="₹0.00" className="split-input" />}
              {form.split_type === 'percentage' && <input type="number" step="0.1" max="100" value={s.percentage} onChange={e=>updateSplit(s.user_id,'percentage',e.target.value)} placeholder="%" className="split-input" />}
              {form.split_type === 'share' && <input type="number" step="0.5" min="0" value={s.shares} onChange={e=>updateSplit(s.user_id,'shares',e.target.value)} placeholder="shares" className="split-input" />}
            </div>
          ))}
        </div>
      </div>
      {err && <div className="error-msg">{err}</div>}
      <div className="modal-actions">
        <button className="btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={submit} disabled={loading}>{loading ? 'Saving…' : expense ? 'Save changes' : 'Add expense'}</button>
      </div>
    </Modal>
  );
}

// ─── BALANCES TAB ─────────────────────────────────────────────────────────────
function BalancesTab({ group, user }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showBreakdown, setShowBreakdown] = useState(null);
  const api = useApi();

  useEffect(() => {
    api.get(`/groups/${group.id}/balances`).then(d=>{ setData(d); setLoading(false); }).catch(()=>setLoading(false));
  }, [group.id]);

  if (loading) return <Spinner/>;
  if (!data) return <div className="error-msg">Could not load balances.</div>;

  const myId = user.user_id;
  const myBalance = data.balances?.find(b => b.user_id === myId);
  const myTransactions = data.transactions?.filter(t => t.from === myId || t.to === myId);

  return (
    <div>
      <div className="tab-header"><h3>Balances</h3></div>

      {myBalance && (
        <div className={`my-balance-card ${myBalance.net > 0 ? 'positive' : myBalance.net < 0 ? 'negative' : 'zero'}`}>
          <div className="my-balance-label">Your balance</div>
          <div className="my-balance-amount">{myBalance.net > 0 ? '+' : ''}₹{myBalance.net.toFixed(2)}</div>
          <div className="my-balance-desc">
            {myBalance.net > 0 ? 'You are owed this amount' : myBalance.net < 0 ? 'You owe this amount' : 'All settled up!'}
          </div>
        </div>
      )}

      <div className="section-title">Suggested payments</div>
      {data.transactions?.length === 0
        ? <div className="all-clear">✅ All settled up! No payments needed.</div>
        : <div className="transaction-list">
            {data.transactions?.map((t,i) => (
              <div key={i} className={`transaction-row ${t.from===myId?'mine':''}`}>
                <div className="transaction-names">
                  <span className="from-name">{t.from_name}</span>
                  <span className="arrow"> → </span>
                  <span className="to-name">{t.to_name}</span>
                </div>
                <div className="transaction-amount">₹{t.amount.toFixed(2)}</div>
              </div>
            ))}
          </div>
      }

      <div className="section-title" style={{marginTop:'1.5rem'}}>Individual balances</div>
      <div className="balance-list">
        {data.balances?.map(b => (
          <div key={b.user_id} className="balance-row">
            <div className="balance-name">{b.display_name} {b.user_id===myId && '(you)'}</div>
            <div className={`balance-net ${b.net>0?'pos':b.net<0?'neg':''}`}>
              {b.net > 0 ? '+' : ''}₹{b.net.toFixed(2)}
              <span className="balance-desc">{b.net>0?' owed':b.net<0?' owes':' settled'}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="section-title" style={{marginTop:'1.5rem'}}>Expense breakdown (per Rohan's requirement)</div>
      <p className="hint-text">Click any expense to see exactly which participants owe what.</p>
      <div className="expense-breakdown-list">
        {data.expense_details?.map(e => (
          <div key={e.id} className="breakdown-item">
            <div className="breakdown-header" onClick={()=>setShowBreakdown(showBreakdown===e.id?null:e.id)} style={{cursor:'pointer'}}>
              <div>
                <div className="breakdown-desc">{e.description}</div>
                <div className="breakdown-meta">{e.date} · Paid by {e.paid_by_name}{e.currency!=='INR'?` · ${e.currency} @ ${e.exchange_rate}`:''}</div>
              </div>
              <div className="breakdown-amount">₹{e.amount_inr?.toFixed(2)} {showBreakdown===e.id?'▲':'▼'}</div>
            </div>
            {showBreakdown===e.id && (
              <div className="breakdown-splits">
                {e.splits?.map(s=>(
                  <div key={s.user_id} className="breakdown-split-row">
                    <span>{s.display_name}</span>
                    <span>owes ₹{s.amount_inr?.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── SETTLEMENTS TAB ──────────────────────────────────────────────────────────
function SettlementsTab({ group, user }) {
  const [settlements, setSettlements] = useState([]);
  const [balances, setBalances] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [loading, setLoading] = useState(true);
  const api = useApi();
  const members = group.members || [];

  const load = useCallback(async () => {
    try {
      const [s, b] = await Promise.all([api.get(`/groups/${group.id}/settlements`), api.get(`/groups/${group.id}/balances`)]);
      setSettlements(s); setBalances(b.transactions || []);
    } catch {} setLoading(false);
  }, [group.id]);
  useEffect(() => { load(); }, []);

  return (
    <div>
      <div className="tab-header">
        <h3>Settlements</h3>
        <button className="btn-primary" onClick={()=>setShowAdd(true)}>+ Record payment</button>
      </div>
      {loading ? <Spinner/> : <>
        {balances.length > 0 && (
          <div className="suggested-box">
            <p className="field-label">Suggested payments</p>
            {balances.map((t,i) => (
              <div key={i} className="suggestion-row">
                <span>{t.from_name} → {t.to_name}: ₹{t.amount.toFixed(2)}</span>
                <button className="btn-small" onClick={()=>setShowAdd({from:t.from,to:t.to,amount:t.amount})}>Record this</button>
              </div>
            ))}
          </div>
        )}
        <div className="settlement-list">
          {settlements.length === 0
            ? <EmptyState icon="✅" title="No recorded payments" desc="Record payments to track who's settled up." />
            : settlements.map(s => (
                <div key={s.id} className="settlement-item">
                  <div>
                    <div><strong>{s.from_name}</strong> paid <strong>{s.to_name}</strong></div>
                    <div className="settlement-meta">{s.settled_at}{s.notes?` · ${s.notes}`:''}</div>
                  </div>
                  <div className="settlement-amount">₹{s.amount_inr.toFixed(2)}</div>
                </div>
              ))}
        </div>
      </>}
      {showAdd && (
        <SettlementModal group={group} prefill={typeof showAdd==='object'?showAdd:null} members={members} onClose={()=>setShowAdd(false)} onSaved={()=>{ setShowAdd(false); load(); }} />
      )}
    </div>
  );
}

function SettlementModal({ group, prefill, members, onClose, onSaved }) {
  const activeMembers = members.filter(m=>!m.left_at);
  const [from, setFrom] = useState(prefill?.from || '');
  const [to, setTo] = useState(prefill?.to || '');
  const [amount, setAmount] = useState(prefill?.amount || '');
  const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
  const [notes, setNotes] = useState('');
  const [err, setErr] = useState('');
  const api = useApi();

  const submit = async () => {
    if (!from || !to || !amount) { setErr('All fields required'); return; }
    if (from === to) { setErr('Payer and recipient must be different'); return; }
    try {
      await api.post(`/groups/${group.id}/settlements`, { paid_by: parseInt(from), paid_to: parseInt(to), amount: parseFloat(amount), settled_at: date, notes });
      onSaved();
    } catch(e) { setErr(e.message); }
  };

  return (
    <Modal title="Record payment" onClose={onClose}>
      <div className="form-grid">
        <label className="form-field">
          <span>Who paid</span>
          <select value={from} onChange={e=>setFrom(e.target.value)}>
            <option value="">— select —</option>
            {activeMembers.map(m=><option key={m.user_id} value={m.user_id}>{m.display_name}</option>)}
          </select>
        </label>
        <label className="form-field">
          <span>Paid to</span>
          <select value={to} onChange={e=>setTo(e.target.value)}>
            <option value="">— select —</option>
            {activeMembers.map(m=><option key={m.user_id} value={m.user_id}>{m.display_name}</option>)}
          </select>
        </label>
        <label className="form-field">
          <span>Amount (₹)</span>
          <input type="number" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)} placeholder="0.00" />
        </label>
        <label className="form-field">
          <span>Date</span>
          <input type="date" value={date} onChange={e=>setDate(e.target.value)} />
        </label>
        <label className="form-field full">
          <span>Notes (optional)</span>
          <input value={notes} onChange={e=>setNotes(e.target.value)} placeholder="e.g. via UPI" />
        </label>
      </div>
      {err && <div className="error-msg">{err}</div>}
      <div className="modal-actions">
        <button className="btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={submit}>Record payment</button>
      </div>
    </Modal>
  );
}

// ─── IMPORT TAB ───────────────────────────────────────────────────────────────
function ImportTab({ group, user, onReload }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [reports, setReports] = useState([]);
  const [selectedReport, setSelectedReport] = useState(null);
  const [approvals, setApprovals] = useState({});
  const api = useApi();
  const fileRef = useRef();

  useEffect(() => {
    api.get(`/groups/${group.id}/import/reports`).then(setReports).catch(()=>{});
  }, [group.id]);

  const submit = async () => {
    if (!file) return;
    setLoading(true); setReport(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await api.upload(`/groups/${group.id}/import`, form);
      setReport(r); onReload();
      const rs = await api.get(`/groups/${group.id}/import/reports`);
      setReports(rs);
    } catch(e) { alert(e.message); }
    setLoading(false);
  };

  const loadReport = async (id) => {
    try { const r = await api.get(`/groups/${group.id}/import/reports/${id}`); setSelectedReport(r); } catch {}
  };

  const displayReport = selectedReport?.report_json || report;

  return (
    <div>
      <div className="tab-header"><h3>Import CSV</h3></div>
      <div className="import-box">
        <p className="import-desc">Upload <code>expenses_export.csv</code> to import expenses. The importer will detect anomalies and produce a full report.</p>
        <div className="file-drop" onClick={()=>fileRef.current.click()}>
          {file ? <span>📄 {file.name}</span> : <span>Click to choose CSV file</span>}
          <input ref={fileRef} type="file" accept=".csv" style={{display:'none'}} onChange={e=>setFile(e.target.files[0])} />
        </div>
        <button className="btn-primary" onClick={submit} disabled={!file||loading}>{loading?'Importing…':'Import CSV'}</button>
      </div>

      {displayReport && <ImportReport report={displayReport} />}

      {reports.length > 0 && (
        <div style={{marginTop:'2rem'}}>
          <div className="section-title">Past imports</div>
          <div className="report-list">
            {reports.map(r => (
              <div key={r.id} className="report-row" onClick={()=>loadReport(r.id)} style={{cursor:'pointer'}}>
                <div>
                  <div>{r.filename}</div>
                  <div className="report-meta">{r.imported_at} · {r.imported_rows}/{r.total_rows} rows imported</div>
                </div>
                <span className="badge badge-info">View report</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ImportReport({ report }) {
  const [tab, setTab] = useState('summary');
  const s = report.summary || {};
  const severityColors = { error: '#E24B4A', warning: '#BA7517', info: '#378ADD' };

  return (
    <div className="import-report">
      <h4>Import report</h4>
      <div className="report-stats">
        <div className="stat-chip"><div className="stat-n">{s.total_rows||0}</div><div className="stat-l">Total rows</div></div>
        <div className="stat-chip success"><div className="stat-n">{s.imported||0}</div><div className="stat-l">Imported</div></div>
        <div className="stat-chip danger"><div className="stat-n">{s.skipped||0}</div><div className="stat-l">Skipped</div></div>
        <div className="stat-chip warning"><div className="stat-n">{s.anomalies_found||0}</div><div className="stat-l">Anomalies</div></div>
        {(s.pending_approval||0) > 0 && <div className="stat-chip info"><div className="stat-n">{s.pending_approval}</div><div className="stat-l">Pending approval</div></div>}
      </div>
      <div className="report-tabs">
        {['summary','anomalies','skipped','pending'].map(t=>(
          <button key={t} className={`tab-btn ${tab===t?'active':''}`} onClick={()=>setTab(t)}>{t}</button>
        ))}
      </div>
      {tab === 'anomalies' && (
        <div className="anomaly-list">
          {(report.anomalies||[]).length===0 ? <p>No anomalies found.</p>
          : report.anomalies.map((a,i) => (
            <div key={i} className="anomaly-row" style={{borderLeft:`3px solid ${severityColors[a.severity]||'#888'}`}}>
              <div className="anomaly-header">
                <span className="anomaly-row-num">Row {a.row}</span>
                <span className="anomaly-type">{a.type}</span>
                <span className={`badge badge-${a.severity==='error'?'danger':a.severity==='warning'?'warning':'info'}`}>{a.severity}</span>
              </div>
              <div className="anomaly-detail">{a.detail}</div>
              <div className="anomaly-action">→ {a.action}</div>
            </div>
          ))}
        </div>
      )}
      {tab === 'skipped' && (
        <div className="anomaly-list">
          {(report.skipped||[]).length===0 ? <p>No rows skipped.</p>
          : report.skipped.map((s,i) => (
            <div key={i} className="anomaly-row" style={{borderLeft:'3px solid #E24B4A'}}>
              <span>Row {s.row}: {s.reason}</span>
            </div>
          ))}
        </div>
      )}
      {tab === 'pending' && (
        <div className="anomaly-list">
          {(report.pending_approval||[]).length===0 ? <p>No rows pending approval.</p>
          : report.pending_approval.map((p,i) => (
            <div key={i} className="anomaly-row" style={{borderLeft:'3px solid #BA7517'}}>
              <div className="anomaly-header">
                <span>Row {p.row}</span>
                <span className="badge badge-warning">Possible duplicate of row {p.original_row}</span>
              </div>
              <div>{p.description} · ₹{p.amount} · {p.date}</div>
              <div className="approval-btns">
                <button className="btn-small success">✓ Approve import</button>
                <button className="btn-small">✗ Discard</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {tab === 'summary' && (
        <div className="summary-prose">
          <p>The importer processed <strong>{s.total_rows}</strong> rows and successfully imported <strong>{s.imported}</strong> expenses.</p>
          {s.skipped > 0 && <p><strong>{s.skipped}</strong> rows were skipped due to unrecoverable errors (missing amount, invalid date, unknown payer). See the "skipped" tab for details.</p>}
          {s.anomalies_found > 0 && <p><strong>{s.anomalies_found}</strong> anomalies were detected (duplicate entries, currency conversions, settlement rows, membership conflicts). See the "anomalies" tab for a full log.</p>}
          {s.pending_approval > 0 && <p><strong>{s.pending_approval}</strong> rows were flagged as potential duplicates and held for your approval (per Meera's requirement).</p>}
        </div>
      )}
    </div>
  );
}

// ─── MEMBERS TAB ──────────────────────────────────────────────────────────────
function MembersTab({ group, user, onReload }) {
  const [allUsers, setAllUsers] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [newMember, setNewMember] = useState('');
  const [joinDate, setJoinDate] = useState(new Date().toISOString().split('T')[0]);
  const [leaveDate, setLeaveDate] = useState('');
  const api = useApi();

  useEffect(() => { api.get('/users').then(setAllUsers).catch(()=>{}); }, []);

  const members = group.members || [];

  const markLeft = async (uid) => {
    const date = prompt('Enter leave date (YYYY-MM-DD):', new Date().toISOString().split('T')[0]);
    if (!date) return;
    try { await api.patch(`/groups/${group.id}/members/${uid}`, { left_at: date }); onReload(); }
    catch(e) { alert(e.message); }
  };

  const addMember = async () => {
    if (!newMember) return;
    try {
      await api.post(`/groups/${group.id}/members`, { user_id: parseInt(newMember), joined_at: joinDate });
      setShowAdd(false); onReload();
    } catch(e) { alert(e.message); }
  };

  return (
    <div>
      <div className="tab-header">
        <h3>Members</h3>
        <button className="btn-primary" onClick={()=>setShowAdd(true)}>+ Add member</button>
      </div>
      <div className="members-list">
        {members.map(m => (
          <div key={`${m.user_id}-${m.joined_at}`} className={`member-row ${m.left_at?'inactive':''}`}>
            <div className="member-avatar">{m.display_name?.[0]?.toUpperCase()}</div>
            <div className="member-info">
              <div className="member-name">{m.display_name} {m.user_id===user.user_id&&'(you)'}</div>
              <div className="member-dates">
                Joined {m.joined_at}{m.left_at?` · Left ${m.left_at}`:''}
              </div>
            </div>
            <div className="member-status">
              {m.left_at
                ? <span className="badge badge-danger">Left</span>
                : <><span className="badge badge-success">Active</span>
                   <button className="btn-small" onClick={()=>markLeft(m.user_id)}>Mark left</button></>
              }
            </div>
          </div>
        ))}
      </div>
      {showAdd && (
        <Modal title="Add member" onClose={()=>setShowAdd(false)}>
          <div className="form-grid">
            <label className="form-field full">
              <span>User</span>
              <select value={newMember} onChange={e=>setNewMember(e.target.value)}>
                <option value="">— select —</option>
                {allUsers.filter(u => !members.find(m=>m.user_id===u.id&&!m.left_at)).map(u=><option key={u.id} value={u.id}>{u.display_name}</option>)}
              </select>
            </label>
            <label className="form-field full">
              <span>Joined on</span>
              <input type="date" value={joinDate} onChange={e=>setJoinDate(e.target.value)} />
            </label>
          </div>
          <div className="modal-actions">
            <button className="btn-ghost" onClick={()=>setShowAdd(false)}>Cancel</button>
            <button className="btn-primary" onClick={addMember}>Add member</button>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ─── SHARED COMPONENTS ────────────────────────────────────────────────────────
function Modal({ title, onClose, children, wide }) {
  return (
    <div className="modal-overlay" onClick={e=>e.target.className==='modal-overlay'&&onClose()}>
      <div className={`modal-box ${wide?'wide':''}`}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

function Spinner() { return <div className="spinner-wrap"><div className="spinner"/></div>; }
function EmptyState({ icon, title, desc }) {
  return <div className="empty-state"><div className="empty-icon">{icon}</div><h4>{title}</h4><p>{desc}</p></div>;
}

export default App;
