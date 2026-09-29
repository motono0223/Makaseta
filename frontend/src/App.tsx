import { NavLink, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Settings from "./pages/Settings";
import ComingSoon from "./pages/ComingSoon";

const NAV = [
  { to: "/", label: "オフィスホーム", end: true },
  { to: "/staff", label: "社員名簿" },
  { to: "/projects", label: "プロジェクト" },
  { to: "/buckets", label: "バケット" },
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
          <Route path="/staff" element={<ComingSoon title="社員名簿" what="社員の雇用・編集・スレッド" />} />
          <Route path="/projects" element={<ComingSoon title="プロジェクト" what="プロジェクト、ロール、バックログとカンバン" />} />
          <Route path="/buckets" element={<ComingSoon title="バケット" what="文書のアップロード・検索・閲覧" />} />
          <Route path="/inbox" element={<ComingSoon title="受信箱" what="質問・レビュー待ち・エラーの通知" />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<ComingSoon title="ページが見つかりません" what="" />} />
        </Routes>
      </main>
    </div>
  );
}
