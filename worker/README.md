# Sophie proxy — deploy runbook

This tiny Cloudflare Worker is what makes Sophie (the chat assistant on the site)
a real Claude-powered assistant instead of a keyword matcher. It holds your
Anthropic API key as a **secret** and sits between the website and Claude.

**Why this exists:** the website is static (GitHub Pages). A static page cannot
hold an API key — anyone can read the page source and steal it, and bots would
drain your Anthropic balance overnight. This Worker is the *only* place the key
lives. You paste the key into your own terminal once; it never goes in the repo,
the page, or anywhere public.

Total time: ~15 minutes. Everything below is free (Cloudflare Workers free tier).

---

## What you'll need

1. A **Cloudflare account** (free) — https://dash.cloudflare.com/sign-up
2. An **Anthropic API key** — https://console.anthropic.com → *API Keys* →
   *Create Key*. **Make a dedicated key just for this Worker** so it's easy to
   cap and revoke.

---

## ⚠️ Two things are REQUIRED before Sophie goes live

The Worker **fails closed**: until you bind the rate limiter (step 3), it returns
a 503 and Sophie simply keeps using her offline brain. This is on purpose — an
unthrottled public proxy on your key is how people get surprise bills. So:

- **A. Rate limiter (step 3 below).** Caps any single visitor/bot to 10 msgs/min,
  120/day.
- **B. An Anthropic monthly spend cap (step 6 below).** The ultimate backstop —
  even in a worst case, spend can't exceed the ceiling you set.

Do both. Then flip it live.

---

## Deploy — step by step

Run these from inside this `worker/` folder:

```bash
cd worker

# 1. Log in to Cloudflare (opens your browser once)
npx wrangler login

# 2. Store your Anthropic key as an encrypted secret.
#    It prompts you to paste the key. Paste it, hit enter.
#    (This is the ONLY place your key goes. Never share it with anyone.)
npx wrangler secret put ANTHROPIC_API_KEY

# 3. Create the rate-limiter store (REQUIRED — the Worker won't serve without it)
npx wrangler kv namespace create SOPHIE_RL
```

Step 3 prints something like `id = "abc123..."`. Open **`wrangler.toml`**,
uncomment the three `[[kv_namespaces]]` lines, and paste that id. Then:

```bash
# 4. Deploy
npx wrangler deploy
```

The deploy prints a URL like:

```
https://sophie-proxy.YOUR-SUBDOMAIN.workers.dev
```

**Copy that URL** — that's Sophie's brain endpoint.

```bash
# 5. Sanity check — should say  api_key=set  rate_limiter=on
curl https://sophie-proxy.YOUR-SUBDOMAIN.workers.dev
```

If it says `rate_limiter=MISSING`, redo step 3 / the `wrangler.toml` edit.

**6. Set the Anthropic spend cap (REQUIRED).** In https://console.anthropic.com →
*Settings → Limits*, set a monthly spend limit + a usage alert on the key you made.
This is your hard ceiling.

---

## Connect the website to the proxy

1. Open `docs/index.html`, search for `SOPHIE_API`.
2. Paste your Worker URL between the quotes:

   ```js
   var SOPHIE_API = "https://sophie-proxy.YOUR-SUBDOMAIN.workers.dev";
   ```

3. Commit and push. Within a minute or two, Sophie on the live site answers with Claude.

**Until you paste the URL, Sophie runs on her built-in offline brain** (the keyword
answers) — so the site is never broken while you set this up. If the proxy is ever
down, rate-limited, or slow, she automatically falls back to that offline brain too.

---

## Tuning

All in `src/index.js` at the top:

- **`MODEL`** — defaults to `claude-sonnet-5` (smart + reasonable cost). For the
  sharpest answers use `claude-opus-4-8`; to minimize cost use
  `claude-haiku-4-5-20251001` (still very capable for a support bot).
- **`MAX_TOKENS`** — cap on each reply length (and therefore cost per reply).
- **`MAX_PER_MIN` / `MAX_PER_DAY`** — the per-IP throttle.
- **`ALLOWED_ORIGINS`** — the only sites allowed to call the proxy in a browser.
- **`SYSTEM_PROMPT`** — Sophie's personality, the company facts, and her guardrails.
  Edit this to change what she knows or how she talks, then redeploy.

Redeploy after any change: `npx wrangler deploy`.

### Escape hatch (not recommended)

To run without the KV rate limiter (e.g. you added a Cloudflare edge Rate-Limiting
rule instead), set `REQUIRE_RL="false"` as a Worker variable in `wrangler.toml`
`[vars]`. Only do this if you have *another* throttle in place.

## Watch it live / debug

```bash
npx wrangler tail    # streams live request logs (no message content is logged)
```

## Cost, honestly

Each answer is a few hundred output tokens. On Sonnet that's a fraction of a cent
per message. Realistic small-site traffic runs a few dollars a month. The rate
limiter caps abuse per visitor, and the Anthropic monthly spend limit is the hard
ceiling regardless.
