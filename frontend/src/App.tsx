import { BookOpen, Settings2 } from "lucide-react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import UploadPage from "./pages/UploadPage";
import SwipePage from "./pages/SwipePage";
import SummaryPage from "./pages/SummaryPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand" aria-label="知页首页">
          <img className="brand-icon" src="/logo.svg" alt="" />
          <strong>
            知页<span>Zhiye</span>
          </strong>
        </Link>
        <nav aria-label="主导航">
          <NavLink to="/" end>
            <BookOpen size={16} />
            <span>我的课件</span>
          </NavLink>
          <NavLink to="/settings">
            <Settings2 size={16} />
            <span>AI 设置</span>
          </NavLink>
        </nav>
        <span className="local-badge">
          <span className="status-dot" />
          本地优先
        </span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/decks/:deckId" element={<SwipePage />} />
          <Route path="/decks/:deckId/summary" element={<SummaryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route
            path="*"
            element={
              <div className="empty-page">
                <h1>这里还没有内容</h1>
                <Link to="/" className="text-link mt-4">
                  返回首页
                </Link>
              </div>
            }
          />
        </Routes>
      </main>
      <footer className="app-footer">
        <span>Zhiye / 知页</span>
        <span>每一页，都学得明白。</span>
        <span>开源 · MIT</span>
      </footer>
    </div>
  );
}
