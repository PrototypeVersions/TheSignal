# The Signal — daily editor's runbook

This file is the complete instruction set for The Signal. Two scheduled tasks follow it each day:

- **Morning edition** (about 5:53am Central): sections 0–9 below, producing the day's edition.
- **Evening update** (about 5:52pm Central): section 10, which updates that same edition with what changed since morning.

A person can follow it too.

The Signal answers one question each morning: **what changed in the world since the last edition that changes our picture of it?** It is not a summary of all the news.

---

## 0. Setup

1. Make sure the repository `PrototypeVersions/TheSignal` is cloned and current:
   - If it is not present, attach it with push access and clone it.
   - `git pull --rebase origin main`
2. Work out today's date in **America/Chicago**. That is the edition date.
3. If `data/editions/<today>.json` already exists:
   - on a **morning** run, stop: today's edition is done. Report that and end.
   - on an **evening** run, go to section 10.
   If it does not exist on an evening run (the morning run failed), produce a full edition by following sections 1–9, and say in `launch_note` that today's edition was published in the evening.
4. Read, in full:
   - the latest edition in `data/editions/` (and skim the one before it); use it as the format reference,
   - every file in `data/threads/`.

## 1. Research (the bulk of the work)

Use web search and fetch the actual articles. Only cite pages you actually opened and read. Aim for 25–40 searches; use the extended search mode for anything recent.

Cover, in this order:

1. **Every active thread.** For each, find what happened since the last edition. Most threads will have something; many will not have anything that changes the picture.
2. **New developments** that are not yet threads. Sweep world headlines from wire services and major outlets (AP, Reuters, AFP, BBC, Al Jazeera, NPR, Guardian, FT, WSJ, Bloomberg) for the past 24–36 hours.
3. **Every region**: North America, Latin America, Europe, Africa, Middle East, Asia, Oceania. Search each one explicitly so quiet regions are judged, not forgotten.
4. **Frontiers — AI**: frontier labs (Anthropic, OpenAI, Google DeepMind, Meta, xAI, DeepSeek and others), model releases, safety and security research, AI science results, regulation, major money and compute deals, labor-market evidence.
5. **Frontiers — science**: major results in science, medicine (pivotal trial results, major approvals), space, energy and climate. Check Nature, Science, NEJM, The Lancet, NASA, ESA, the FDA and EMA, and science desks (AP, Reuters, Nature News, Science News, STAT).
6. **Regional extras**: for each region, one to three developments that matter but will not be main stories (they become that region's `briefs`, section 3).

Prefer original reporting and official sources over aggregators. When figures disagree between sources, use the most recent figure from a named, credible source and say that figures differ.

## 2. Choose the edition

- **World stories: 8–12.** Pick by how much the picture changed, not by how loud the coverage is. A big story with nothing new today can be left out.
- **Frontiers: 3–6.** Usually 3–4 AI items plus 0–2 from science, medicine, space, energy or climate, but only when something truly clears the bar. Never add a science item to fill space. When no science item qualifies, say so in `frontier_note` and, if useful, name a coming result worth watching. Skip routine product updates and incremental studies.
- **Frontier stories can lead.** If an AI or science development is the single biggest change of the day, put it first in `stories` (as a world story with `why` and `watch`, without `places`) instead of in `frontiers`. Use this rarely.
- Each story belongs to exactly one thread. If a story starts a new thread, create `data/threads/<id>.json` (see section 5).
- Never use the same thread twice in one edition.
- Order world stories by importance of the change, biggest first. The order sets the front page: story 1 is the large lead with a big map, stories 2–3 sit side by side with maps, and the rest form the "More that changed" list. Put the day's single most important change first.

### Change labels (pick one)

| value | meaning |
|---|---|
| `major` | Our understanding changed substantially since the last edition. Use sparingly: usually 1–4 per edition. |
| `new` | A situation that matters and that we were not following before. |
| `developing` | Real movement, but in the direction already expected. |
| `quiet` | Important but little changed. Normally leave these out of the edition and mention them in the pulse. |

## 3. Write

### How stories appear

The front page is short on purpose. Each story shows its labels, headline and `dek` (the lead story also shows `why`), with a **Full report** or **Read the full story** link to the story's own page. That page carries everything else: the map or illustration, any evening updates, `key_facts`, the full `report`, `why` and `watch`, and every source. So the `dek` must stand on its own, and the `report` must be a complete article.

### Format of each world story

```json
{
  "thread": "thread-id",
  "change": "major|new|developing|quiet",
  "headline": "Sentence case, specific, under ~80 characters",
  "dek": "One or two sentences (under ~40 words) with the single most important new fact. Shown on the front page.",
  "key_facts": ["Three to five short, sourced facts a reader could quote: numbers, dates, names."],
  "report": [
    {"heading": "What happened", "paragraphs": ["...", "..."]},
    {"heading": "Background", "paragraphs": ["..."]},
    {"heading": "What comes next", "paragraphs": ["..."]}
  ],
  "why": "Why this change matters, in one to three sentences.",
  "watch": "What would tell us where this goes next. Concrete events or dates.",
  "sources": [{"outlet": "AP via ABC News", "title": "Article title", "url": "https://..."}],
  "places": {
    "countries": ["FRA"],
    "related": ["DEU"],
    "points": [{"name": "Paris", "lat": 48.86, "lon": 2.35}],
    "view": [-6, 41, 10, 52]
  }
}
```

**`report` is the full story** and is required for every world and Frontiers item. Write two to five sections, about 300–500 words in total (shorter only when the sourced facts genuinely run out; never pad). Typical headings: what happened, the response, background or context, what comes next. Do not add a section called "Why it matters"; `why` already appears beside the report. Every sentence must be supported by a listed source, so research enough to write it properly: open the main articles and at least one background source.

**`places` draws the story's locator map. Every world story should have one.**
- `countries`: the main country or countries, as ISO 3166 alpha-3 codes (FRA, UKR, USA, KEN…). Drawn highlighted.
- `related`: optional, other countries directly involved, drawn lighter (for example RUS on a story about strikes inside Ukraine, IRN behind the Houthis).
- `points`: two to four key cities or sites with accurate coordinates. The first point is drawn largest. Avoid two points so close that their labels overlap.
- `view`: optional framing box `[west longitude, south latitude, east longitude, north latitude]`. Leave it out for most stories; the map frames the countries and points automatically. Set it when a country is huge or has far-off territories (Russia, the US, Canada, France with overseas territories) or when the story is about one small area.
- The West Bank is `PSE`. Codes the map does not know will fail the build check; use a neighboring country or just points instead.
- Frontier items have no map.

### Frontier items (`frontiers` list)

Same shape as world stories, but with `field`, `picture` and `image` instead of `why`, `watch` and `places`:

```json
{
  "thread": "thread-id",
  "field": "AI|Science|Medicine|Space|Energy|Climate",
  "change": "...",
  "headline": "...", "dek": "...", "key_facts": ["..."], "report": [...],
  "picture": "One to three sentences on why it matters. Shown as 'Why it matters' on the story page. Keep it proportionate: say plainly when something is a modest step.",
  "image": {"asset": "images/YYYY-MM-DD/<thread-id>.svg", "alt": "What the picture shows and how it connects to the story.", "credit": "Illustration"},
  "sources": [...]
}
```

On the front page Frontiers items look like the "More that changed" list: picture, labels, headline, `dek` and a "Read the full story" link. See section 4 for the illustrations.

Optional `frontier_note` (one or two sentences, shown under the section) with `frontier_note_sources`.

### Writing rules

- Lead with what is **new since the last edition**. Use "Saturday", "on 17 October" etc. rather than vague "recently".
- `dek`: one or two sentences, the single most important new fact. `report`: the full story, about 300–500 words in sections. Concrete numbers, names, places, dates.
- **Paraphrase everything.** Do not copy sentences from sources. Quotes only when the exact words matter, under 15 words, at most one per source. Never reproduce song lyrics or poems.
- Attribute disputed claims ("Russia says…", "according to the Interior Ministry…"). Present competing accounts side by side when they conflict.
- Neutral on politics: describe positions and evidence, do not take sides. No loaded adjectives.
- No graphic detail of violence. No personal information about private individuals beyond what a story needs.
- Plain words, active voice, British or American spelling consistently within an edition (the launch edition uses mostly British forms like "organizers", "center").
- Every story needs at least one source; important or surprising claims need two independent ones.

### The rest of the edition

- `number`: previous edition's number + 1.
- `published_at`: current time as ISO 8601 with offset.
- `lede`: one paragraph, 3–5 sentences, that tells a busy reader the day in one breath.
- `launch_note`: omit (it was for edition 1 only), unless something about this edition is unusual and readers should know (for example a missed day).
- `pulse`: exactly seven entries, one per region (`North America`, `Latin America`, `Europe`, `Africa`, `Middle East`, `Asia`, `Oceania`). Together they drive the front page's region map and the seven region pages.
  - `status` is `moved` or `quiet`; `text` is a two- or three-sentence summary of the region today. When nothing cleared the bar, say "No development cleared our bar today."
  - `threads` lists thread ids mentioned. A story appears under a region when its thread's `region` matches, or when its thread is listed here (use this for stories that span regions, for example a US decision about Russia).
  - `briefs`: one to three extra developments that are not main stories, each `{"headline": "...", "text": "One or two sentences.", "change": "new", "sources": [...]}`. Rate `change` exactly as for a main story; they feed the At a glance bar, which counts every story on the map. Open and read every source; prefer the last 48 hours; do not repeat a main story. Leave the list empty when nothing qualifies; the site says so. Never pad.
  - `sources` supports any fact in `text` that is not already sourced in a story or brief.
- `corrections`: usually empty. See section 6.

Save as `data/editions/<YYYY-MM-DD>.json`.

## 4. Illustrations for Frontiers

Every Frontiers item gets a simple original illustration, saved as `images/<YYYY-MM-DD>/<thread-id>.svg` and referenced in its `image` field.

- Before drawing, write down in one sentence the concrete thing from the story the picture shows: an object, place, mechanism or action a reader would recognise from the headline (a chip and a falling price line for chip stocks sliding; a pie with one slice lifted toward a hard hat for a share fund for displaced workers; a path going around a barrier for AI agents getting past their controls). If you cannot name one, use a different concrete element of the story; never a generic robot, brain or abstract swirl.
- Hand-write a self-contained SVG, 1200×800 (`viewBox="0 0 1200 800"`), with shapes and paths only: no text, logos, real people, scripts, external images or fonts. Keep it under 50 KB.
- Use the site's palette: background `#0B1422`–`#16243D`, panels `#1A2943`/`#23365A`, lines `#2F4163`, blue `#86A2FF`, coral `#FF8B7B`, and at most one warm accent such as `#E9B44C`.
- One strong subject, quiet space around it. Check the result against the headline: someone seeing only the picture and the headline should see the connection.

## 5. Threads (`data/threads/<id>.json`)

```json
{
  "id": "kebab-case-id",
  "title": "Short title",
  "short": "1–2 word label for the trace",
  "section": "world|frontier",
  "region": "North America|Latin America|Europe|Africa|Middle East|Asia|Oceania|Frontiers",
  "started": "YYYY-MM-DD or YYYY-MM",
  "started_label": "Human-readable start, e.g. 17 October 2026",
  "status": "active|dormant|closed",
  "summary": "Two or three sentences on where things stand now.",
  "background": [{"date": "YYYY-MM-DD", "text": "Key event before we started following."}]
}
```

- Update `summary` whenever a story in the thread changes the picture. Keep it current, not a history.
- Set `status` to `dormant` after 14 days without a story, and `closed` when the situation is over (an election decided, an outbreak declared over).
- The thread's timeline is built automatically from editions; don't copy stories into the thread file.

## 6. Corrections

If research shows an earlier edition got something wrong, add an entry to **that** edition's `corrections` list: `{"date": "<today>", "text": "We said X. In fact Y, according to Z."}`. Fix the wrong sentence in that edition too. Mention significant corrections in today's lede only if they change the picture.

## 7. Check before publishing

1. Re-read every story against its sources. Delete or rewrite any sentence you cannot point to a source for. Check every number twice.
2. Check that nothing is copied word-for-word from a source beyond a short attributed quote.
3. Run `python3 scripts/build.py --check` and fix every error it reports.
4. Run `python3 scripts/build.py` to regenerate `docs/`.
5. Open `docs/index.html` and skim it: correct date, all sections present, every map shows the right place.

## 8. Publish

```
git add -A
git commit -m "Edition <N>: <YYYY-MM-DD>"
git push origin main
```

If the push is rejected, `git pull --rebase origin main`, rebuild, and push again. GitHub Pages serves `docs/` from `main`; the site updates within a few minutes.

## 9. Report

Finish with a short message: the edition number and date, the three biggest changes, anything you could not verify and left out, and any problem the owner should know about.

## 10. Evening update

The evening update keeps the morning edition current. It does **not** create a second edition and does not rewrite the morning's work. Readers should be able to see what is new since morning at a glance.

1. Read today's edition and its threads.
2. Research what happened since the morning edition was published (`published_at`), with the same care as section 1: every story in today's edition, every scheduled event named in a "What to watch", and a sweep of world and frontier headlines for anything major and new.
3. For each story where something material happened, append an entry to that story's `updates` list:
   ```json
   "updates": [{"at": "2026-10-18T17:55:00-05:00", "text": "One to three sentences on what changed since this morning.", "sources": [{"outlet": "...", "title": "...", "url": "https://..."}]}]
   ```
   - Do not edit the morning's headline, dek, report, why or watch, except to fix an outright error (then also add a correction, section 6). The update block is where the new information goes; the front page shows an "Updated" tag on the story and the update itself appears on the story's page, after "Why it matters".
   - Leave `change` as it was.
   - Skip stories where nothing material happened. Most evenings, only a few stories get updates.
4. If something **major and new** happened that is not in the edition, you may add up to two new stories (world or frontier) in the full normal format (including `key_facts`, `report`, and for Frontiers an illustration), and a new thread if needed. Put a world story where its importance belongs in the order; moving it to first place makes it the lead.
5. Add a region brief (in `pulse`) for any major regional development that does not warrant a main story, and refresh a region's `text` if its picture changed.
6. Rewrite the `lede` only if the day's picture changed; otherwise leave it.
7. Set `"updated_at"` on the edition to the current time (ISO 8601 with offset). The site shows "Updated 5:55pm CT".
8. Check (section 7), build, and publish with the commit message `Edition <N> evening update: <YYYY-MM-DD>`.
9. Report: which stories got updates, any new stories, and anything left out because it could not be verified.

If nothing material happened since morning, still set `updated_at`, and say so in the report.

