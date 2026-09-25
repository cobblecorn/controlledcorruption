# Architecture

The guiding rule is a strict separation of three concerns:

```
WHERE corruption occurs   ->  Region        (core/regions.py)
WHAT the data represents  ->  category / data_type on a Region
HOW the data is mutated   ->  Mutation strategy (core/mutations/*)
```

The **engine** never contains game-specific or platform-specific logic. Game
knowledge lives in **profiles** (data), platform knowledge lives in **platform
adapters** (small classes). This is what lets support grow by adding files
rather than editing the engine.

## Layers

```
controlled_corruptor/
├── core/                     # game-agnostic engine
│   ├── prng.py               # deterministic xoshiro256** PRNG (versioned)
│   ├── binary.py             # load/hash/safe-write; original never modified
│   ├── regions.py            # Region model + interval arithmetic
│   ├── settings.py           # MutationSettings (density, magnitude, types…)
│   ├── history.py            # MutationRecord / MutationLog
│   ├── mutations/            # strategy classes + registry
│   ├── engine.py             # effective-area computation + mutation loop
│   ├── validation.py         # PASS/WARNING/FAIL reports (advisory)
│   ├── diff.py               # differential analysis
│   ├── pipeline.py           # ties platform+profile+engine (CLI & GUI share)
│   └── project.py            # .ccproject / .ccseed + non-destructive layers
├── platforms/                # Generic, N64 (+ registry & detection)
├── profiles/                 # profile schema + loader (JSON/YAML by hash)
├── emulator/                 # launch abstraction + custom-command adapter
├── cli/                      # argparse front-end
├── ui/                       # optional PySide6 desktop UI
└── demo.py                   # synthetic demo ROM generator
```

## Determinism

`Rng` implements SplitMix64-seeded **xoshiro256\*\***, fully specified so it can
be reimplemented in another language. Seeds (string or int) fold through
SHA-256. The version string `ccprng-1` is stored in every project/seed; the
engine refuses to run a project made with a different PRNG version, so old
corruptions stay reproducible when the algorithm evolves.

Given the same input bytes + regions + settings + seed, the output is
**byte-identical**. Strategies must consume the PRNG in a fixed order.

## The mutation loop

`Engine.run`:

1. Build the **target** interval set (from regions filtered by category, and/or
   raw `target_intervals`).
2. Build the **protected** interval set (platform + profile + user).
3. `effective = merge(targets) - protected`  → protection always wins.
4. `num_ops = round(density * mutable_bytes)`.
5. For each op: pick a strategy (weighted), which picks a legal offset via
   `_SpanPicker` (guaranteed inside one effective interval) and mutates a
   private copy, logging a `MutationRecord`.

`_SpanPicker` counts legal start positions across all intervals and picks
uniformly, so multi-byte mutations never straddle a protected/boundary edge.

## Non-destructive mutation stack

A `.ccproject` holds an ordered list of `Layer`s. Output is always rebuilt as
`original + enabled layers`, applied in order onto a running buffer. Toggling a
layer off simply regenerates without it — no cumulative accidental corruption.
Region offsets are size-stable, so they are gathered from the original binary
while the engine runs on the running buffer.

## Extending

### Add a mutation strategy

```python
# core/mutations/my_op.py
from .base import Mutation, MutationContext

class MyOp(Mutation):
    name = "my_op"
    def apply(self, ctx, index):
        off = ctx.pick_span(4)          # legal, in-bounds offset (or None)
        if off is None:
            return None
        old = ctx.out[off]
        ctx.out[off] = (old + 1) & 0xFF
        return ctx.make_record(index, "my_op", off, size=1,
                               before=str(old), after=str(ctx.out[off]))
```

Register it in `core/mutations/__init__.py` (add to `ALL_TYPES` in
`settings.py` to expose it in the UI/CLI).

### Add a platform adapter

Implement `PlatformAdapter` (`platforms/base.py`): `detect`, `endianness`,
`protected_regions`, optional `known_regions`, `repair_checksum`, `validate`.
Register it in `platforms/__init__.py`. `detect` returns a confidence in
`[0,1]`; only positive-confidence adapters are eligible, and `priority` breaks
ties. Checksum logic belongs **here**, exposed as `repair_checksum`, never in
the engine (see N64's CIC implementation for a full example).

This is the path for PS1/PS2/GameCube/Wii/GBA/DS/PSP and the
PlayStation/Xbox disc formats: each is one new file. Until an adapter exists a
file still works in Generic mode.

### Add a game profile

Data only — a JSON/YAML file identified by SHA-256. See
`profiles/n64/example-n64.json`. No code changes needed.

### Add an emulator

The custom-command adapter (`emulator/custom.py`) covers most emulators via a
`{ROM}` template. Add a dedicated subclass only if you need process
inspection / crash detection beyond exit codes.

## Testing invariants

`tests/` enforces the properties the whole design depends on:

- **Determinism** — same inputs ⇒ identical bytes and identical log.
- **Bounds** — no byte outside the effective mutable area ever changes.
- **Protection** — protected bytes are never touched, even when a target
  overlaps them.
- **Source immutability** — the input buffer is never mutated in place.
- **Serialization** — projects/seeds round-trip; `apply` == direct `corrupt`.
