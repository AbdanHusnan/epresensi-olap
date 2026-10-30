'use client';
import { useState, type FormEvent } from 'react';
export function LoginForm() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [visible, setVisible] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPending(true); setError('');
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: form.get('username'), password: form.get('password') }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      window.location.assign(result.redirect);
    } catch (error) { setError(error instanceof Error ? error.message : 'Unable to sign in. Please try again.'); setPending(false); }
  }
  return <form onSubmit={submit} className="login-form">
    <label htmlFor="username">Username</label><input id="username" name="username" placeholder="Enter your username" autoComplete="username" required autoFocus maxLength={100}/>
    <label htmlFor="password">Password</label><div className="password-field"><input id="password" name="password" type={visible ? 'text' : 'password'} placeholder="Enter your password" autoComplete="current-password" required maxLength={256}/><button type="button" onClick={() => setVisible(!visible)} aria-label={visible ? 'Hide password' : 'Show password'}>{visible ? 'Hide' : 'Show'}</button></div>
    {error && <p className="form-error" role="alert">{error}</p>}
    <button className="primary-button" type="submit" disabled={pending}>{pending ? 'Signing in…' : 'Sign in'}<span aria-hidden="true">→</span></button>
    <p className="form-footnote">Your account opens the dashboard for your management role.</p>
  </form>;
}
