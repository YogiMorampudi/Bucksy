import { useEffect, useState } from 'react';
import {
  ShieldCheck,
  Users,
  ArrowLeftRight,
  IndianRupee,
  Goal,
  Search,
  Trash2,
  ShieldAlert,
  UserCheck
} from 'lucide-react';
import { api } from '../lib/api';

export default function Admin() {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [statsData, usersData] = await Promise.all([
        api('/api/admin/stats'),
        api('/api/admin/users')
      ]);
      setStats(statsData);
      setUsers(usersData.users || []);
    } catch (err) {
      setError(err.message || 'Failed to load admin data. Ensure you are signed in as an administrator.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function handleToggleAdmin(uid, currentStatus) {
    try {
      await api(`/api/admin/users/${uid}/toggle-admin`, { method: 'POST' });
      setMessage(`Updated admin status for user.`);
      loadData();
      setTimeout(() => setMessage(null), 4000);
    } catch (err) {
      alert(err.message || 'Error updating user role');
    }
  }

  async function handleDeleteUser(uid, email) {
    if (!window.confirm(`Are you sure you want to permanently delete user ${email}?\nAll their transactions, goals, and records will be deleted forever.`)) {
      return;
    }
    try {
      await api(`/api/admin/users/${uid}`, { method: 'DELETE' });
      setMessage(`User ${email} was permanently deleted.`);
      loadData();
      setTimeout(() => setMessage(null), 4000);
    } catch (err) {
      alert(err.message || 'Error deleting user');
    }
  }

  const filteredUsers = users.filter(u =>
    (u.full_name || '').toLowerCase().includes(search.toLowerCase()) ||
    (u.email || '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      <section className="welcome-row">
        <div>
          <p className="eyebrow">CONTROL CENTER</p>
          <h2>Platform Administration & User Management 🛡️</h2>
          <p className="muted">Manage user privileges, inspect accounts, and monitor platform transaction metrics.</p>
        </div>
        <div className="status-pill" style={{ borderColor: '#f59e0b', color: '#f59e0b' }}>
          <span style={{ background: '#f59e0b', boxShadow: '0 0 0 4px #f59e0b22' }} />
          Admin Session
        </div>
      </section>

      {message && (
        <div style={{
          background: 'rgba(66, 214, 154, 0.12)',
          border: '1px solid #42d69a',
          color: '#42d69a',
          padding: '12px 18px',
          borderRadius: '12px',
          marginBottom: '20px',
          fontSize: '13px',
          fontWeight: '600'
        }}>
          ✓ {message}
        </div>
      )}

      {error && (
        <div style={{
          background: 'rgba(242, 85, 85, 0.12)',
          border: '1px solid #f25555',
          color: '#f87171',
          padding: '14px 18px',
          borderRadius: '12px',
          marginBottom: '20px',
          fontSize: '13px'
        }}>
          ⚠️ {error}
        </div>
      )}

      {/* Stat Cards */}
      <section className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', marginBottom: '25px' }}>
        <article className="stat-card">
          <div className="stat-top">
            <span>Total Registered</span>
            <span className="stat-icon violet"><Users size={18} /></span>
          </div>
          <strong>{stats ? stats.total_users : '—'}</strong>
          <small>Active user accounts</small>
        </article>

        <article className="stat-card">
          <div className="stat-top">
            <span>Transactions</span>
            <span className="stat-icon violet"><ArrowLeftRight size={18} /></span>
          </div>
          <strong>{stats ? stats.total_transactions : '—'}</strong>
          <small>Across entire platform</small>
        </article>

        <article className="stat-card">
          <div className="stat-top">
            <span>Platform Volume</span>
            <span className="stat-icon green"><IndianRupee size={18} /></span>
          </div>
          <strong>{stats ? `₹${Number(stats.total_volume).toLocaleString('en-IN')}` : '—'}</strong>
          <small>Logged cashflow</small>
        </article>

        <article className="stat-card">
          <div className="stat-top">
            <span>Savings Goals</span>
            <span className="stat-icon orange"><Goal size={18} /></span>
          </div>
          <strong>{stats ? stats.total_goals : '—'}</strong>
          <small>Active & achieved</small>
        </article>
      </section>

      {/* Users Directory Table */}
      <section className="panel" style={{ padding: '24px' }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '16px',
          paddingBottom: '20px',
          borderBottom: '1px solid #202a40',
          marginBottom: '20px'
        }}>
          <div>
            <h3 style={{ margin: '0 0 4px', font: "600 18px 'Space Grotesk'" }}>
              Registered Users ({filteredUsers.length})
            </h3>
            <p className="muted" style={{ fontSize: '12px' }}>
              Promote administrators or manage member accounts.
            </p>
          </div>

          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: '#111a2c',
            border: '1px solid #26324a',
            borderRadius: '9px',
            padding: '7px 12px'
          }}>
            <Search size={16} color="#71809b" />
            <input
              type="text"
              placeholder="Search user or email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                background: 'transparent',
                border: 'none',
                outline: 'none',
                color: '#fff',
                fontSize: '13px',
                width: '210px'
              }}
            />
          </div>
        </div>

        {loading ? (
          <p className="muted" style={{ textAlign: 'center', padding: '40px' }}>Loading platform users...</p>
        ) : filteredUsers.length === 0 ? (
          <p className="muted" style={{ textAlign: 'center', padding: '40px' }}>No users matched your search criteria.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ color: '#818da8', textAlign: 'left', borderBottom: '1px solid #1f293d', paddingBottom: '10px' }}>
                  <th style={{ padding: '12px 10px' }}>ID</th>
                  <th style={{ padding: '12px 10px' }}>User</th>
                  <th style={{ padding: '12px 10px' }}>Role</th>
                  <th style={{ padding: '12px 10px' }}>Joined Date</th>
                  <th style={{ padding: '12px 10px' }}>Transactions</th>
                  <th style={{ padding: '12px 10px' }}>Goals</th>
                  <th style={{ padding: '12px 10px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((u) => (
                  <tr key={u.id} style={{ borderBottom: '1px solid #161f33' }}>
                    <td style={{ padding: '14px 10px', color: '#64748b', fontFamily: 'monospace' }}>
                      #{u.id}
                    </td>
                    <td style={{ padding: '14px 10px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{
                          width: '32px',
                          height: '32px',
                          borderRadius: '50%',
                          background: '#1d273f',
                          display: 'grid',
                          placeItems: 'center',
                          color: '#c9bcff',
                          fontWeight: '700'
                        }}>
                          {(u.full_name || 'U')[0].toUpperCase()}
                        </div>
                        <div>
                          <strong style={{ display: 'block', color: '#e2e8f0' }}>{u.full_name}</strong>
                          <span style={{ fontSize: '11px', color: '#71809b' }}>{u.email}</span>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: '14px 10px' }}>
                      {u.is_admin ? (
                        <span style={{
                          background: 'rgba(245, 158, 11, 0.15)',
                          color: '#f59e0b',
                          border: '1px solid rgba(245, 158, 11, 0.3)',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          fontSize: '11px',
                          fontWeight: '700',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}>
                          <ShieldCheck size={12} /> Admin
                        </span>
                      ) : (
                        <span style={{
                          background: 'rgba(59, 130, 246, 0.1)',
                          color: '#60a5fa',
                          border: '1px solid rgba(59, 130, 246, 0.2)',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          fontSize: '11px',
                          fontWeight: '600'
                        }}>
                          Member
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '14px 10px', color: '#818da8' }}>
                      {(u.created_at || '').slice(0, 10)}
                    </td>
                    <td style={{ padding: '14px 10px' }}>
                      <strong style={{ color: '#cbd5e1' }}>{u.transactions_count || 0}</strong>
                      <span style={{ display: 'block', fontSize: '11px', color: '#64748b' }}>
                        ₹{Number(u.transactions_volume || 0).toLocaleString('en-IN')}
                      </span>
                    </td>
                    <td style={{ padding: '14px 10px', color: '#94a3b8' }}>
                      {u.goals_count || 0}
                    </td>
                    <td style={{ padding: '14px 10px', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '8px' }}>
                        <button
                          type="button"
                          onClick={() => handleToggleAdmin(u.id, u.is_admin)}
                          title={u.is_admin ? 'Demote to regular member' : 'Promote to Admin'}
                          style={{
                            background: '#1a233a',
                            border: '1px solid #2c3a5a',
                            color: '#cbd5e1',
                            padding: '6px 11px',
                            borderRadius: '7px',
                            fontSize: '11px',
                            cursor: 'pointer',
                            fontWeight: '600'
                          }}
                        >
                          {u.is_admin ? 'Demote' : 'Make Admin'}
                        </button>

                        <button
                          type="button"
                          onClick={() => handleDeleteUser(u.id, u.email)}
                          title="Permanently delete user"
                          style={{
                            background: 'rgba(239, 68, 68, 0.1)',
                            border: '1px solid rgba(239, 68, 68, 0.3)',
                            color: '#f87171',
                            padding: '6px 10px',
                            borderRadius: '7px',
                            fontSize: '11px',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px'
                          }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

