# LedgerGraph — Production Deployment Guide

This guide details how to deploy **LedgerGraph** to production. LedgerGraph is composed of four modular services:
1. **FalkorDB** (Graph database for multi-tenant isolation, graph traversal, and PageRank)
2. **Redis** (Session caching, rate limiting, and temporary queues)
3. **FastAPI Backend** (Deterministic tax math, OCR extraction, Cypher graph queries, audit trail)
4. **Next.js 14 Frontend** (CA Partner web console with responsive UI, live graph charts, and print views)

---

## Architecture Overview

```
                                [Internet / WhatsApp Webhook]
                                              │
                                              ▼
                             [Reverse Proxy: Nginx / Caddy]
                              (TLS Term, 80/443 -> 3000/8000)
                                     │                 │
                   ┌─────────────────┘                 └────────────────┐
                   ▼                                                    ▼
      [Next.js 14 Frontend]                                   [FastAPI Backend]
          (Port 3000)                                            (Port 8000)
                                                                       │
                                                       ┌───────────────┴───────────────┐
                                                       ▼                               ▼
                                              [FalkorDB Graph DB]                [Redis Cache]
                                                  (Port 6379)                     (Port 6379)
```

---

## Option 1: One-Command Docker Compose Deployment (Recommended for VPS / Cloud VM)

Recommended hardware:
* 2 vCPU, 4GB RAM minimum (AWS t3.medium, DigitalOcean Droplet, Hetzner CPX21).
* Ubuntu 22.04 / 24.04 LTS or Debian 12 with Docker & Docker Compose installed.

### Step 1: Clone Repository & Configure Environment
```bash
git clone https://github.com/Taran-G/gst-Easy.git
cd gst-Easy

# Copy production environment variables
cp .env.example .env
```

### Step 2: Edit `.env` with Your Production Keys
```ini
# Core Configuration
MODE=live
GEMINI_API_KEY=your_gemini_api_key_here
JWT_SECRET=generate_with_openssl_rand_hex_32

# Production Domain URLs
ALLOWED_ORIGINS=https://app.yourdomain.com,https://api.yourdomain.com

# Meta WhatsApp Cloud API (Optional - required for live incoming bills)
WHATSAPP_PHONE_NUMBER_ID=your_whatsapp_phone_number_id
WHATSAPP_ACCESS_TOKEN=your_whatsapp_access_token
WHATSAPP_VERIFY_TOKEN=your_custom_webhook_secret

# GST Suvidha Provider (Optional - mock fixtures used by default if empty)
GSP_BASE_URL=https://api.gsp.nic.in
GSP_CLIENT_ID=
GSP_CLIENT_SECRET=
GSP_AUTH_TOKEN=
```

### Step 3: Launch with Docker Compose
```bash
# Build and start all 4 services in the background
docker compose up -d --build

# Verify container health
docker compose ps
```

### Step 4: Seed Initial Admin & Demo Firm
```bash
# Execute seed inside the running API container
docker compose exec api python -m app.seed
```

### Step 5: Run Automated Production Smoke Verification
```bash
./scripts/smoke.sh
```
If you see `=== ALL SMOKE CHECKS PASSED SUCCESSFULLY ===`, all database graphs, auth mechanisms, audit chains, and tax calculation engines are fully operational.

---

## Option 2: Managed Cloud Deployment (Split Tier)

If deploying to serverless/managed platforms:

### 1. Database Tier: FalkorDB Cloud
1. Create a free or paid database at [FalkorDB Cloud](https://app.falkordb.cloud/).
2. Note your host, port, and password.
3. In your backend environment settings, configure:
   ```ini
   FALKORDB_HOST=your-cluster.falkordb.cloud
   FALKORDB_PORT=6379
   FALKORDB_PASSWORD=your_secure_password
   ```

### 2. Backend API Tier: Render / AWS ECS / Google Cloud Run
* **Runtime**: Docker or Python 3.11.
* **Build Command**: `pip install -r api/requirements.txt`
* **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
* **Root Directory**: `api/`
* **Health Check Path**: `/health`

### 3. Frontend Web Tier: Vercel / Netlify
* **Framework Preset**: Next.js
* **Root Directory**: `web/`
* **Build Command**: `npm run build`
* **Output Directory**: `.next`
* **Environment Variable**:
  * `NEXT_PUBLIC_API_URL`: `https://api.yourdomain.com/api/v1`

---

## Option 3: Production Systemd Service (Bare-Metal Ubuntu Server)

### 1. FalkorDB & Redis Systemd or Docker
```bash
docker run -d --name ledgergraph_falkordb -p 6379:6379 -v falkordb_data:/data --restart always falkordb/falkordb:latest
docker run -d --name ledgergraph_redis -p 6389:6379 --restart always redis:7-alpine
```

### 2. Backend Service (`/etc/systemd/system/ledgergraph-api.service`)
```ini
[Unit]
Description=LedgerGraph FastAPI Production Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/gstEasy
EnvironmentFile=/var/www/gstEasy/.env
ExecStart=/var/www/gstEasy/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 3. Frontend Service (`/etc/systemd/system/ledgergraph-web.service`)
```ini
[Unit]
Description=LedgerGraph Next.js 14 Production Web
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/gstEasy/web
Environment=NODE_ENV=production
Environment=PORT=3000
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ledgergraph-api ledgergraph-web
```

---

## Nginx Reverse Proxy & SSL Setup

Create `/etc/nginx/sites-available/ledgergraph`:
```nginx
# Web Frontend
server {
    server_name app.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}

# API Backend
server {
    server_name api.yourdomain.com;
    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable SSL via Certbot:
```bash
sudo certbot --nginx -d app.yourdomain.com -d api.yourdomain.com
```

---

## Default Production Credentials

After running `make seed` or `python -m app.seed`:
* **Web UI URL**: `https://app.yourdomain.com` (or `http://localhost:3000`)
* **CA Partner Login**: `partner@demo`
* **Default Password**: `partner123`
* **Pre-configured Tenants**:
  * **Apex Auto Parts** (`apex`): Intrastate auto manufacturing enterprise
  * **Greenleaf Traders** (`greenleaf`): Interstate FMCG distribution firm

---

## Operational Runbook

| Action | Command |
|---|---|
| Run full test suite (47 tests) | `make test` |
| Execute production smoke test | `make smoke` |
| Check API health | `curl http://localhost:8000/api/v1/health` |
| Backup FalkorDB data | `docker exec -it ledgergraph_falkordb redis-cli SAVE` |
| Inspect tamper-evident audit log | `curl -H "Authorization: Bearer <TOKEN>" -H "X-Tenant: apex" http://localhost:8000/api/v1/audit` |
| Export GSTR-2B reconciliation CSV | `curl -H "Authorization: Bearer <TOKEN>" -H "X-Tenant: apex" http://localhost:8000/api/v1/reconcile/092026/export-csv -o recon.csv` |
