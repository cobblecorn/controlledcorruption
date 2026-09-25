# Generic profiles

Drop JSON/YAML profiles here for non-console binaries (game data files,
archives, extracted assets). A profile identifies its target by SHA-256 and
lists named regions with categories.

Minimal example:

```json
{
  "id": "my-game-data",
  "name": "My Game data.pak",
  "platform": "generic",
  "identification": { "sha256": ["<hash from `ccorrupt info file.pak`>"] },
  "regions": [
    { "name": "Meshes", "category": "models", "start": "0x1000", "end": "0x5000", "data_type": "float32" }
  ]
}
```

Point the tool at extra directories with the `CCORRUPT_PROFILES` environment
variable (OS path-separated), or install to `~/.config/ccorrupt/profiles`.
