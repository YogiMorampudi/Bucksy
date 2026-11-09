
import { useState } from 'react';
import { NavLink, Route, Routes } from 'react-router-dom';
import {
  Activity,
  ArrowLeftRight,
  BookOpen,
  Goal,
  LayoutDashboard,
  Menu,
  Wallet,
  X,
  Download,
  ShieldCheck
} from 'lucide-react';

import Overview from './pages/Overview.jsx';
import Admin from './pages/Admin.jsx';
import './app.css';

const nav = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
  { to: '/khata', label: 'Khata Book', icon: BookOpen },
  { to: '/achievements', label: 'Achievements', icon: Goal },
  { to: '/admin', label: 'Admin Panel', icon: ShieldCheck }
];

function ComingSoon({ title }) {
  return (
    <section className="panel coming">
      <div className="coming-icon"><Activity size={22} /></div>
      <h2>{title}</h2>
      <p>This React page is scaffolded. The next integration step will connect it to the existing Flask feature and database.</p>
    </section>
  );
}

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);

  // Download current webpage as HTML
  function downloadWebsite() {
    const html = '<!DOCTYPE html>\n' +
      document.documentElement.outerHTML;

    const blob = new Blob([html], {
      type: 'text/html;charset=utf-8'
    });

    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');

    link.href = url;
    link.download = 'Bucksy-Website.html';

    document.body.appendChild(link);
    link.click();
    link.remove();

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <div className="shell">
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <span className="brand-mark"><Wallet size={21} /></span>
          <span>Bucksy</span>
          <button className="mobile-close" onClick={() => setMenuOpen(false)} aria-label="Close menu">
            <X />
          </button>
        </div>

        <div className="nav-caption">WORKSPACE</div>

        <nav className="nav-list">
          {nav.map(item => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <div className="profile-avatar">B</div>
          <div>
            <strong>Bucksy account</strong>
            <small>React migration workspace</small>
          </div>
        </div>
      </aside>

      {menuOpen && (
        <button className="scrim" onClick={() => setMenuOpen(false)} aria-label="Close navigation" />
      )}

      <main className="main">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Menu />
          </button>

          <div>
            <span className="eyebrow">YOUR MONEY, IN CONTROL</span>
            <h1>Bucksy</h1>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              type="button"
              onClick={downloadWebsite}
              title="Download webpage as HTML"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '7px',
                padding: '9px 13px',
                borderRadius: '9px',
                border: '1px solid #64748b',
                cursor: 'pointer',
                fontWeight: '600'
              }}
            >
              <Download size={17} />
              Download
            </button>

            <span className="status-pill"><span /> React setup</span>
          </div>
        </header>

        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/transactions" element={<ComingSoon title="Transactions" />} />
          <Route path="/khata" element={<ComingSoon title="Khata Book" />} />
          <Route path="/achievements" element={<ComingSoon title="Achievements" />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<ComingSoon title="Page not found" />} />
        </Routes>

        <footer className="footer">
          BUCKSY <span>·</span> Keep every rupee accounted for.
        </footer>
      </main>
    </div>
  );
}
