# Remoto — Car Refurbishment Platform

Premium doorstep car refurbishment booking website built with Next.js 14, Supabase, and Tailwind CSS.

---

## Stack

- **Frontend:** Next.js 14 (App Router) + TypeScript + Tailwind CSS
- **Backend / Auth / DB:** Supabase
- **Hosting:** Vercel

---

## Local Setup (Step by Step)

### 1. Install dependencies

```bash
npm install
```

### 2. Set up Supabase

1. Go to [supabase.com](https://supabase.com) → New Project
2. Name it `remoto`, pick region `ap-south-1 (Mumbai)`, set a DB password
3. Wait for the project to spin up (~2 min)
4. Go to **SQL Editor** → paste the entire contents of `supabase_setup.sql` → Run
5. Go to **Settings → API** → copy:
   - Project URL
   - `anon` public key

### 3. Add environment variables

Edit `.env.local`:

```
NEXT_PUBLIC_SUPABASE_URL=https://your-project-id.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key-here
```

### 4. Configure Supabase Auth

In Supabase dashboard → **Authentication → URL Configuration**:
- Site URL: `http://localhost:3000` (for local dev)
- After deploying: update to your Vercel URL

### 5. Run locally

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

---

## Pages

| Route | Description |
|---|---|
| `/` | Landing page with hero, services strip, how-it-works |
| `/services` | All refurbishment services with pricing |
| `/book/[serviceId]` | Booking form (auth required) |
| `/confirmation` | Booking confirmed screen |
| `/auth` | Login / Signup |

---

## Deploy to Vercel

### Option A — Via CLI (fastest)

```bash
npm install -g vercel
vercel
```

Follow the prompts. When asked about environment variables, add:
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

Deploy to production:
```bash
vercel --prod
```

### Option B — Via GitHub (recommended for ongoing)

1. Push this repo to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/remoto.git
   git push -u origin main
   ```

2. Go to [vercel.com](https://vercel.com) → Import Project → select your repo

3. In **Environment Variables**, add:
   - `NEXT_PUBLIC_SUPABASE_URL` = your Supabase URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = your Supabase anon key

4. Click **Deploy**

### After deploying: Update Supabase Auth URL

Go to Supabase → **Authentication → URL Configuration**:
- **Site URL:** `https://your-app.vercel.app`
- **Redirect URLs:** `https://your-app.vercel.app/**`

---

## Supabase Schema Reference

### `services` table
Seeded automatically by `supabase_setup.sql`. Contains 6 refurbishment services.

### `bookings` table
Created when a user submits the booking form. Row Level Security ensures users only see their own bookings.

---

## Submission Checklist

- [x] Frontend UI — polished multi-page Next.js app
- [x] Backend logic — Supabase DB with bookings + services tables
- [x] Supabase Auth — email login/signup on `/auth`
- [x] Hosted URL — deploy to Vercel and submit the live URL

---

## Project by
Masters' Union TBM Program — Option A Product Website
