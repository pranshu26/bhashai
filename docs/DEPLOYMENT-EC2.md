# BhashAI — AWS EC2 Deployment & Environment Guide

Two supported topologies. Start with **A** (single box), graduate to **B** (split processes)
when load grows. Both use the same images and `.env`.

## A. Single EC2 box (Docker Compose) — recommended start

```
                 ┌─────────────────────────── EC2 (Ubuntu 22.04) ───────────────────────────┐
Internet ─443──► Nginx ─┬─► api (NestJS :3001)                                                │
                        └─► web (Next.js :3000)                                                │
                            worker (NestJS, all queues)                                        │
                            parser-service (FastAPI :8000)        postgres:5432  redis:6379    │
                            [indictrans-service :8001  — optional, GPU box]                     │
                 └────────────────────────────────────────────────────────────────────────────┘
                            S3 (raw + processed buckets)  ← external
```

### 1. Provision
- Instance: `t3.large` (2 vCPU / 8 GB) minimum for API+web+worker+parser+pg+redis. Bump to
  `m6i.xlarge` for real workloads. OCR/LibreOffice render is CPU-hungry.
- Storage: 50–100 GB gp3 (temp artifacts spill before S3 upload).
- Security group: inbound 22 (your IP), 80, 443 only. DB/Redis stay on the Docker network.
- IAM: attach an **instance role** with least-privilege S3 access to the two buckets (preferred
  over static keys). If using keys, put them in `.env` (never in git).

### 2. Base setup
```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
sudo usermod -aG docker $USER && newgrp docker
git clone <your-repo> bhashai && cd bhashai
cp .env.example .env   # then edit (see env table below)
```

### 3. S3 buckets
```bash
aws s3 mb s3://bhashai-raw-<env>
aws s3 mb s3://bhashai-processed-<env>
# block public access; rely on presigned URLs. Lifecycle for temp artifacts (Phase 4):
#   processed/jobs/*/extracted/  expire 7d ;  processed/jobs/*/assets/  expire 7d
```

### 4. Run
```bash
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
docker compose -f infra/docker-compose.yml exec api pnpm --filter @bhashai/db prisma:migrate:deploy
docker compose -f infra/docker-compose.yml exec api pnpm --filter @bhashai/db seed   # optional
```
Compose services: `postgres`, `redis`, `api`, `worker`, `web`, `parser`. `indictrans` is in a
separate `infra/docker-compose.gpu.yml` overlay you enable only on a GPU instance.

### 5. Nginx reverse proxy + TLS
`infra/nginx/bhashai.conf` (template) proxies `/api` → api:3001 and `/` → web:3000, with
`client_max_body_size {{MAX_UPLOAD_MB}}m;` and long timeouts for upload. Then:
```bash
sudo cp infra/nginx/bhashai.conf /etc/nginx/sites-available/bhashai
sudo ln -s /etc/nginx/sites-available/bhashai /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d yourdomain.com           # or use Cloudflare proxy + origin cert
```
Large uploads should go **direct to S3 via presigned PUT** (api issues the URL), so Nginx isn't
in the upload path for big files — set `MAX_UPLOAD_MB` only as a guard for multipart fallback.

### 6. Health checks, logs, restart
- `GET /api/health` checks DB + Redis + S3; wire to an ALB/Cloudwatch or `docker healthcheck`.
- Compose: `restart: unless-stopped` on every service. Logs via `docker compose logs -f <svc>`
  shipped to CloudWatch agent (Phase 4).
- DB backups: nightly `pg_dump` to S3 (cron) + RDS migration path documented for scale.

## B. PM2 (no Docker) — alternative
For teams preferring PM2: install Node 24, pnpm, Postgres, Redis on the host; `pnpm install &&
pnpm build`; run `pm2 start infra/ecosystem.config.js` which defines `api`, `web`, and one
process per worker group. `pm2 save && pm2 startup` for boot persistence. Same `.env`.

## C. Scaling (Phase 4)
- Split the single `worker` into `translation-worker` (high concurrency, scale horizontally),
  `extraction-worker` (CPU/OCR-bound), `qa-worker`, `reconstruction-worker` via `WORKER_QUEUES`.
- Move Postgres → RDS, Redis → ElastiCache, run API/web behind an ALB, workers on an ASG.
- `indictrans-service` on a `g5.xlarge` GPU instance, pointed to by `INDICTRANS_SERVICE_URL`.
- Amazon Translate **async batch** (`StartTextTranslationJob`, S3 in/out, ≤5GB) for very large
  document collections instead of per-chunk calls — selected by the router for bulk jobs.

## Environment variables (`.env`)

| Variable | Required | Example / default | Used by |
| --- | --- | --- | --- |
| `DATABASE_URL` | yes | `postgresql://bhashai:pw@postgres:5432/bhashai` | api, worker, db |
| `REDIS_URL` | yes | `redis://redis:6379` | api, worker |
| `JWT_SECRET` | yes | `<random 32+ bytes>` | api |
| `AWS_REGION` | yes (cloud) | `ap-south-1` | storage, translate |
| `AWS_ACCESS_KEY_ID` | if no IAM role | — | storage, translate |
| `AWS_SECRET_ACCESS_KEY` | if no IAM role | — | storage, translate |
| `S3_BUCKET_RAW` | yes (cloud) | `bhashai-raw-prod` | storage |
| `S3_BUCKET_PROCESSED` | yes (cloud) | `bhashai-processed-prod` | storage |
| `STORAGE_DRIVER` | no | `s3` \| `local` (default `local` in dev) | storage |
| `OPENAI_API_KEY` | one LLM key | — | engines (LLM) |
| `ANTHROPIC_API_KEY` | one LLM key | — | engines (LLM) |
| `LLM_PROVIDER` | no | `anthropic` \| `openai` \| `gemini` | engines |
| `LLM_MODEL` | no | provider default | engines |
| `GOOGLE_TRANSLATE_CREDENTIALS` | if Google on | path to service-account JSON | engines |
| `AWS_TRANSLATE_ENABLED` | no | `false` | engine router |
| `GOOGLE_TRANSLATE_ENABLED` | no | `false` | engine router |
| `INDICTRANS_SERVICE_URL` | if IndicTrans on | `http://indictrans:8001` | engines |
| `PARSER_SERVICE_URL` | yes | `http://parser:8000` | parsing |
| `MAX_UPLOAD_MB` | no | `100` | api, nginx |
| `DEFAULT_TRANSLATION_ENGINE` | no | `LLM` | engine router |
| `ENABLE_OCR` | no | `false` \| `textract` \| `local` | parser |
| `ENABLE_LAYOUT_PRESERVATION` | no | `false` | reconstruct |
| `WORKER_QUEUES` | no | `*` (all) or CSV of queue names | worker |
| `WORKER_CONCURRENCY_TRANSLATION` | no | `4` | worker |
| `QA_PASS_THRESHOLD` | no | `70` | qa |
| `WEB_PUBLIC_API_URL` | yes | `https://yourdomain.com/api` | web |

`.env.example` in the repo lists every variable with safe defaults; dev runs with
`STORAGE_DRIVER=local`, `ENABLE_OCR=false`, Mock+LLM engines, no AWS needed.
