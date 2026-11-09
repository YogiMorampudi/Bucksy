import { useEffect, useState } from 'react';
import { ArrowDownLeft, ArrowUpRight, IndianRupee, ShieldCheck } from 'lucide-react';
import { api } from '../lib/api';

export default function Overview() {
  const [health, setHealth] = useState('checking');
  useEffect(() => {
    let active = true;
    api('/health').then(() => { if (active) setHealth('online'); })
      .catch(() => { if (active) setHealth('offline'); });
    return () => { active = false; };
  }, []);

  return <>
    <section className="welcome-row"><div><p className="eyebrow">PERSONAL FINANCE DASHBOARD</p><h2>Welcome to your new Bucksy workspace</h2><p className="muted">Your existing Flask app and records stay in place while we move the interface to React.</p></div><div className={`backend-chip ${health}`}><span className="pulse-dot"/>{health === 'checking' ? 'Checking Flask API' : health === 'online' ? 'Flask backend reachable' : 'Flask backend not detected'}</div></section>
    <section className="stats-grid">
      <article className="stat-card"><div className="stat-top"><span>Total balance</span><span className="stat-icon violet"><IndianRupee size={18}/></span></div><strong>—</strong><small>Will load from your existing database</small></article>
      <article className="stat-card"><div className="stat-top"><span>Total income</span><span className="stat-icon green"><ArrowDownLeft size={18}/></span></div><strong>—</strong><small>Waiting for the dashboard API</small></article>
      <article className="stat-card"><div className="stat-top"><span>Total expenses</span><span className="stat-icon orange"><ArrowUpRight size={18}/></span></div><strong>—</strong><small>Waiting for the dashboard API</small></article>
    </section>
    <section className="panel migration-panel"><div className="panel-icon"><ShieldCheck size={21}/></div><div><h3>Migration checkpoint 1</h3><p>React + Vite is now separated into its own <code>frontend</code> folder. The Flask application, templates, authentication logic and database adapter remain untouched.</p><ul><li>React Router navigation is ready.</li><li>API client uses cookie credentials for Flask sessions.</li><li>Vite proxies API requests to Flask on port 5000.</li></ul><p className="note">No financial records are copied, reset or migrated in this step.</p></div></section>
  </>;
}
