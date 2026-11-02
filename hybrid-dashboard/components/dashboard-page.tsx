import { Brand } from './brand';
import { OrganizationLogo } from './organization-logo';
import { LogoutButton } from './logout-button';
import { MetabaseEmbed } from './metabase-embed';
import { type User } from '../lib/auth';
import { testRuns } from '../lib/test-runs';
export function DashboardPage({ user }: { user: User }) {
  const analytical=user.role==='director';
  const title=analytical?'Dashboard Analitikal':'Dashboard Operasional';
  return <div className="workspace">
    <aside className="sidebar"><Brand/><div className="workspace-label">RUANG KERJA</div><a className="nav-link active" href={analytical?'/analytical':'/operational'} aria-current="page"><span aria-hidden="true">▥</span>{analytical?'Ikhtisar Organisasi':'Ikhtisar Departemen'}<span className="nav-dot"/></a>
      <div className="sidebar-context"><span className="context-icon" aria-hidden="true">◎</span><p>Ruang kerja Anda</p><strong>{analytical?'Manajemen Eksekutif':'Manajemen Operasional'}</strong><small>{analytical?'Presensi menyeluruh organisasi':'Presensi harian departemen'}</small></div>
      <div className="sidebar-footer"><span className="live-dot"/> Sistem Presensi BKD<span>Aktif</span></div>
    </aside>
    <div className="workspace-body"><header className="topbar"><div className="breadcrumbs">Ruang Kerja <span>/</span> <strong>{analytical?'Analitikal':'Operasional'}</strong></div><div className="topbar-actions"><div className="user-menu"><span className="avatar">{analytical?'DR':'MG'}</span><div><strong>{user.name}</strong><small>{analytical?'Direktur':'Manajer'}</small></div><LogoutButton/></div><OrganizationLogo/></div></header>
      <main className="dashboard-main analytical-main">
        <MetabaseEmbed role={user.role} runs={testRuns} publicUrl={process.env.METABASE_PUBLIC_URL||''} departmentId={user.departmentId}/>
      </main>
    </div>
  </div>;
}
