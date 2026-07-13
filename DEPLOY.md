# Deploying the backend for free

Recommended free stack:

| Piece    | Service                         | Free?                                  |
| -------- | ------------------------------- | -------------------------------------- |
| API host | **Render** (Web Service)        | ✅ (sleeps after ~15 min idle)          |
| Database | **Neon** (serverless Postgres)  | ✅ persistent free tier                 |
| Media    | **Cloudinary**                  | ✅ (already configured)                 |

> Heads-up: the free API instance **spins down when idle**, so the first request
> after a nap takes ~30–60s to wake. Fine for a demo/portfolio. Hitting `GET /`
> wakes it.

---

## 1. Create a free Postgres (Neon)

1. Sign up at <https://neon.tech> → create a project.
2. Copy the **connection string** — it looks like:
   `postgresql://user:pass@ep-xxx-123.us-east-2.aws.neon.tech/neondb?sslmode=require`
3. Keep it for step 3 (this is your `DATABASE_URL`).

Tables are created automatically on first boot (`Base.metadata.create_all`), so
there's nothing to migrate.

## 2. Push the code to GitHub

Deploy from a Git repo. Make sure `.env` is **not** committed (it's gitignored).
Either push the whole monorepo or just the `server/` folder.

## 3. Deploy the API (Render)

**Option A — Blueprint (uses `render.yaml`):**
1. <https://dashboard.render.com> → **New +** → **Blueprint** → connect your repo.
2. Render reads `server/render.yaml` and creates the service.
3. Fill in the secret env vars when prompted (see the list below).

**Option B — Manual Web Service:**
1. **New +** → **Web Service** → connect your repo.
2. Settings:
   - **Root Directory:** `server`  (skip if the repo *is* the server folder)
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free
3. Add the environment variables below → **Create Web Service**.

### Environment variables to set in Render

| Key                       | Value                                             |
| ------------------------- | ------------------------------------------------- |
| `DATABASE_URL`            | the Neon connection string from step 1            |
| `STORAGE_BACKEND`         | `cloudinary`                                      |
| `CLOUDINARY_CLOUD_NAME`   | from your Cloudinary dashboard                     |
| `CLOUDINARY_API_KEY`      | from your Cloudinary dashboard                     |
| `CLOUDINARY_API_SECRET`   | from your Cloudinary dashboard                     |
| `JWT_SECRET`              | any long random string (Blueprint auto-generates) |

You'll get a public URL like `https://spotify-backend-xxxx.onrender.com`.
Verify it: opening that URL should return `{"status":"ok"}`.

## 4. Point the mobile app at it

In [`spotify-rn/src/constants/server.ts`](../spotify-rn/src/constants/server.ts)
set your Render URL as `PROD_API_URL`. Dev builds keep using localhost; release
builds use the live server automatically.

---

## Other free hosts (same code)

A `Dockerfile` and `Procfile` are included, so the app also runs on:

- **Koyeb** — free web service; reads the `Dockerfile`.
- **Fly.io** — `fly launch` (Dockerfile); small free allowance.
- **Hugging Face Spaces** — Docker Space, great for a permanent free demo.
- **Railway** — reads the `Procfile` (trial credit, not fully free anymore).

For the database on any of these, Neon works everywhere via `DATABASE_URL`.
