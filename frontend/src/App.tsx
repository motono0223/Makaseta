import { NavLink, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Settings from "./pages/Settings";
import ComingSoon from "./pages/ComingSoon";
import Staff from "./pages/Staff";
import HireStaff from "./pages/HireStaff";
import StaffDetail from "./pages/StaffDetail";

const NAV = [
  { to: "/", label: "オフィスホーム", end: true },
  { to: "/staff", label: "社員名簿" },
  { to: "/projects", label: "プロジェクト" },
  { to: "/library", label: "資料室" },
  { to: "/inbox", label: "受信箱" },
  { to: "/settings", label: "設定" },
];

export default function App() {
  return (
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
          <Route path="/projects" element={<ComingSoon title="プロジェクト" what="プロジェクト、ロール、バックログとカンバン" />} />
          <Route path="/library" element={<ComingSoon title="資料室" what="文書のアップロード・検索・閲覧" />} />
          <Route path="/inbox" element={<ComingSoon title="受信箱" what="質問・レビュー待ち・エラーの通知" />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<ComingSoon title="ページが見つかりません" what="" />} />
        </Routes>
      </main>
    </div>
  );
}
