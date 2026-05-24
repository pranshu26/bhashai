export const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001/api';

const TOKEN_KEY = 'bhashai_token';

export function getToken(): string | null {
  return typeof window !== 'undefined' ? localStorage.getItem(TOKEN_KEY) : null;
}
export function setToken(t: string) {
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function req(path: string, opts: RequestInit = {}): Promise<any> {
  const token = getToken();
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string>) };
  if (token) headers['authorization'] = `Bearer ${token}`;
  const res = await fetch(API + path, { ...opts, headers });
  if (!res.ok) {
    let detail = '';
    try {
      detail = JSON.stringify(await res.json());
    } catch {
      detail = await res.text();
    }
    throw new Error(`${res.status} ${detail}`.slice(0, 300));
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res;
}

export interface Job {
  id: string;
  status: string;
  targetLanguage: string;
  tone: string;
  outputMode: string;
  originalFileName: string | null;
  progressPercentage?: number;
  currentStage?: string;
  totalChunks?: number;
  completedChunks?: number;
  failedChunks?: number;
  errorMessage?: string | null;
  createdAt?: string;
  hasOutput?: boolean;
}

export const api = {
  signup: (b: { email: string; password: string; name?: string }) =>
    req('/auth/signup', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(b) }),
  login: (b: { email: string; password: string }) =>
    req('/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(b) }),
  listJobs: (): Promise<Job[]> => req('/translation-jobs'),
  createJob: (b: Record<string, unknown>): Promise<Job> =>
    req('/translation-jobs', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(b) }),
  getJob: (id: string): Promise<Job> => req(`/translation-jobs/${id}`),
  uploadFile: (id: string, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return req(`/translation-jobs/${id}/upload`, { method: 'POST', body: fd });
  },
  startJob: (id: string) => req(`/translation-jobs/${id}/start`, { method: 'POST' }),
  progress: (id: string): Promise<Job> => req(`/translation-jobs/${id}/progress`),
};

export async function downloadJob(id: string, filename: string) {
  const token = getToken();
  const res = await fetch(`${API}/translation-jobs/${id}/download`, {
    headers: token ? { authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error('download failed');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const LANGUAGES: Record<string, string> = {
  hi: 'Hindi', mr: 'Marathi', bn: 'Bengali', pa: 'Punjabi', gu: 'Gujarati', ta: 'Tamil',
  te: 'Telugu', kn: 'Kannada', or: 'Odia', ur: 'Urdu', as: 'Assamese', ml: 'Malayalam',
};
export const TONES = ['FORMAL', 'INFORMAL', 'EDUCATIONAL', 'CONVERSATIONAL', 'TECHNICAL', 'LITERARY', 'GOVERNMENT', 'ACADEMIC'];
export const OUTPUT_MODES = ['LAYOUT_PRESERVED', 'REFLOWED', 'BILINGUAL'];
