# Morning Brief

A personal, fully-automated daily podcast. Every morning at 5:30 AM Gulf Standard Time, GitHub Actions:

1. Pulls Al Jazeera top stories, market data for a configured ticker list, and any new episodes from a configured podcast list
2. Sends the brief to GPT-4o-mini, which writes a ~10-minute two-host script
3. Renders the script through OpenAI TTS (two distinct voices), stitches it into a single mp3
4. Pushes the new mp3 and an updated RSS feed to GitHub Pages

Spotify (or any podcast app) subscribes to the RSS feed and the new episode appears in your library before your commute.

---

## One-time setup

You'll do this **once**, takes about 10 minutes total.

### 1. Create the GitHub repo

1. Go to https://github.com/new
2. Repository name: `morning-brief`
3. Set it to **Public** (required for the free GitHub Pages tier to host the mp3s; the URL is obscure, no one will find it)
4. Do **not** initialize with a README — we'll push our own
5. Click **Create repository**

### 2. Upload these files to the repo

Easiest path — drag and drop:

1. On the empty repo page, click **uploading an existing file** in the quick-setup block
2. Drag the entire contents of this folder (the project root, not the folder itself) into the browser
3. **Important:** make sure `.github/workflows/daily.yml` makes it up. GitHub's drag-drop sometimes misses dotfile folders — verify after upload by browsing to `.github/workflows/` in the repo
4. **Important:** do NOT upload `.env` — it has your API key. The included `.gitignore` excludes it, but the web upload doesn't respect gitignore. Delete `.env` from the upload before dragging, or delete it from the repo immediately after
5. Commit message: "Initial setup", then **Commit changes**

If you have git installed locally, the alternative is:

```bash
cd morning-brief
git init
git remote add origin https://github.com/irmoiz/morning-brief.git
git add -A
git commit -m "Initial setup"
git branch -M main
git push -u origin main
```

### 3. Add the OpenAI API key as a repo secret

1. In the repo, click **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `OPENAI_API_KEY`
4. Value: paste your OpenAI key (the one saved in your local `.env`)
5. Click **Add secret**

The daily workflow reads this at runtime — the key never gets committed to the repo.

### 4. Enable GitHub Pages

1. **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, folder: `/docs`
4. **Save**

Wait ~1 minute for the first deploy. Your feed will then be available at:

```
https://irmoiz.github.io/morning-brief/feed.xml
```

You can also visit `https://irmoiz.github.io/morning-brief/cover.png` to verify the cover art is up.

### 5. Run the workflow once to produce the first episode

The cron only fires at 5:30 AM GST, so for the first episode we trigger it manually:

1. Repo → **Actions** tab
2. Click **Daily Morning Brief** in the left sidebar
3. Click **Run workflow** → **Run workflow** (green button)
4. Wait ~3–5 minutes; you'll see a green check when done
5. Verify: the feed should now show one episode at `https://irmoiz.github.io/morning-brief/feed.xml`

### 6. Submit the feed to Spotify

Spotify is the only major podcast app that doesn't subscribe to RSS URLs directly inside the listening app — instead, you tell their podcaster portal about your feed once, and they poll it for new episodes.

1. Go to https://podcasters.spotify.com → **Get started** → **I have a podcast**
2. Paste your feed URL: `https://irmoiz.github.io/morning-brief/feed.xml`
3. Spotify will email a verification code to the address in the feed (`mkprods@gmail.com` per your `settings.json`). Paste the code back.
4. Fill in basic info (most of it auto-fills from the feed)
5. Submit. Spotify usually approves within a few hours
6. Once approved, open Spotify on your phone, search for **"Morning Brief"** (or the title you set), and follow. Episodes will appear automatically going forward.

> Tip: Spotify polls the RSS feed every ~1 hour. The pipeline is scheduled at 5:30 AM GST so episodes are reliably indexed in Spotify by your 7:30 commute.

---

## Daily life

Nothing. The workflow runs on its own at 5:30 AM GST every day. You'll see a new episode in Spotify each morning.

You can also trigger an extra run any time via **Actions** → **Daily Morning Brief** → **Run workflow**.

---

## Customizing

All config lives in `config/`:

- **`tickers.json`** — list of stock symbols to cover in the markets segment. Edit and commit.
- **`podcasts.json`** — list of podcasts to monitor for new-episode summaries. Edit and commit. RSS feeds are auto-discovered by show name; set `"rss"` explicitly to lock to a specific URL.
- **`settings.json`** — voice choices, host names, target length, podcast metadata, cron schedule.

To change the schedule, edit `cron_utc` in `settings.json` **and** the cron line in `.github/workflows/daily.yml` (the YAML cron is what GitHub actually reads).

To change voices, edit `voice_host_1` and `voice_host_2` in `settings.json`. Available OpenAI voices: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`.

---

## Testing locally (optional)

If you want to run the pipeline on your own machine for testing:

```bash
cd morning-brief
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...   # your key
python src/run_daily.py
```

This runs the full pipeline but the publish step will try to `git push` — set `PODCAST_BASE_URL` to a local path and comment out the publish step in `run_daily.py` if you just want to test the audio.

---

## Troubleshooting

**The Action ran but no episode appeared in Spotify.**
- Check the Actions tab for errors. The most common failure is the OpenAI key being rejected or rate-limited.
- Spotify polls every ~1 hour. Wait, then refresh the show page.

**The Action fails on `git push`.**
- This means the repo doesn't have write permissions configured for Actions. Go to Settings → Actions → General → Workflow permissions and select **Read and write permissions**.

**Audio sounds robotic / too fast.**
- Try `tts-1-hd` instead of `tts-1` (already the default in `settings.json`).
- Tweak `speaking_rate` in `settings.json` (1.0 is normal; 0.95 is slightly slower).

**Episodes are too long / too short.**
- Adjust `target_words` in `settings.json`. Roughly 140 words per minute.

---

## Security note

The `.env` file in this folder contains your OpenAI key. It's already in `.gitignore` so it should never be committed, but **rotate the key once final setup is done** (delete it from platform.openai.com → API keys, create a fresh one, update the GitHub repo secret + your local `.env`) — because the key was shared in chat during setup and that chat is logged.
