'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { api, downloadJob, getToken, LANGUAGES, type Job } from '@/lib/api';

function badge(s: string) {
  if (s === 'COMPLETED') return <span className="badge ok">Completed</span>;
  if (s === 'PARTIALLY_COMPLETED') return <span className="badge warn">Partial — review</span>;
  if (s === 'FAILED' || s === 'CANCELLED') return <span className="badge err">{s.toLowerCase()}</span>;
  return <span className="badge run">{s.toLowerCase()}</span>;
}
const TERMINAL = ['COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED'];

export default function JobPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [meta, setMeta] = useState<Job | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState('');
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace('/login');
      return;
    }
    api.getJob(id).then(setMeta).catch(() => {});
    let stop = false;
    async function tick() {
      try {
        const p = await api.progress(id);
        if (stop) return;
        setJob(p);
        if (!TERMINAL.includes(p.status)) setTimeout(tick, 2000);
      } catch (e: any) {
        if (!stop) setErr(e.message);
      }
    }
    tick();
    return () => {
      stop = true;
    };
  }, [id, router]);

  const done = job && ['COMPLETED', 'PARTIALLY_COMPLETED'].includes(job.status);
  const pct = job?.progressPercentage ?? 0;

  async function onDownload() {
    setDownloading(true);
    try {
      const base = (meta?.originalFileName || 'document').replace(/\.[^.]+$/, '');
      const srcExt = meta?.originalFileName?.split('.').pop()?.toLowerCase();
      const outExt = srcExt === 'docx' ? 'docx' : srcExt === 'txt' ? 'txt' : 'pdf';
      await downloadJob(id, `${base}-${meta?.targetLanguage || 'translated'}.${outExt}`);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand"><span className="dot" /> BhashAI</div>
        <Link href="/dashboard"><button className="secondary">← Dashboard</button></Link>
      </div>

      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div className="h1">{meta?.originalFileName || 'Translation job'}</div>
        {job && badge(job.status)}
      </div>
      {meta && (
        <p className="muted">English → {LANGUAGES[meta.targetLanguage] || meta.targetLanguage} · {meta.tone?.toLowerCase()} · {meta.outputMode?.toLowerCase().replace('_', ' ')}</p>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Progress</h2>
        <div className="progress"><div style={{ width: `${pct}%` }} /></div>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <span className="muted">{job?.currentStage || '—'}</span>
          <span className="muted">{pct}%</span>
        </div>
        <div className="kv"><span className="muted">Status</span><span>{job?.status || '…'}</span></div>
        <div className="kv"><span className="muted">Chunks</span><span>{job?.completedChunks ?? 0} / {job?.totalChunks ?? 0}{(job?.failedChunks ?? 0) > 0 ? ` (${job?.failedChunks} failed)` : ''}</span></div>
        {job?.errorMessage && <div className="err">Note: {job.errorMessage}</div>}

        {done && (
          <div style={{ marginTop: 18 }}>
            {job?.status === 'PARTIALLY_COMPLETED' && (
              <p className="muted" style={{ fontSize: 13 }}>
                Some sections kept the original (e.g. text baked into images, or a failed chunk) and are flagged. The translated output is ready.
              </p>
            )}
            <button onClick={onDownload} disabled={downloading}>{downloading ? 'Preparing…' : '⬇ Download translated file'}</button>
          </div>
        )}
        {job && !done && job.status !== 'FAILED' && <p className="muted" style={{ fontSize: 13, marginTop: 12 }}>Translating… this page updates automatically.</p>}
        {err && <div className="err">{err}</div>}
      </div>
    </div>
  );
}
