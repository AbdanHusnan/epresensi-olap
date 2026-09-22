import { Sidebar } from "@/components/layout/sidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Lewati navigasi</a>
      <Sidebar />
      <div className="workspace">
        <header className="topbar"><span>Dashboard Presensi</span><span className="draft-badge">Pratinjau</span></header>
        <main id="main-content" tabIndex={-1}>{children}</main>
        <footer>ePresensi <span>Dashboard manajemen</span></footer>
      </div>
    </div>
  );
}
