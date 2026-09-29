import { useCallback, useState } from "react";
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
