# Changelog

All notable changes to this project are documented here.

## 0.1.0 — initial release

A deterministic, region-aware ROM/binary corruption framework.

### Core engine
- Versioned `xoshiro256**` PRNG (SHA-256 seed folding) for byte-identical
  reproducibility across runs.
- Region model with interval arithmetic; protected regions always override
  targets. Original input is never modified.
- Mutation strategies: byte replace, bit flip, byte offset, int16, int32,
  float32 (multiply/add/sign-flip/replace, NaN-safe), block swap/repeat/shift.
- Intensity split into **density** (how many) and **magnitude** (how hard).
- Mutation history/log; safe atomic output writes.

### Semantic (Level-3) corruption
- Model/vertex ops: scale, stretch, displace, mirror, flatten, reverse per
  axis, preserving topology.
- Texture ops: channel shift/swap/scale, invert (rgba8888/rgb888/rgba5551/
  rgb565), and format-agnostic palette rotate/shuffle.

### Projects & workflow
- `.ccproject` with a non-destructive mutation stack (layers); `.ccseed`
  shareable recipes (hashes + offsets only, never ROM bytes).
- Interactive mutation **evolution** (keep/reject/regenerate).
- **Batch** generation across seeds; guided-fuzz **region sweep** with a
  crash/survival heat map (emulator-agnostic, pluggable tester).
- `verify` reproducibility check; `corrupt --dry-run`.

### Platforms (12 adapters)
- Cartridge: Nintendo 64 (CIC checksum repair), Game Boy Advance (header
  checksum), Nintendo DS (header CRC-16).
- Disc: GameCube, Wii, ISO9660 (PS1/PS2/PSP images).
- Executables: PlayStation PS-X EXE, Xbox 360 XEX, original Xbox XBE, ELF
  (PS2/PSP/homebrew), PE (PC/Windows).
- Generic fallback for any binary.

### Profiles
- External JSON/YAML profiles identified by ROM hash; example + runnable demo.
- CLI authoring: `mkprofile` (from specs or a diff) and `addregion`.

### Front-ends & tooling
- CLI: info, corrupt, apply, verify, diff, model, texture, batch, sweep,
  evolve, mkprofile, addregion, emu, hex, search, strings, entropy, scan, demo.
- PySide6 desktop GUI sharing the same core (ROM map, history, hex inspector,
  semantic mode).
- Emulator launcher with saved presets (`emu`, `--launch @name`).
- Reverse-engineering helpers: hex viewer + value interpretation, byte/ASCII/
  int/float search, strings, entropy sparkline, structure heuristics,
  differential analysis.

### Tests & quality
- 156 tests covering determinism, bounds, protection, source immutability,
  serialization, platforms, semantic/texture ops, evolution, fuzz, CLI and GUI.
- Clean under `ruff` (pyflakes + syntax rules).
