# Deploying the Jute Sliver Analyzer (Supabase + Render)

This covers everything from unzipping the project to having it live on the
internet, with your data and photos stored in Supabase instead of on Render's
disk (which gets wiped on every redeploy).

---

## 1. Extract the zip

1. Download `juteapp_supabase.zip`.
2. Unzip it anywhere on your computer. You should see:
   ```
   juteapp_extracted/
     server.py
     requirements.txt
     Procfile
     .env.example
     public/
       dashboard.html, batches.html, login.html, ... etc
     migrate.py            (only relevant for the old desktop/SQLite version — ignore for web deploy)
     BUILD_INSTRUCTIONS.txt, JuteSliverAnalyzer.spec, build.bat   (only for the Windows .exe build — ignore for web deploy)
   ```
3. Rename the folder to whatever you want your GitHub repo to be called, e.g. `jute-sliver-analyzer`.

---

## 2. Set up Supabase (database + photo storage)

### 2a. Create the project
1. Go to [supabase.com](https://supabase.com) → sign up / log in → **New project**.
2. Pick an organization, name the project, set a database password (**save this password somewhere** — you'll need it in step 2c), choose a region close to you, and create it.
3. Wait ~2 minutes for it to finish provisioning.

### 2b. Create a storage bucket (for photos)
1. In the left sidebar, click **Storage**.
2. Click **New bucket**.
3. Name it exactly `jute-uploads` (or any name — just remember it).
4. Toggle **Public bucket** to ON. This lets the app link directly to photos without extra auth plumbing.
5. Click **Create bucket**.

### 2c. Get your connection string (DATABASE_URL)
1. Left sidebar → **Project Settings** (gear icon) → **Database**.
2. Under **Connection string**, choose the **URI** tab.
3. Copy it — it looks like:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxx.supabase.co:5432/postgres
   ```
4. Replace `[YOUR-PASSWORD]` with the database password from step 2a.
5. Save this full string somewhere — this is your `DATABASE_URL`.

> If your Supabase project offers a "Session pooler" / "Transaction pooler" connection string too, either works — the direct connection string above is simplest to start with.

### 2d. Get your API keys
1. Left sidebar → **Project Settings** → **API**.
2. Copy the **Project URL** (e.g. `https://xxxxxxxxxxxx.supabase.co`) — this is your `SUPABASE_URL`.
3. Copy the **`service_role`** key (NOT the `anon` key — the service_role key is required for the app to upload/delete photos). This is your `SUPABASE_SERVICE_KEY`.

**Keep the service_role key private.** Never put it in frontend code or commit it to GitHub — it goes into Render's environment variables only (step 4).

You should now have four values saved somewhere:
```
DATABASE_URL=postgresql://postgres:...@db...supabase.co:5432/postgres
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...(long string)
SUPABASE_BUCKET=jute-uploads
```

---

## 3. Push the project to GitHub

If you don't already have Git installed, get it from [git-scm.com](https://git-scm.com).

1. Go to [github.com](https://github.com) → **New repository**. Name it (e.g. `jute-sliver-analyzer`), keep it **Private** if you don't want it public, don't initialize with a README (you already have files).
2. Open a terminal in your unzipped project folder and run:
   ```bash
   cd path/to/juteapp_extracted
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/jute-sliver-analyzer.git
   git push -u origin main
   ```
3. Refresh your GitHub repo page — you should see all the files there.

> Double check `.env.example` got committed but you never create/commit a real `.env` file with actual secrets in it. Real secrets only go into Render's environment settings (next step).

---

## 4. Deploy on Render

1. Go to [render.com](https://render.com) → sign up / log in (you can sign in with GitHub directly).
2. Click **New +** → **Web Service**.
3. Connect your GitHub account if you haven't, then select your `jute-sliver-analyzer` repo.
4. Fill in the settings:
   - **Name:** anything, e.g. `jute-sliver-analyzer`
   - **Region:** any
   - **Branch:** `main`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn server:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
     (this matches the `Procfile`, so Render may auto-fill it for you)
   - **Instance Type:** Free (or paid, if you want it to not spin down when idle)
5. Scroll to **Environment Variables** and add these four, using the values you saved in step 2:
   | Key | Value |
   |---|---|
   | `DATABASE_URL` | your Supabase connection string |
   | `SUPABASE_URL` | your Supabase project URL |
   | `SUPABASE_SERVICE_KEY` | your service_role key |
   | `SUPABASE_BUCKET` | `jute-uploads` |
6. Click **Create Web Service**.
7. Watch the **Logs** tab. First deploy takes a few minutes (installing Pillow etc.). You're looking for something like:
   ```
   Booting worker with pid: ...
   ```
   with no tracebacks above it.
8. Once it says **Live**, open the URL Render gives you (e.g. `https://jute-sliver-analyzer.onrender.com`). You should land on the login page.

---

## 5. Verify it actually works

1. Log in with any name (this app uses simple name-based sessions, no password).
2. Create a batch, then upload a sliver photo as a sample.
3. Go back to Supabase → **Storage** → your `jute-uploads` bucket — you should see the uploaded file appear there.
4. Go to Supabase → **Table Editor** → `samples` table — you should see a new row with `image_path` set to a full `https://...supabase.co/storage/...` URL.
5. Redeploy the service on Render (or just wait for it to spin down and wake back up on the free tier) and confirm your batch/sample is still there — this is the part that used to break with local SQLite + local disk storage.

---

## Troubleshooting

- **Deploy fails at build step, missing package** → check `requirements.txt` was committed and Render's Build Command is `pip install -r requirements.txt`.
- **App crashes on boot with a `DATABASE_URL is not set` error** → environment variable wasn't saved correctly on Render; recheck step 4.5, then trigger **Manual Deploy → Deploy latest commit**.
- **Photos don't load (broken image icons)** → confirm the bucket is set to **Public** (step 2b) and `SUPABASE_BUCKET` matches the bucket name exactly.
- **"password authentication failed" in logs** → the password in `DATABASE_URL` doesn't match your Supabase database password; regenerate it under Project Settings → Database if needed, and update the Render env var.
- **Uploads fail with a 401/403** → double check you copied the `service_role` key, not the `anon` key, into `SUPABASE_SERVICE_KEY`.
