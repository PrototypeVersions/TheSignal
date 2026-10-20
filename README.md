# The Signal

A daily briefing on what changed in the world, with a Frontiers section on AI and science, an at-a-glance strip and a map of every region. The front page stays short; every story has its own page with a full report, key facts and sources.

Live site: https://prototypeversions.github.io/TheSignal/

## How it works

- **Editions** (`data/editions/YYYY-MM-DD.json`): one per day, about ten world stories, three to six Frontiers items (AI and science), and a seven-region pulse with extra regional news. Every story carries a short `dek` for the front page and a full `report` for its own page.
- **Threads** (`data/threads/*.json`): each story belongs to a situation we keep following. Thread pages show the full timeline, built from the editions.
- **Illustrations** (`images/YYYY-MM-DD/*.svg`): simple original pictures for Frontiers items.
- **Build** (`scripts/build.py`): standard-library Python that validates the data and writes the static site to `docs/`, which GitHub Pages serves. It creates the front page, a page per story (`editions/<date>/<thread>/`), a page per region (`regions/<region>/`), thread pages, the archive and the feed.
- **Design** (`site/`): stylesheet, script and favicon, copied into `docs/assets/`.

Each morning a scheduled Claude task follows [`EDITOR.md`](EDITOR.md): research, write the edition, update threads, validate, build, and push.

## Running locally

```
python3 scripts/build.py --check   # validate only
python3 scripts/build.py           # validate and build docs/
python3 -m http.server -d docs     # preview at http://localhost:8000
```

Edit data and design files, not `docs/`; it is regenerated on every build.
