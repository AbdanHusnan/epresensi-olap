import { Brand } from './brand';
import { OrganizationLogo } from './organization-logo';
import { LogoutButton } from './logout-button';
import { MetabaseEmbed } from './metabase-embed';
import { type User } from '../lib/auth';
import { testRuns } from '../lib/test-runs';
export function DashboardPage({ user }: { user: User }) {
  const analytical=user.role==='director';
  const title=analytical?'Analytical dashboard':'Operational dashboard';
  return <div className="workspace">
    <aside className="sidebar"><Brand/><div className="workspace-label">WORKSPACE</div><a className="nav-link active" href={analytical?'/analytical':'/operational'} aria-current="page"><span aria-hidden="true">▥</span>{analytical?'Organization overview':'Department overview'}<span className="nav-dot"/></a>
      <div className="sidebar-context"><span className="context-icon" aria-hidden="true">◎</span><p>Your workspace</p><strong>{analytical?'Top management':'Middle management'}</strong><small>{analytical?'Organization-wide attendance':'Daily department attendance'}</small></div>
      <div className="sidebar-footer"><span className="live-dot"/> Prototype workspace<span>Phase 01</span></div>
    </aside>
    <div className="workspace-body"><header className="topbar"><div className="breadcrumbs">Workspace <span>/</span> <strong>{analytical?'Analytical':'Operational'}</strong></div><div className="topbar-actions"><div className="user-menu"><span className="avatar">{analytical?'DR':'MG'}</span><div><strong>{user.name}</strong><small>{analytical?'Director':'Manager'}</small></div><LogoutButton/></div><OrganizationLogo/></div></header>
      <main className={`dashboard-main ${analytical?'analytical-main':''}`}>{!analytical&&<div className="page-heading"><div><p className="eyebrow">{analytical?'THE ORGANIZATION AT A GLANCE':'YOUR DEPARTMENT, IN FOCUS'}</p><h1>{title}</h1><p className="page-description">{analytical?'Understand attendance across departments, with a shared view of the numbers.':'Review daily attendance and find the records that need follow-up.'}</p></div><span className="scope-badge"><span aria-hidden="true">◎</span>{analytical?'All departments':`Department ${user.departmentId}`}</span></div>}
        <MetabaseEmbed role={user.role} runs={testRuns} publicUrl={process.env.METABASE_PUBLIC_URL||''}/>
        {!analytical&&<footer className="page-footer"><span>e-Presensi · Attendance insights</span><span>Reporting timezone: Asia/Jakarta</span></footer>}
      </main>
    </div>
  </div>;
}
