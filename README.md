# The Signal

A once-a-day briefing on what changed in the world, with a Frontiers section on AI and science, a markets strip, a pulse check on every region, and running forecasts with a public track record.

Live site: https://prototypeversions.github.io/TheSignal/

## How it works

- **Editions** (`data/editions/YYYY-MM-DD.json`): one per day, about ten world stories, three to six Frontiers items (AI and science), a markets strip, and a seven-region pulse.
- **Threads** (`data/threads/*.json`): each story belongs to a situation we keep following. Thread pages show the full timeline, built from the editions.
- **Forecasts** (`data/forecasts.json`): yes/no questions with exact resolution rules. History is append-only; resolved questions are scored.
- **Build** (`scripts/build.py`): standard-library Python that validates the data and writes the static site to `docs/`, which GitHub Pages serves.
- **Design** (`site/`): stylesheet and favicon, copied into `docs/assets/`.

Each morning a scheduled Claude task follows [`EDITOR.md`](EDITOR.md): research, write the edition, update threads and forecasts, validate, build, and push.

## Running locally

```
python3 scripts/build.py --check   # validate only
python3 scripts/build.py           # validate and build docs/
python3 -m http.server -d docs     # preview at http://localhost:8000
```

Edit data and design files, not `docs/`; it is regenerated on every build.
