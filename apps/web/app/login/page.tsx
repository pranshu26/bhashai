'use client';
import { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { api, setToken } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr('');
    setBusy(true);
    try {
      const r = mode === 'login' ? await api.login({ email, password }) : await api.signup({ email, password, name });
      setToken(r.accessToken);
      router.replace('/dashboard');
    } catch (e: any) {
      setErr(e.message || 'failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container">
      <div className="brand"><span className="dot" /> BhashAI</div>
      <p className="muted" style={{ marginTop: 6 }}>English → Indian-language document translation</p>
      <div className="center">
        <form className="card" style={{ width: 380 }} onSubmit={submit}>
          <div className="tabs">
            <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Log in</button>
            <button type="button" className={mode === 'signup' ? 'active' : ''} onClick={() => setMode('signup')}>Sign up</button>
          </div>
          {mode === 'signup' && (
            <>
              <label>Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
            </>
          )}
          <label>Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required />
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required />
          <div style={{ marginTop: 18 }}>
            <button type="submit" disabled={busy} style={{ width: '100%' }}>
              {busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}
            </button>
          </div>
          {err && <div className="err">{err}</div>}
        </form>
      </div>
    </div>
  );
}
