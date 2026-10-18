# The Signal — daily editor's runbook

This file is the complete instruction set for producing one edition. The daily scheduled task follows it from top to bottom. A person can follow it too.

The Signal answers one question each morning: **what changed in the world since the last edition that changes our picture of it?** It is not a summary of all the news.

---

## 0. Setup

1. Make sure the repository `PrototypeVersions/TheSignal` is cloned and current:
   - If it is not present, attach it with push access and clone it.
   - `git pull --rebase origin main`
2. Work out today's date in **America/Chicago**. That is the edition date.
3. If `data/editions/<today>.json` already exists, stop: today's edition is done. Report that and end.
4. Read, in full:
   - the latest edition in `data/editions/` (and skim the one before it),
   - every file in `data/threads/`,
   - `data/forecasts.json`.

## 1. Research (the bulk of the work)

Use web search and fetch the actual articles. Only cite pages you actually opened and read. Aim for 25–40 searches; use the extended search mode for anything recent.

Cover, in this order:

1. **Every active thread.** For each, find what happened since the last edition. Most threads will have something; many will not have anything that changes the picture.
2. **New developments** that are not yet threads. Sweep world headlines from wire services and major outlets (AP, Reuters, AFP, BBC, Al Jazeera, NPR, Guardian, FT, WSJ, Bloomberg) for the past 24–36 hours.
3. **Every region**: North America, Latin America, Europe, Africa, Middle East, Asia, Oceania. Search each one explicitly so quiet regions are judged, not forgotten.
4. **AI frontier**: frontier labs (Anthropic, OpenAI, Google DeepMind, Meta, xAI, DeepSeek and others), model releases, safety and security research, AI science results, regulation, major money and compute deals, labor-market evidence.
5. **Forecast evidence**: anything bearing on each open forecast, and whether any forecast has resolved.
6. **Markets and economy** where they moved meaningfully (oil, major indices, central banks, key data releases).

Prefer original reporting and official sources over aggregators. When figures disagree between sources, use the most recent figure from a named, credible source and say that figures differ.

## 2. Choose the edition

- **World stories: 8–12.** Pick by how much the picture changed, not by how loud the coverage is. A big story with nothing new today can be left out.
- **AI frontier: 3–5.** Only items that could change where AI is heading. Skip routine product updates.
- Each story belongs to exactly one thread. If a story starts a new thread, create `data/threads/<id>.json` (see section 5).
- Never use the same thread twice in one edition.
- Order world stories by importance of the change, biggest first. The order sets the front page: story 1 is the large lead with a big map, stories 2–3 sit side by side, and the rest form a compact list. Put the day's single most important change first.

### Change labels (pick one)

| value | meaning |
|---|---|
| `major` | Our understanding changed substantially since the last edition. Use sparingly: usually 1–4 per edition. |
| `new` | A situation that matters and that we were not following before. |
| `developing` | Real movement, but in the direction already expected. |
| `quiet` | Important but little changed. Normally leave these out of the edition and mention them in the pulse. |

### Momentum (pick one)

| value | meaning |
|---|---|
| `up` | Intensifying: escalating, spreading, accelerating, or rising in stakes. |
| `steady` | Holding: no clear direction change. |
| `down` | Easing: de-escalating, contained, resolved or fading. |

Judge momentum against the previous entry in the same thread. Do not keep a thread at `up` out of habit.

## 3. Write

### Format of each world story

```json
{
  "thread": "thread-id",
  "change": "major|new|developing|quiet",
  "momentum": "up|steady|down",
  "headline": "Sentence case, specific, under ~80 characters",
  "dek": "One or two sentences with the single most important new fact.",
  "body": ["Paragraph one.", "Optional paragraph two."],
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

**`places` draws the story's locator map. Every world story should have one.**
- `countries`: the main country or countries, as ISO 3166 alpha-3 codes (FRA, UKR, USA, KEN…). Drawn highlighted.
- `related`: optional, other countries directly involved, drawn lighter (for example RUS on a story about strikes inside Ukraine, IRN behind the Houthis).
- `points`: two to four key cities or sites with accurate coordinates. The first point is drawn largest. Avoid two points so close that their labels overlap.
- `view`: optional framing box `[west longitude, south latitude, east longitude, north latitude]`. Leave it out for most stories; the map frames the countries and points automatically. Set it when a country is huge or has far-off territories (Russia, the US, Canada, France with overseas territories) or when the story is about one small area.
- The West Bank is `PSE`. Codes the map does not know will fail the build check; use a neighboring country or just points instead.
- AI frontier items have no map.

AI frontier items use the same shape but replace `why` and `watch` with `picture`: one to three sentences completing "This changes the picture because…".

### Writing rules

- Lead with what is **new since the last edition**. Use "Saturday", "on 17 October" etc. rather than vague "recently".
- Body: one or two short paragraphs, about 60–140 words in total. Concrete numbers, names, places, dates.
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
- `pulse`: exactly seven entries, one per region (`North America`, `Latin America`, `Europe`, `Africa`, `Middle East`, `Asia`, `Oceania`). `status` is `moved` or `quiet`. When nothing cleared the bar, say "No development cleared our bar today." `threads` lists thread ids mentioned; `sources` supports any fact that is not already sourced in a story.
- `forecast_notes`: one entry per forecast you moved or resolved: `{"id": "...", "from": 12, "to": 18, "why": "..."}`.
- `corrections`: usually empty. See section 6.

Save as `data/editions/<YYYY-MM-DD>.json`.

## 4. Forecasts (`data/forecasts.json`)

- Keep **6–10 open forecasts** at any time, spread across regions and including at least one AI question.
- **Never edit or delete an existing history entry.** Only append.
- Append `{"date": "<today>", "p": <1–99>, "note": "<why it moved>"}` only when the evidence moved your estimate. A move of 1–2 points is noise; don't log it.
- Resolving: when a question's outcome is known, set `"status": "resolved"`, `"resolution": "yes"|"no"|"void"`, `"resolved_on": "<date>"`, and `"resolution_note"` with the evidence and a source URL. Leave the history alone. The site scores resolved forecasts automatically.
- New forecasts need: a question with a clear yes/no answer, exact resolution criteria naming the authority that decides it, a close date, an `opened` date, related `threads`, and a first history entry with reasoning.
- Calibrate honestly. Look at base rates. Do not drift toward 50% to avoid being wrong, and do not chase the day's headlines.

## 5. Threads (`data/threads/<id>.json`)

```json
{
  "id": "kebab-case-id",
  "title": "Short title",
  "short": "1–2 word label for the trace",
  "section": "world|ai",
  "region": "North America|Latin America|Europe|Africa|Middle East|Asia|Oceania|AI",
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

Finish with a short message: the edition number and date, the three biggest changes, any forecast moves or resolutions, anything you could not verify and left out, and any problem the owner should know about.
