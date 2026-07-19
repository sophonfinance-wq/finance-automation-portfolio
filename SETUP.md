# sophonfinance.com — go-live checklist

Two features are built and shipped but **switched off until you flip them on** with
your own accounts. The site works fine in the meantime (Sophie uses her offline
brain; the booking modal shows the email form). Turn them on when ready.

---

## 1. Sophie's live AI brain (Claude)

Sophie currently answers from a built-in keyword brain. To make her a real
Claude-powered assistant, deploy the tiny proxy that holds your Anthropic key as a
secret. **Full step-by-step in [`worker/README.md`](worker/README.md).** Short version:

```bash
cd worker
npx wrangler login
npx wrangler secret put ANTHROPIC_API_KEY      # you paste your key — nobody else sees it
npx wrangler kv namespace create SOPHIE_RL     # REQUIRED (rate limiter); paste the id into wrangler.toml
npx wrangler deploy                            # prints your Worker URL
```

Then set a **monthly spend cap** on the key in the Anthropic Console, and paste the
Worker URL into `docs/index.html`:

```js
var SOPHIE_API = "https://sophie-proxy.YOUR-SUBDOMAIN.workers.dev";
```

Commit + push. If the proxy is ever down, Sophie auto-falls-back to the offline brain.

---

## 2. Live call booking (Google Calendar + Google Meet)

Visitors can self-book **30-minute** or **60-minute** calls straight from your live
calendar, and Google adds a **Google Meet** link automatically. Set it up once:

### A. Create the two appointment schedules

1. Open **Google Calendar** (calendar.google.com) signed in as
   **sophonfinance@gmail.com**.
2. Click **Create → Appointment schedule** (or the gear → *Appointment schedules*).
3. First schedule:
   - **Title:** `30-minute intro call`
   - **Appointment duration:** 30 minutes
   - **General availability:** set the hours/days you want to take calls, plus any
     buffer time, max bookings per day, and how far ahead people can book.
   - **Booking form / Where:** choose **Google Meet video conferencing** as the
     location so every booking gets a Meet link. (You can also allow phone; visitors
     can note a preference in the booking form.)
   - Save.
4. Repeat for a second schedule titled `60-minute working session`, duration **60 min**.

### B. Copy each booking link

On each schedule, click **Share → Embed** (or *Share* → copy the booking page link).
Copy the **URL** for each. Prefer the long
`https://calendar.google.com/calendar/appointments/schedules/...` URL — it embeds
cleanly inside the site's booking window.

### C. Paste the URLs into the site

In `docs/index.html`, find `BOOK30` / `BOOK60` (in the booking-modal script):

```js
var BOOK30 = "https://calendar.google.com/calendar/appointments/schedules/AAA...";
var BOOK60 = "https://calendar.google.com/calendar/appointments/schedules/BBB...";
```

Commit + push. Now every "Book a free consultation" button opens a chooser:
**30-min intro** or **60-min working session** → your live calendar grid → the
visitor picks a slot → Google books it and emails both of you a Meet link.

**Notes**
- Leave either variable blank to hide that duration. Leave *both* blank and the modal
  just shows the email form (the current behavior) — nothing breaks.
- The email form is always available via *"Prefer we email you instead?"*, and it
  still routes to `contact@sophonfinance.com` via FormSubmit with the auto-reply.
- If a pasted URL ever shows blank in the embed, the built-in **"Open the booking page
  in a new tab"** link is right there as a fallback.
