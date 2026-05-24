'use client';
import { useEffect, useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api, getToken, LANGUAGES, TONES, OUTPUT_MODES } from '@/lib/api';

export default function NewJob() {
  const router = useRouter();
  const [target, setTarget] = useState('hi');
  const [tone, setTone] = useState('EDUCATIONAL');
  const [outputMode, setOutputMode] = useState('LAYOUT_PRESERVED');
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState('');

  useEffect(() => {
    if (!getToken()) router.replace('/login');
  }, [router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) { setErr('Please choose a file'); return; }
    setErr('');
    try {
      setBusy('Creating job…');
      const job = await api.createJob({ targetLanguage: target, tone, outputMode });
      setBusy('Uploading…');
      await api.uploadFile(job.id, file);
      setBusy('Starting…');
      await api.startJob(job.id);
      router.replace(`/jobs/${job.id}`);
    } catch (e: any) {
      setErr(e.message || 'failed');
      setBusy('');
    }
  }

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand"><span className="dot" /> BhashAI</div>
        <Link href="/dashboard"><button className="secondary">← Dashboard</button></Link>
      </div>
      <div className="h1">New translation</div>
      <form className="card" onSubmit={submit}>
        <h2>Document</h2>
        <label>File (PDF, DOCX, or TXT)</label>
        <input type="file" accept=".pdf,.docx,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />

        <h2 style={{ marginTop: 22 }}>Settings</h2>
        <div className="grid2">
          <div>
            <label>Target language</label>
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              {Object.entries(LANGUAGES).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
            </select>
          </div>
          <div>
            <label>Tone</label>
            <select value={tone} onChange={(e) => setTone(e.target.value)}>
              {TONES.map((t) => <option key={t} value={t}>{t[0] + t.slice(1).toLowerCase()}</option>)}
            </select>
          </div>
        </div>
        <label>Output mode</label>
        <select value={outputMode} onChange={(e) => setOutputMode(e.target.value)}>
          {OUTPUT_MODES.map((m) => <option key={m} value={m}>{m.toLowerCase().replace('_', '-')}</option>)}
        </select>
        <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          Layout-preserved keeps the original design and swaps text in place (best for PDFs).
        </p>

        <div style={{ marginTop: 20 }} className="row">
          <button type="submit" disabled={!!busy}>{busy || 'Translate'}</button>
        </div>
        {err && <div className="err">{err}</div>}
      </form>
    </div>
  );
}
