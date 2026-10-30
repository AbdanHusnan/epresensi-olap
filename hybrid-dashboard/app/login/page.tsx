import { redirect } from 'next/navigation';
import { currentUser, homeFor } from '../../lib/auth';
import { Brand } from '../../components/brand';
import { LoginForm } from '../../components/login-form';
export const dynamic = 'force-dynamic';
export default async function LoginPage() {
  const user=await currentUser();if(user)redirect(homeFor(user.role));
  return <main className="login-page"><section className="login-story"><Brand light/><div className="story-content"><span className="story-kicker"><span/> A CLEARER VIEW OF ATTENDANCE</span><h1>Better visibility.<br/>Better follow-up.</h1><p>One place to understand your organization’s attendance, from the big picture to the daily details.</p><div className="story-graphic" aria-hidden="true"><div className="graphic-top"><span>ATTENDANCE OVERVIEW</span><span>↗</span></div><div className="graphic-bars">{[42,62,51,78,67,89,76,94,81,100,87,110].map((height,i)=><i key={i} style={{height}}/>)}</div><div className="graphic-bottom"><span>Daily clarity</span><span>Organization-wide perspective</span></div></div></div><div className="story-footer"><span>Built around your role.</span><span>e-Presensi / 01</span></div></section>
    <section className="login-panel"><div className="login-panel-top"><span className="prototype-pill"><span/> Prototype</span></div><div className="login-content"><p className="eyebrow">WELCOME TO YOUR WORKSPACE</p><h2>Sign in to e-Presensi</h2><p className="login-intro">Attendance insights for better-informed decisions.</p><LoginForm/><div className="role-note"><span aria-hidden="true">◎</span><div><strong>A view for every responsibility</strong><p>Directors see organization insights. Managers see their department’s daily attendance.</p></div></div></div><footer className="login-footer">e-Presensi <span>Attendance management workspace</span></footer></section></main>;
}
