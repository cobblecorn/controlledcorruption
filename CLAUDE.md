# CLAUDE.md — guidance for AI agents & contributors

Controlled ROM Corruptor: a deterministic, region-aware ROM/binary corruption
framework. This file orients you fast. Read `docs/ARCHITECTURE.md` for depth.

## Setup / build / test

```bash
pip install -e '.[dev]'      # editable install + pytest
python -m pytest -q          # run all tests (should be all green)
ccorrupt demo demo.z64       # write the synthetic demo ROM to try things
```

GUI (optional): `pip install -e '.[gui]'` then `ccorrupt-gui`. The GUI is
PySide6; in a headless environment run tests under `QT_QPA_PLATFORM=offscreen`.

## Non-negotiable invariants (there are tests for each — keep them green)

1. **Determinism** — same input + regions + settings + seed ⇒ byte-identical
   output. Consume the PRNG (`core/prng.py`) in a fixed order; never use
   Python's `random`. Bump `PRNG_VERSION` if the stream must change.
2. **Bounds** — no byte outside the effective mutable area may change.
3. **Protection** — protected regions always override targets.
4. **Source immutability** — never mutate the caller's input bytes; work on a
   copy.
5. **No ROM bytes in project/seed files** — only hashes + offsets.
6. **Never overwrite the source** unless the user explicitly forces it.

## Architecture in one breath

Keep three concerns separate: **WHERE** (regions) / **WHAT** (categories,
`data_type`) / **HOW** (mutation strategies). The engine (`core/`) is
game-agnostic. Platform knowledge lives in `platforms/` (small classes), game
knowledge in `profiles/` (JSON data). CLI and GUI both call
`core/pipeline.py`, so they never diverge.

Key modules: `core/engine.py` (mutation loop), `core/prng.py`, `core/regions.py`
(interval math), `core/project.py` (.ccproject layers + .ccseed),
`core/semantic.py` (Level-3 vertex ops), `core/evolve.py`, `core/fuzz.py`,
`core/analysis.py` + `core/hexview.py` (RE tools).

## Extending (each is one file, no engine edits)

- **Mutation strategy**: subclass `Mutation` in `core/mutations/`, register in
  its `__init__.py`, add to `ALL_TYPES` in `core/settings.py`.
- **Platform**: subclass `PlatformAdapter` in `platforms/`, register in its
  `__init__.py`. Put checksum logic in `repair_checksum` — never in the engine.
  `detect()` returns confidence in [0,1]; only positive-confidence adapters win.
- **Game profile**: add JSON to `profiles/`, keyed by SHA-256. No code.

## Conventions

- Keep the core dependency-free (stdlib only). PySide6/PyYAML are optional.
- Prefer adding a test alongside any behaviour change; mirror existing tests.
- Offsets: `end` is exclusive everywhere.
- Don't fabricate real game hashes/offsets in committed profiles; mark
  templates clearly (see `profiles/n64/example-n64.json`).
