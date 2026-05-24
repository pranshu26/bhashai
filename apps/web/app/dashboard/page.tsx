'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api, clearToken, getToken, LANGUAGES, type Job } from '@/lib/api';

function statusBadge(s: string) {
  if (s === 'COMPLETED') return <span className="badge ok">Completed</span>;
  if (s === 'PARTIALLY_COMPLETED') return <span className="badge warn">Partial</span>;
  if (s === 'FAILED') return <span className="badge err">Failed</span>;
  if (s === 'CANCELLED') return <span className="badge err">Cancelled</span>;
  if (s === 'PENDING' || s === 'UPLOADED') return <span className="badge">{s.toLowerCase()}</span>;
  return <span className="badge run">{s.toLowerCase()}</span>;
}

export default function Dashboard() {
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      router.replace('/login');
      return;
    }
    api
      .listJobs()
      .then(setJobs)
      .catch((e) => {
        if (String(e.message).startsWith('401')) {
          clearToken();
          router.replace('/login');
        } else setErr(e.message);
      })
      .finally(() => setLoading(false));
  }, [router]);

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand"><span className="dot" /> BhashAI</div>
        <div className="row">
          <Link href="/jobs/new"><button>+ New translation</button></Link>
          <button className="secondary" onClick={() => { clearToken(); router.replace('/login'); }}>Log out</button>
        </div>
      </div>
      <div className="h1">Your translations</div>
      <p className="muted">Upload a document, pick a language, and download a translation that keeps the original layout.</p>

      <div className="card" style={{ marginTop: 18 }}>
        {loading && <div className="muted">Loading…</div>}
        {!loading && jobs.length === 0 && <div className="muted">No jobs yet. Start one with “+ New translation”.</div>}
        {jobs.map((j) => (
          <Link key={j.id} href={`/jobs/${j.id}`} style={{ color: 'inherit' }}>
            <div className="jobrow">
              <div>
                <div style={{ fontWeight: 600 }}>{j.originalFileName || '(no file yet)'}</div>
                <div className="muted" style={{ fontSize: 13 }}>
                  English → {LANGUAGES[j.targetLanguage] || j.targetLanguage} · {j.tone?.toLowerCase()} · {j.outputMode?.toLowerCase().replace('_', ' ')}
                </div>
              </div>
              {statusBadge(j.status)}
            </div>
          </Link>
        ))}
        {err && <div className="err">{err}</div>}
      </div>
    </div>
  );
}
