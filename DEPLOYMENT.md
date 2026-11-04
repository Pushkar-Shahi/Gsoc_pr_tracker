# Issue-to-PR Platform: Production Deployment & Operations Runbook

This guide covers everything required to deploy, configure, scale, and maintain the **Issue-to-PR Platform** in a production cloud environment.

---

## 1. Production Architecture Overview

The platform is designed to be **operationally lean and cloud-native**:
- **Unified Single Container**: The multi-stage [`Dockerfile`](file:///Users/shahi/Desktop/PROJECT/issue-to-pr-platform/Dockerfile) compiles the React frontend into static assets and packages them directly into a Python 3.12 slim runtime. FastAPI serves both the REST API and the React SPA on `$PORT`, eliminating CORS and separate frontend hosting bills.
- **Unprivileged Runtime**: Runs under system user `appuser` (UID 10001) for strict container security.
- **Dynamic Database Normalization**: Translates `postgres://` or `postgresql://` connection strings from Render, Railway, Supabase, Neon, or AWS RDS to `postgresql+asyncpg://` automatically.
- **Graceful Fault Tolerance**: Falls back cleanly to local Git worktrees if Docker is absent, in-memory queues if Redis is offline, and cached high-value bounties if Polar.sh API is unreachable.

```
                     +---------------------------------------+
                     |         Internet / End Users          |
                     +---------------------------------------+
                                         |
                                         v
                     +---------------------------------------+
                     |  Cloud Host (Render / Railway / Fly)  |
                     |  Single Multi-Stage Docker Container  |
                     |  +---------------------------------+  |
                     |  | Port $PORT (Default 8000)       |  |
                     |  | - React Web SPA (/app/dist)     |  |
                     |  | - FastAPI API Gateway (/api/v1) |  |
                     |  | - Preflight Engine & SSE Stream |  |
                     |  +---------------------------------+  |
                     +---------------------------------------+
                                |                 |
            +-------------------+                 +-------------------+
            v                                                         v
+-----------------------+                                 +-----------------------+
|  Managed PostgreSQL   |                                 |  Distributed Runner   |
|  (Orgs, Tasks, Subs)  |                                 |  (Local/Cloud Daemon) |
+-----------------------+                                 +-----------------------+
```

---

## 2. Deployment Options

### Option A: Deploy on Render (Recommended Blueprint)
Render automatically provisions a managed PostgreSQL database and builds the container via Infrastructure-as-Code:

1. Push your repository to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com), click **New +** &rarr; **Blueprint**.
3. Select your repository. Render will automatically detect [`render.yaml`](file:///Users/shahi/Desktop/PROJECT/issue-to-pr-platform/render.yaml).
4. Fill in the required environment variables:
   - `SECRET_KEY`: Generate via `openssl rand -hex 32`.
   - `GITHUB_CLIENT_ID` & `GITHUB_CLIENT_SECRET`: From your GitHub App.
   - `STRIPE_SECRET_KEY` & `STRIPE_WEBHOOK_SECRET`: From your Stripe Dashboard.
5. Click **Apply**. Render will automatically build the image, run database migrations, and deploy the application.

---

### Option B: Deploy on Railway
Railway provides zero-config Docker builds and instant Postgres add-ons:

1. Install the Railway CLI or use the web dashboard at [railway.app](https://railway.app).
2. Create a new project and add a **PostgreSQL** database service.
3. Link your GitHub repository. Railway detects [`railway.toml`](file:///Users/shahi/Desktop/PROJECT/issue-to-pr-platform/railway.toml) and [`Dockerfile`](file:///Users/shahi/Desktop/PROJECT/issue-to-pr-platform/Dockerfile).
4. Under **Variables**, attach the database reference:
   ```env
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   SECRET_KEY=replace_with_openssl_rand_hex_32
   ENVIRONMENT=production
   ```
5. Deploy. The healthcheck probe (`/api/health`) will verify readiness before routing traffic.

---

### Option C: Deploy on Fly.io
Fly.io runs applications globally close to users on lightweight micro-VMs:

1. Authenticate with the Fly CLI:
   ```bash
   fly auth login
   ```
2. Launch the application using the included [`fly.toml`](file:///Users/shahi/Desktop/PROJECT/issue-to-pr-platform/fly.toml):
   ```bash
   fly launch --no-deploy
   ```
3. Create a managed Postgres cluster on Fly:
   ```bash
   fly postgres create --name issuetopr-db
   fly postgres attach issuetopr-db
   ```
4. Set production secrets:
   ```bash
   fly secrets set SECRET_KEY=$(openssl rand -hex 32) \
                   ENVIRONMENT=production \
                   STRIPE_SECRET_KEY=sk_live_... \
                   GITHUB_CLIENT_ID=... \
                   GITHUB_CLIENT_SECRET=...
   ```
5. Deploy:
   ```bash
   fly deploy
   ```

---

### Option D: Self-Hosted Production with Docker Compose
For on-premises Linux servers or AWS EC2 / DigitalOcean Droplets:

1. Clone the repository onto your host server:
   ```bash
   git clone https://github.com/Pushkar-Shahi/Gsoc_pr_tracker.git /opt/issuetopr
   cd /opt/issuetopr
   ```
2. Copy the production environment template:
   ```bash
   cp .env.production.example .env
   nano .env # Set your real domain, SECRET_KEY, and Stripe/GitHub credentials
   ```
3. Start the stack in detached mode:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```
4. Verify services are healthy:
   ```bash
   docker compose -f docker-compose.prod.yml ps
   curl -i http://localhost:8000/api/health
   ```

---

## 3. Preflight Health Verification Tooling

Before launching or after applying updates, run the automated preflight validator:

```bash
# Direct shell execution
./scripts/deploy_check.sh

# Or via Python module
PYTHONPATH=backend python3 backend/app/core/preflight.py
```

The preflight engine verifies:
- PostgreSQL database connectivity and automatic schema migrations.
- `SECRET_KEY` entropy and production suitability.
- Persistent storage volume read/write permissions.
- Stripe API configuration and webhook signature readiness.
- GitHub OAuth and fallback token accessibility.
- Queue service backend (Redis vs in-memory fallback) and sandbox provider routing.

---

## 4. Production Third-Party Service Setup

### 1. GitHub App & OAuth Setup
1. Navigate to **GitHub Settings** &rarr; **Developer Settings** &rarr; **GitHub Apps** &rarr; **New GitHub App**.
2. **Homepage URL**: `https://your-domain.com`
3. **User authorization callback URL**: `https://your-domain.com/api/v1/auth/github/callback`
4. **Webhook URL**: `https://your-domain.com/api/v1/webhooks/github`
5. **Webhook Secret**: Generate a 32-character string and set as `GITHUB_WEBHOOK_SECRET`.
6. **Repository Permissions**:
   - Issues: *Read & write*
   - Pull requests: *Read & write*
   - Checks & Commit statuses: *Read-only*
   - Contents: *Read & write*
7. **Subscribe to events**:
   - `Issues`
   - `Pull request`
   - `Pull request review`
   - `Check run`

### 2. Stripe Live Mode Setup
1. In the [Stripe Dashboard](https://dashboard.stripe.com), toggle to **Live mode**.
2. Copy your **Secret key** (`sk_live_...`) &rarr; `STRIPE_SECRET_KEY`.
3. Copy your **Publishable key** (`pk_live_...`) &rarr; `STRIPE_PUBLISHABLE_KEY`.
4. Go to **Developers** &rarr; **Webhooks** &rarr; **Add endpoint**:
   - URL: `https://your-domain.com/api/v1/billing/webhook`
   - Events:
     - `checkout.session.completed`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
5. Copy the **Signing secret** (`whsec_...`) &rarr; `STRIPE_WEBHOOK_SECRET`.
6. Create your subscription products (**Pro Developer** $29/mo, **Engineering Team** $79/seat/mo) and set their Price IDs in your environment.

### 3. Polar.sh Bounty Hunter Setup
1. Go to [polar.sh/settings](https://polar.sh/settings) &rarr; **Personal Access Tokens**.
2. Generate a token with read permissions &rarr; set as `POLAR_ACCESS_TOKEN`.
3. If omitted, the platform uses its built-in catalog of verified high-value bounties ($250 to $1,500 across top open-source projects).

---

## 5. Backup & Disaster Recovery

### Automated PostgreSQL Backup
Create a daily cron job to backup the database:
```bash
pg_dump -Fc --no-acl --no-owner -h <db-host> -U <db-user> issuetopr > /backups/issuetopr_$(date +%Y%m%d_%H%M%S).dump
```

### Database Restore
To restore from a backup snapshot:
```bash
pg_restore --clean --if-exists -h <db-host> -U <db-user> -d issuetopr /backups/issuetopr_YYYYMMDD_HHMMSS.dump
```

---

## 6. Upgrades & Zero-Downtime Rollouts

When updating the platform:
1. Pull latest code or build new container image:
   ```bash
   git pull origin main
   ```
2. Run preflight check:
   ```bash
   ./scripts/deploy_check.sh
   ```
3. Restart container:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --no-deps --build web
   ```
   *FastAPI and the preflight script handle database column migrations automatically on boot.*

