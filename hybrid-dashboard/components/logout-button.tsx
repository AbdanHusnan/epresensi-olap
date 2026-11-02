'use client';
import { useState } from 'react';
export function LogoutButton() {
  const [pending,setPending]=useState(false);
  const [error,setError]=useState('');
  async function logout() {
    setPending(true);setError('');
    try { const r=await fetch('/api/auth/logout',{method:'POST'});if(!r.ok)throw new Error();window.location.assign('/login'); }
    catch { setError('Gagal keluar. Silakan coba lagi.');setPending(false); }
  }
  return <div><button className="signout" onClick={logout} disabled={pending}>{pending ? 'Keluar…' : 'Keluar'} <span aria-hidden="true">↗</span></button>{error&&<p role="alert">{error}</p>}</div>;
}
