import { FormEvent, useCallback, useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { ThreadProvider } from "./components/ThreadDrawer";
import Inbox from "./pages/Inbox";
import Skills from "./pages/Skills";
import { usePolling } from "./usePolling";
import Home from "./pages/Home";
import Settings from "./pages/Settings";
import ComingSoon from "./pages/ComingSoon";
import Staff from "./pages/Staff";
import HireStaff from "./pages/HireStaff";
import StaffDetail from "./pages/StaffDetail";
import Library from "./pages/Library";
import LibraryRoom from "./pages/LibraryRoom";
import Projects from "./pages/Projects";
import ProjectNew from "./pages/ProjectNew";
import ProjectDetail from "./pages/ProjectDetail";

const NAV = [
  { to: "/", label: "オフィスホーム", end: true },
  { to: "/staff", label: "社員名簿" },
  { to: "/projects", label: "プロジェクト" },
  { to: "/library", label: "資料室" },
  { to: "/skills", label: "スキル" },
  { to: "/inbox", label: "受信箱" },
  { to: "/settings", label: "設定" },
];

export default function App() {
  const [auth, setAuth] = useState<{ required: boolean; authenticated: boolean } | null>(null);
  const checkAuth = useCallback(() => {
    api.authStatus().then(setAuth).catch(() => setAuth({ required: false, authenticated: true }));
  }, []);
  useEffect(() => {
    checkAuth();
    window.addEventListener("makaseta:logged-out", checkAuth);
    return () => window.removeEventListener("makaseta:logged-out", checkAuth);
  }, [checkAuth]);

  if (!auth) return null;
  if (!auth.authenticated) return <Login onDone={checkAuth} />;
  return <Office canLogout={auth.required} onLogout={() => api.logout().finally(checkAuth)} />;
}

function Login({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.login(password);
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <div className="login">
      <form className="card login-card form" onSubmit={submit}>
        <div className="brand login-brand">
          <span className="brand-name">makaseta</span>
          <span className="brand-sub">任せた</span>
        </div>
        <div className="field">
          <label htmlFor="password">パスワード</label>
          <input id="password" type="password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p className="status bad">{error}</p>}
        <button type="submit" className="btn primary">ログイン</button>
      </form>
    </div>
  );
}

function Office({ canLogout, onLogout }: { canLogout: boolean; onLogout: () => void }) {
  const [inboxCount, setInboxCount] = useState(0);
  const refreshInbox = useCallback(() => {
    api.inbox().then((items) => setInboxCount(items.length)).catch(() => undefined);
  }, []);
  usePolling(refreshInbox, 8000);

  return (
    <ThreadProvider>
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">
            <span className="brand-name">makaseta</span>
            <span className="brand-sub">任せた</span>
          </div>
          <nav>
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className="nav-link">
                {item.label}
                {item.to === "/inbox" && inboxCount > 0 && <span className="nav-badge">{inboxCount}</span>}
              </NavLink>
            ))}
          </nav>
          {canLogout && (
            <button type="button" className="nav-link logout" onClick={onLogout}>ログアウト</button>
          )}
        </aside>
        <main className="content">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/staff" element={<Staff />} />
            <Route path="/staff/new" element={<HireStaff />} />
            <Route path="/staff/:id" element={<StaffDetail />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/new" element={<ProjectNew />} />
            <Route path="/projects/:id" element={<ProjectDetail />} />
            <Route path="/library" element={<Library />} />
            <Route path="/library/:room/*" element={<LibraryRoom />} />
            <Route path="/inbox" element={<Inbox />} />
            <Route path="/skills" element={<Skills />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<ComingSoon title="ページが見つかりません" what="" />} />
          </Routes>
        </main>
      </div>
    </ThreadProvider>
  );
}
