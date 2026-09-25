# Controlled ROM Corruptor

A **deterministic, region-aware** ROM / binary corruption framework.

Instead of "flip random bytes and hope the ROM boots", this tool corrupts
*specific* things (character models, animations, textures, maps, audio, …)
inside *specific* regions, reproducibly from a seed, while protecting headers,
boot code and checksums. It is built as a small, game-agnostic **mutation
engine** plus extensible **platform adapters** and **game profiles** — so
support grows by adding data files, not by rewriting the program.

> It sits somewhere between a ROM corruptor, a binary editor, and a
> game-data experimentation toolkit.

## Status

MVP is complete and tested (72 tests). Working today:

- ✅ Generic corruption of any binary file
- ✅ Deterministic, versioned seeds (identical output every time)
- ✅ Region targeting + protected regions (protection always wins)
- ✅ Categories (models / animations / textures / maps / audio / …)
- ✅ Mutation intensity split into **density** and **magnitude**
- ✅ Mutation history / log
- ✅ Non-destructive mutation stack (layers) — toggle a layer, regenerate
- ✅ Save / load projects (`.ccproject`) and shareable recipes (`.ccseed`)
- ✅ CLI **and** desktop GUI (they share one core)
- ✅ Platform adapters: Generic, **Nintendo 64**, **GBA**, **Nintendo DS**
  (each header-aware, with checksum/CRC repair)
- ✅ External JSON/YAML game profiles (+ an example + a runnable demo)
- ✅ Emulator launcher (custom command with `{ROM}`)
- ✅ Differential analysis (turn a modded ROM into regions)
- ✅ Semantic model/vertex corruption (Level 3: scale/mirror/flatten/… by axis)
- ✅ Reverse-engineering helpers (hex viewer, search, strings, entropy, scan)
- ✅ Batch generation across seeds + guided-fuzz region sweep (emulator-agnostic)

The original file is **never** modified, and project files never store ROM
contents — only hashes and offsets.

## Install

```bash
pip install -e .            # core + CLI
pip install -e '.[gui]'     # + PySide6 desktop UI
pip install -e '.[yaml]'    # + YAML profile support
```

Python 3.9+. No required third-party dependencies for the core/CLI.

## Quick start (no ROM needed)

The tool ships a synthetic **demo ROM** so you can try the whole pipeline
without any copyrighted file:

```bash
ccorrupt demo demo.z64                 # write the synthetic demo ROM
ccorrupt info demo.z64                 # hashes, platform, matched profile
ccorrupt corrupt demo.z64 \
    --target models \                  # corrupt only the "models" category
    --seed CODY-3491281 \
    --density 0.01 --magnitude 0.5 \
    -o demo_corrupt.z64 \
    --save-project demo.ccproject      # save a reproducible project
ccorrupt diff demo.z64 demo_corrupt.z64   # confirm what changed
ccorrupt apply demo.ccproject demo.z64 -o again.z64   # reproduce it exactly
```

Re-running `corrupt` with the same seed/settings produces a **byte-identical**
file. `apply` reproduces the same output from the saved project.

### Real ROMs

```bash
ccorrupt info game.z64                 # get the SHA-256
# ...add a profile keyed to that hash (see profiles/n64/example-n64.json)...
ccorrupt corrupt game.z64 --target models --target animations \
    --seed CODY-3491281 --intensity 0.4 -o game_corrupt.z64 \
    --launch "retroarch -L mupen64plus_libretro.so {ROM}"
```

### Generic mode (any binary, no profile)

```bash
ccorrupt corrupt data.pak --range 0x500000:0x900000 \
    --type float32 --type byte_replace --seed 12345 -o data_c.pak
```

### Semantic model corruption (Level 3)

When a region is a float32 vertex/animation array, corrupt it *coherently*
instead of with random noise — scale/stretch/mirror/flatten/displace/reverse
per axis, preserving topology (index data is never touched):

```bash
# stretch the "Character Models" region on Y only, leaving X/Z intact
ccorrupt model game.z64 --region "Character Models" \
    --op scale -x 0.0 -y 2.0 -z 0.0 --seed CODY -o game_tall.z64
# or a raw range with an explicit element stride
ccorrupt model data.bin --range 0x1000:0x5000 --stride 12 --op mirror -x 1 --seed 1
```

### Reverse-engineering helpers

```bash
ccorrupt hex game.z64 --offset 0x40000 --interpret   # int/float/pointer views
ccorrupt search game.z64 --float 1.0 --tol 0.01      # find float values
ccorrupt strings game.z64 --min-len 6
ccorrupt entropy game.z64                            # entropy sparkline
ccorrupt scan game.z64                               # experimental structure guesses
```

## Desktop GUI

```bash
ccorrupt-gui           # or: python -m controlled_corruptor.ui.app
```

Open a ROM, tick categories, set density/magnitude/seed, click **Generate**,
inspect the ROM map and mutation history, then **Save Corrupted As…**. The GUI
calls the exact same core APIs as the CLI, so results match.

## Concepts

The whole design keeps three things separate:

| Concept | Answers | Lives in |
|--------|---------|----------|
| **WHERE** corruption happens | which bytes | Regions |
| **WHAT** the data represents | models? floats? | Categories / `data_type` |
| **HOW** the data is mutated | flip? scale? swap? | Mutation strategies |

Three levels of knowledge:

1. **Generic** — works on any binary (bytes/bits/ints/floats/blocks).
2. **Platform-aware** — headers, endianness, protected regions, checksums
   (Generic, N64 today).
3. **Game-aware** — external profiles mark known regions by ROM hash.

**Intensity** is deliberately two knobs: `density` (how many mutations) and
`magnitude` (how hard each one hits), so you can do "few huge changes" or
"many tiny changes".

## Mutation types

`byte_replace`, `bit_flip`, `byte_offset`, `int16`, `int32`, `float32`
(multiply / add / sign-flip / replace, NaN-safe), `block_swap`, `block_repeat`,
`block_shift`. Add your own by registering a strategy — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Adding a game profile

Profiles are plain JSON identified by ROM hash (never filename):

```json
{
  "id": "my-game",
  "name": "My Game (US)",
  "platform": "n64",
  "identification": { "sha256": ["<from `ccorrupt info`>"] },
  "regions": [
    { "name": "Character Models", "category": "models",
      "start": "0x01738000", "end": "0x018A4000",
      "endianness": "big", "data_type": "float32" }
  ]
}
```

Drop it in `profiles/`, `~/.config/ccorrupt/profiles/`, or a directory named in
`$CCORRUPT_PROFILES`. See `profiles/n64/example-n64.json`.

## Consoles & roadmap

Working platform adapters:

| Adapter | Detects | Protects | Checksum repair |
|---------|---------|----------|-----------------|
| `n64` | Nintendo 64 (z64/v64/n64) | header + boot | ✅ CIC CRC |
| `gba` | Game Boy Advance | 192-byte header | ✅ header byte |
| `nds` | Nintendo DS | 0x200 header | ✅ CRC-16 |
| `gamecube` | GameCube disc | disc header | — |
| `wii` | Wii disc | disc header (warns on partitions) | — |
| `iso9660` | ISO discs (PS1/PS2/PSP images) | 16-sector system area | — |
| `psx-exe` | PlayStation executable | PS-X EXE header | — |
| `xex` | **Xbox 360** executable (XEX2) | header | — |
| `xbe` | **Original Xbox** executable (XBEH) | header | — |
| `generic` | anything | nothing (user-marked only) | — |

Everything not listed still works **today in Generic mode** (open the file, set
ranges/regions). Adding structure awareness for a new format is a single file
implementing `PlatformAdapter` — see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

Roadmap: deeper disc awareness (PS2/PSP filesystem + per-partition Wii hashes,
Xbox XISO/XDVDFS, PS3/PS4 PKG), so corruption can target individual on-disc
files and repair per-section integrity fields.

Longer term (see the handoff design): visual ROM map editing, hex viewer with
type interpretation, semantic model/animation/texture corruption, guided
fuzzing with crash heat maps, and mutation evolution.

## Development

```bash
pip install -e '.[dev]'
python -m pytest -q          # 72 tests: determinism, bounds, protection,
                             # immutability, serialization, platforms, CLI
```

Tested invariants: **determinism**, **bounds** (nothing changes outside the
mutable area), **protection** (protected bytes never change), **source
immutability** (the input buffer is never touched), and **serialization**
round-trips.

## Safety & legality

- The tool never modifies the original file; it writes a new output.
- It refuses to overwrite the source unless you pass `--overwrite`.
- `.ccproject` / `.ccseed` store only hashes + offsets, never ROM bytes, so
  corruptions can be shared without sharing copyrighted data.
- Use it on files you are legally allowed to use.

## License

MIT — see [LICENSE](LICENSE).
