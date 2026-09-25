"""Command line interface for the Controlled ROM Corruptor.

The GUI calls the same core APIs, so anything doable here is doable there.

Examples
--------
    ccorrupt info game.z64
    ccorrupt corrupt game.z64 --profile sm64_us --target models --target animations \\
        --density 0.002 --magnitude 0.4 --seed CODY-3491281 --output corrupt.z64
    ccorrupt corrupt game.bin --range 0x500000:0x900000 --type float32 --seed 12345
    ccorrupt apply my.ccproject game.z64 -o out.z64
    ccorrupt diff original.z64 modded.z64
    ccorrupt demo demo.z64        # write the bundled synthetic demo ROM
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional, Sequence, Tuple

from .. import __version__
from ..core import analysis, hexview
from ..core import binary as binmod
from ..core.diff import diff_summary
from ..core.pipeline import corrupt as run_corrupt
from ..core.project import CorruptionProject, CorruptionSeed
from ..core.regions import Region, parse_offset
from ..core.settings import ALL_TYPES, DEFAULT_TYPES, MutationSettings
from ..profiles import ProfileLibrary
from .. import platforms

SUBCOMMANDS = {"info", "corrupt", "apply", "profiles", "diff", "demo",
               "hex", "search", "strings", "entropy", "scan", "model", "texture",
               "batch", "sweep", "evolve", "mkprofile", "addregion", "emu", "verify"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _parse_range(text: str) -> Tuple[int, int]:
    if ":" not in text:
        raise argparse.ArgumentTypeError(f"range must be START:END, got {text!r}")
    a, b = text.split(":", 1)
    start, end = parse_offset(a), parse_offset(b)
    if end <= start:
        raise argparse.ArgumentTypeError(f"range END must exceed START in {text!r}")
    return (start, end)


def _fmt_hex(n: int) -> str:
    return f"0x{n:08X}"


def _eprint(*a):
    print(*a, file=sys.stderr)


# --------------------------------------------------------------------------
# info
# --------------------------------------------------------------------------
def cmd_info(args) -> int:
    bf = binmod.load_binary(args.input)
    plat = platforms.detect(bf.data)
    lib = ProfileLibrary()
    profile = lib.identify(bf.sha256)
    report = plat.validate(bf.data)

    info = {
        "file": args.input,
        "size": bf.size,
        "size_hex": _fmt_hex(bf.size),
        "hashes": bf.hashes,
        "platform": plat.info(bf.data),
        "profile": (profile.id if profile else None),
        "validation": report.to_dict(),
    }
    if args.json:
        print(json.dumps(info, indent=2))
        return 0

    print(f"File:      {args.input}")
    print(f"Size:      {bf.size:,} bytes ({_fmt_hex(bf.size)})")
    print(f"SHA-256:   {bf.sha256}")
    print(f"MD5:       {bf.hashes.get('md5')}")
    print(f"SHA-1:     {bf.hashes.get('sha1')}")
    print(f"CRC32:     {bf.hashes.get('crc32')}")
    print(f"Platform:  {plat.name} ({plat.id})")
    for k, v in plat.info(bf.data).items():
        if k not in ("platform", "name"):
            print(f"    {k}: {v}")
    print(f"Profile:   {profile.name + ' [' + profile.id + ']' if profile else '(none matched)'}")
    if profile:
        print(f"    categories: {', '.join(profile.categories())}")
    print(f"Validation: {report.worst.value}")
    for c in report.checks:
        print(f"    {c}")
    return 0


# --------------------------------------------------------------------------
# corrupt
# --------------------------------------------------------------------------
def _settings_from_args(args) -> MutationSettings:
    types = args.type if args.type else list(DEFAULT_TYPES)
    if args.intensity is not None:
        s = MutationSettings.from_intensity(args.intensity, seed=args.seed, types=types)
    else:
        s = MutationSettings(seed=args.seed, density=args.density,
                             magnitude=args.magnitude, types=types)
    s.wrap = not args.clamp
    s.allow_nan = args.allow_nan
    if args.block_size is not None:
        s.block_size = args.block_size
    if args.endianness:
        s.endianness = args.endianness
    return s


def cmd_corrupt(args) -> int:
    bf = binmod.load_binary(args.input)
    settings = _settings_from_args(args)

    intervals = list(args.range) if args.range else None
    extra_protected = None
    if args.protect:
        extra_protected = [
            Region(f"user_protect_{i}", s, e, category="header", mutable=False,
                   source="cli")
            for i, (s, e) in enumerate(args.protect)
        ]

    try:
        result = run_corrupt(
            bf,
            settings,
            categories=args.target or None,
            profile_id=args.profile,
            auto_identify=not args.no_auto,
            platform=(platforms.get(args.platform) if args.platform else None),
            target_intervals=intervals,
            extra_protected=extra_protected,
            repair_checksum=not args.no_repair,
        )
    except KeyError as exc:
        _eprint(f"error: {exc}")
        return 2

    # Decide output path.
    out_path = args.output or binmod.suggest_output_name(args.input, settings.seed)
    if os.path.abspath(out_path) == os.path.abspath(args.input) and not args.overwrite \
            and not args.dry_run:
        _eprint("error: output would overwrite the source; refusing "
                "(choose --output or pass --overwrite)")
        return 2
    if not args.dry_run:
        binmod.write_output(out_path, result.output, overwrite=args.overwrite)

    # Logging / summary.
    log = result.engine_result.log
    summary = log.summary()
    plat = result.platform
    prof = result.profile
    if not args.quiet:
        _eprint(f"[INFO] Loaded {args.input} ({bf.size:,} bytes)")
        _eprint(f"[INFO] Platform: {plat.name}")
        _eprint(f"[INFO] Profile:  {prof.name if prof else '(none)'}")
        _eprint(f"[INFO] Seed:     {settings.seed}")
        if args.target:
            _eprint(f"[INFO] Targets:  {', '.join(args.target)}")
        _eprint(f"[INFO] Mutable bytes: {result.engine_result.mutable_bytes:,}")
        _eprint(f"[INFO] Mutations: {summary['applied']} applied, "
                f"{summary['skipped']} skipped")
        if result.checksum_repaired:
            _eprint("[INFO] Recalculated platform checksum")
        if args.dry_run:
            from ..core.diff import changed_intervals
            changed = changed_intervals(bf.data, result.output, merge_gap=64)
            _eprint(f"[DRY-RUN] Would change {len(changed)} range(s); "
                    f"output NOT written to {out_path}")
        else:
            _eprint(f"[INFO] Saved output -> {out_path}")

    if args.verbose:
        limit = args.limit if args.limit is not None else 25
        for rec in log.records[:limit]:
            _eprint("   ", rec.describe())
        if len(log.records) > limit:
            _eprint(f"    ... {len(log.records) - limit} more")

    # Optional artifacts.
    if args.save_project:
        project = CorruptionProject.single(
            bf, settings, categories=args.target or None,
            profile_id=(prof.id if prof else args.profile),
            platform=(plat.id if not args.no_auto else args.platform),
            target_intervals=intervals, repair_checksum=not args.no_repair,
        )
        project.save(args.save_project)
        if not args.quiet:
            _eprint(f"[INFO] Saved project -> {args.save_project}")
    if args.save_seed:
        project = CorruptionProject.single(
            bf, settings, categories=args.target or None,
            profile_id=(prof.id if prof else args.profile),
            platform=(plat.id if not args.no_auto else args.platform),
            target_intervals=intervals, repair_checksum=not args.no_repair,
        )
        CorruptionSeed.from_project(project).save(args.save_seed)
        if not args.quiet:
            _eprint(f"[INFO] Saved seed -> {args.save_seed}")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(log.to_dict(), fh, indent=2)
        if not args.quiet:
            _eprint(f"[INFO] Saved mutation report -> {args.report}")

    # Optional emulator launch (supports @preset names).
    if args.launch and not args.dry_run:
        from ..emulator import CustomCommandEmulator, resolve_launch

        try:
            command = resolve_launch(args.launch)
        except KeyError as exc:
            _eprint(f"error: {exc}")
            return 2
        emu = CustomCommandEmulator(command)
        _eprint(f"[INFO] Launching: {' '.join(emu.build_args(out_path))}")
        emu.launch(out_path)

    if not args.dry_run:
        print(out_path)
    return 0


# --------------------------------------------------------------------------
# apply
# --------------------------------------------------------------------------
def cmd_apply(args) -> int:
    project = CorruptionProject.load(args.project)
    bf = binmod.load_binary(args.input)
    ok, msg = project.verify_source(bf)
    if not ok:
        _eprint(f"[WARN] {msg}")
        if not args.force:
            _eprint("       pass --force to apply anyway")
            return 2
    result = project.apply(bf, verify=False)
    out_path = args.output or binmod.suggest_output_name(
        args.input, project.layers[0].settings.seed if project.layers else "project"
    )
    binmod.write_output(out_path, result.output, overwrite=args.overwrite)
    summary = result.combined_log.summary()
    if not args.quiet:
        _eprint(f"[INFO] Applied {len([l for l in project.layers if l.enabled])} "
                f"layer(s): {summary['applied']} mutations")
        if result.checksum_repaired:
            _eprint("[INFO] Recalculated platform checksum")
        _eprint(f"[INFO] Saved output -> {out_path}")
    print(out_path)
    return 0


# --------------------------------------------------------------------------
# verify (reproduce from project/seed and confirm)
# --------------------------------------------------------------------------
def cmd_verify(args) -> int:
    bf = binmod.load_binary(args.input)
    recipe = args.recipe
    if recipe.lower().endswith(".ccseed"):
        project = CorruptionSeed.load(recipe).to_project()
    else:
        project = CorruptionProject.load(recipe)

    ok, msg = project.verify_source(bf)
    if not ok:
        _eprint(f"[FAIL] {msg}")
        return 1
    _eprint(f"[PASS] source hash matches ({bf.sha256})")

    # Reproduce twice to prove determinism.
    out1 = project.apply(bf, verify=False).output
    out2 = project.apply(bf, verify=False).output
    if out1 != out2:
        _eprint("[FAIL] non-deterministic: two applies produced different output")
        return 1
    h = binmod.compute_hashes(out1, ("sha256",))["sha256"]
    _eprint(f"[PASS] deterministic reproduction (output sha256 {h})")

    if args.against:
        other = binmod.load_binary(args.against)
        if other.data == out1:
            _eprint(f"[PASS] output matches {args.against}")
        else:
            from ..core.diff import diff_summary
            s = diff_summary(other.data, out1)
            _eprint(f"[FAIL] output does NOT match {args.against}: "
                    f"{s['changed_ranges']} differing range(s), "
                    f"{s['changed_bytes']} bytes")
            return 1
    print(h)
    return 0


# --------------------------------------------------------------------------
# profiles
# --------------------------------------------------------------------------
def cmd_profiles(args) -> int:
    lib = ProfileLibrary()
    if args.json:
        print(json.dumps([{"id": p.id, "name": p.name, "platform": p.platform,
                           "categories": p.categories(),
                           "sha256": p.sha256} for p in lib.all()], indent=2))
        return 0
    if not lib.all():
        print("(no profiles found)")
    for p in sorted(lib.all(), key=lambda x: x.id):
        print(f"{p.id}")
        print(f"    name:       {p.name}")
        print(f"    platform:   {p.platform}")
        print(f"    categories: {', '.join(p.categories()) or '(none)'}")
        print(f"    hashes:     {len(p.sha256)}")
    if lib.errors:
        _eprint("\nProfile load errors:")
        for e in lib.errors:
            _eprint("   ", e)
    return 0


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------
def cmd_diff(args) -> int:
    a = binmod.load_binary(args.a)
    b = binmod.load_binary(args.b)
    summary = diff_summary(a.data, b.data, merge_gap=args.merge_gap)
    if args.json or args.export:
        payload = {
            "a": args.a, "b": args.b,
            "size_a": summary["size_a"], "size_b": summary["size_b"],
            "changed_ranges": summary["changed_ranges"],
            "changed_bytes": summary["changed_bytes"],
            "regions": [
                {"name": f"diff_{i:03d}", "start": _fmt_hex(s), "end": _fmt_hex(e),
                 "category": "unknown"}
                for i, (s, e) in enumerate(summary["intervals"])
            ],
        }
        if args.export:
            with open(args.export, "w", encoding="utf-8") as fh:
                json.dump({"regions": payload["regions"]}, fh, indent=2)
            _eprint(f"[INFO] Exported {summary['changed_ranges']} regions -> {args.export}")
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0
    print(f"A: {args.a} ({summary['size_a']:,} bytes)")
    print(f"B: {args.b} ({summary['size_b']:,} bytes)")
    print(f"Changed ranges: {summary['changed_ranges']}  "
          f"({summary['changed_bytes']:,} bytes)")
    for i, (s, e) in enumerate(summary["intervals"][: args.limit]):
        print(f"    diff_{i:03d}: {_fmt_hex(s)} - {_fmt_hex(e)} ({e - s} bytes)")
    if summary["changed_ranges"] > args.limit:
        print(f"    ... {summary['changed_ranges'] - args.limit} more")
    return 0


# --------------------------------------------------------------------------
# hex
# --------------------------------------------------------------------------
def cmd_hex(args) -> int:
    bf = binmod.load_binary(args.input)
    start = parse_offset(args.offset)
    if start < 0 or start > bf.size:
        _eprint(f"error: offset 0x{start:X} out of range (size 0x{bf.size:X})")
        return 2
    if args.interpret:
        print(hexview.format_interpret(bf.data, start, endian=args.endianness))
        return 0
    length = parse_offset(args.length) if args.length is not None else 256
    print(hexview.hex_dump(bf.data, start, length, width=args.width))
    return 0


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------
def cmd_search(args) -> int:
    bf = binmod.load_binary(args.input)
    hits: List[int] = []
    label = ""
    if args.bytes is not None:
        try:
            pattern = bytes.fromhex(args.bytes.replace(" ", ""))
        except ValueError:
            _eprint("error: --bytes must be hex, e.g. 'deadbeef' or 'de ad be ef'")
            return 2
        hits = analysis.search_bytes(bf.data, pattern, limit=args.limit)
        label = f"bytes {pattern.hex()}"
    elif args.ascii is not None:
        hits = analysis.search_bytes(bf.data, args.ascii.encode("latin-1"), limit=args.limit)
        label = f"ascii {args.ascii!r}"
    elif args.int is not None:
        hits = analysis.search_int(bf.data, args.int, size=args.size,
                                   endian=args.endianness, signed=args.signed,
                                   limit=args.limit)
        label = f"int {args.int} (size {args.size}, {args.endianness}, " \
                f"{'signed' if args.signed else 'unsigned'})"
    elif args.float is not None:
        hits = analysis.search_float(bf.data, args.float, tol=args.tol,
                                     endian=args.endianness, double=args.double,
                                     limit=args.limit)
        label = f"float ~{args.float} (tol {args.tol})"
    else:
        _eprint("error: provide one of --bytes / --ascii / --int / --float")
        return 2

    if args.json:
        print(json.dumps({"query": label, "count": len(hits),
                          "offsets": [_fmt_hex(o) for o in hits]}, indent=2))
        return 0
    print(f"{len(hits)} match(es) for {label}")
    for o in hits:
        print(f"    {_fmt_hex(o)}")
    return 0


# --------------------------------------------------------------------------
# strings
# --------------------------------------------------------------------------
def cmd_strings(args) -> int:
    bf = binmod.load_binary(args.input)
    found = analysis.find_strings(bf.data, min_len=args.min_len, limit=args.limit)
    if args.json:
        print(json.dumps([{"offset": _fmt_hex(f.offset), "text": f.text}
                          for f in found], indent=2))
        return 0
    for f in found:
        print(f"{_fmt_hex(f.offset)}  {f.text}")
    return 0


# --------------------------------------------------------------------------
# entropy
# --------------------------------------------------------------------------
def cmd_entropy(args) -> int:
    bf = binmod.load_binary(args.input)
    pairs = analysis.entropy_blocks(bf.data, blocks=args.blocks)
    if args.json:
        print(json.dumps([{"offset": _fmt_hex(o), "entropy": round(e, 3)}
                          for o, e in pairs], indent=2))
        return 0
    spark = analysis.entropy_sparkline(pairs)
    print(f"entropy over {len(pairs)} blocks (0..8 bits): low ' .:-' .. high '#%@'")
    print(spark)
    hi = [(_fmt_hex(o), round(e, 2)) for o, e in pairs if e >= 7.5]
    if hi:
        print(f"high-entropy blocks (>=7.5): {', '.join(f'{o}:{e}' for o, e in hi[:12])}")
    return 0


# --------------------------------------------------------------------------
# scan (structure heuristics -- experimental)
# --------------------------------------------------------------------------
def cmd_scan(args) -> int:
    bf = binmod.load_binary(args.input)
    do_all = not (args.floats or args.pointers or args.strings)
    result = {}
    if args.floats or do_all:
        runs = analysis.float_triplets(bf.data, endian=args.endianness)
        result["float_triplets"] = runs
    if args.pointers or do_all:
        ptrs = analysis.pointer_candidates(bf.data, endian=args.endianness, limit=args.limit)
        result["pointer_candidates"] = ptrs
    if args.strings or do_all:
        strs = analysis.find_strings(bf.data, min_len=6, limit=args.limit)
        result["strings"] = strs

    if args.json:
        payload = {
            "note": "EXPERIMENTAL / low confidence heuristics",
            "float_triplets": [{"start": _fmt_hex(o), "count": c}
                               for o, c in result.get("float_triplets", [])],
            "pointer_candidates": [{"offset": _fmt_hex(o), "value": _fmt_hex(v)}
                                   for o, v in result.get("pointer_candidates", [])[:args.limit]],
            "strings": [{"offset": _fmt_hex(f.offset), "text": f.text}
                        for f in result.get("strings", [])],
        }
        print(json.dumps(payload, indent=2))
        return 0

    print("[EXPERIMENTAL] structure guesses -- low confidence, verify manually\n")
    if "float_triplets" in result:
        runs = result["float_triplets"]
        print(f"Vertex-like float32 triplet runs: {len(runs)}")
        for o, c in runs[:args.limit]:
            print(f"    {_fmt_hex(o)}  x{c} triplets  (~{c*12} bytes)")
    if "pointer_candidates" in result:
        ptrs = result["pointer_candidates"]
        print(f"\nPointer candidates (word in [0, filesize)): {len(ptrs)}")
        for o, v in ptrs[:args.limit]:
            print(f"    {_fmt_hex(o)} -> {_fmt_hex(v)}")
    if "strings" in result:
        strs = result["strings"]
        print(f"\nStrings (>=6 chars): {len(strs)}")
        for f in strs[:args.limit]:
            print(f"    {_fmt_hex(f.offset)}  {f.text}")
    return 0


# --------------------------------------------------------------------------
# model (semantic / Level-3 corruption)
# --------------------------------------------------------------------------
def cmd_model(args) -> int:
    from ..core import semantic
    from ..core.regions import merge_intervals, subtract_intervals

    bf = binmod.load_binary(args.input)
    plat = platforms.get(args.platform) if args.platform else platforms.detect(bf.data)
    lib = ProfileLibrary()
    profile = lib.get(args.profile) if args.profile else lib.identify(bf.sha256)

    # Resolve the target range.
    if args.range:
        start, end = args.range
    elif args.region:
        if not profile:
            _eprint("error: --region needs a matching profile; use --range instead")
            return 2
        match = next((r for r in profile.regions if r.name.lower() == args.region.lower()), None)
        if not match:
            _eprint(f"error: region {args.region!r} not in profile {profile.id}")
            return 2
        start, end = match.start, match.end
        if args.endianness is None and match.endianness:
            args.endianness = match.endianness
    else:
        _eprint("error: provide --range START:END or --region NAME")
        return 2

    # Never write into protected regions.
    protected = [r.interval for r in plat.protected_regions(bf.data)]
    if profile:
        protected += [r.interval for r in profile.protected]
    safe = subtract_intervals([(start, end)], protected)
    if not safe:
        _eprint("error: requested range is entirely protected")
        return 2
    if merge_intervals(safe) != [(start, end)]:
        _eprint(f"[WARN] range trimmed to avoid protected areas: "
                f"{', '.join(_fmt_hex(s) + ':' + _fmt_hex(e) for s, e in safe)}")

    endian = args.endianness or plat.endianness(bf.data)
    comps = None
    if args.components:
        comps = [parse_offset(c) for c in args.components.split(",")]
    layout = semantic.build_layout(stride=args.stride, component_offsets=comps,
                                    endian=endian)
    strengths = [args.x, args.y, args.z]
    settings = semantic.SemanticSettings(op=args.op, strengths=strengths,
                                         avoid_nan=not args.allow_nan, seed=args.seed)

    out = bytearray(bf.data)
    log = None
    for s, e in safe:
        log = semantic.corrupt_region(out, s, e, layout, settings,
                                      region_name=(args.region or "range"), log=log)
    output = bytes(out)
    if not args.no_repair:
        output = plat.repair_checksum(output)

    out_path = args.output or binmod.suggest_output_name(args.input, args.seed)
    if os.path.abspath(out_path) == os.path.abspath(args.input) and not args.overwrite:
        _eprint("error: output would overwrite the source; use --output or --overwrite")
        return 2
    binmod.write_output(out_path, output, overwrite=args.overwrite)

    if not args.quiet:
        s = log.summary() if log else {"applied": 0}
        _eprint(f"[INFO] Semantic op '{args.op}' on {endian}-endian float array "
                f"(stride {layout.stride}, components {list(layout.component_offsets)})")
        _eprint(f"[INFO] X={args.x} Y={args.y} Z={args.z}")
        _eprint(f"[INFO] Components changed: {s['applied']}")
        _eprint(f"[INFO] Saved output -> {out_path}")
    print(out_path)
    return 0


# --------------------------------------------------------------------------
# batch
# --------------------------------------------------------------------------
def cmd_batch(args) -> int:
    from ..core.batch import generate_batch, seed_series

    bf = binmod.load_binary(args.input)
    settings = MutationSettings(seed=0, density=args.density, magnitude=args.magnitude,
                                types=args.type or list(DEFAULT_TYPES))
    seeds = (args.seed if args.seed else
             seed_series(args.count, prefix=args.seed_prefix, start=args.start_seed))
    items = generate_batch(bf, settings, seeds, categories=args.target or None,
                           profile_id=args.profile, auto_identify=not args.no_auto,
                           repair_checksum=not args.no_repair)
    os.makedirs(args.outdir, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(args.input))
    manifest = []
    for item in items:
        tag = "".join(ch for ch in str(item.seed) if ch.isalnum()) or "seed"
        out_path = os.path.join(args.outdir, f"{base}_{tag}{ext}")
        binmod.write_output(out_path, item.output, overwrite=True)
        manifest.append({"seed": item.seed, "file": out_path, "summary": item.summary})
        if not args.quiet:
            _eprint(f"[INFO] {out_path}  ({item.summary['applied']} mutations)")
    if args.manifest:
        with open(args.manifest, "w", encoding="utf-8") as fh:
            json.dump({"source": bf.sha256, "items": manifest}, fh, indent=2)
        if not args.quiet:
            _eprint(f"[INFO] Wrote manifest -> {args.manifest}")
    print(f"{len(items)} variants -> {args.outdir}")
    return 0


# --------------------------------------------------------------------------
# sweep (guided fuzz -- needs an emulator)
# --------------------------------------------------------------------------
def cmd_sweep(args) -> int:
    from ..core.fuzz import emulator_tester, sweep

    if not args.launch:
        _eprint("error: sweep needs an emulator to classify results; pass "
                '--launch "emulator {ROM}"')
        return 2
    from ..emulator import resolve_launch
    try:
        command = resolve_launch(args.launch)
    except KeyError as exc:
        _eprint(f"error: {exc}")
        return 2
    bf = binmod.load_binary(args.input)
    plat = platforms.detect(bf.data)
    tester = emulator_tester(command, boot_time=args.boot_time, timeout=args.timeout)
    settings = MutationSettings(seed=0, density=args.density, magnitude=args.magnitude)

    def progress(done, total, outcome):
        if not args.quiet:
            _eprint(f"[{done}/{total}] 0x{outcome.start:08X} "
                    f"safety={outcome.safety:.2f}")

    heat = sweep(bf, tester, block_size=args.block_size, settings=settings,
                 trials=args.trials, on_progress=progress,
                 repair_checksum=not args.no_repair)
    if args.json:
        print(json.dumps(heat.to_dict(), indent=2))
    else:
        print(heat.render())
        crit = heat.critical_blocks(threshold=args.critical_threshold)
        print(f"\nCritical blocks (safety < {args.critical_threshold}): {len(crit)}")
        for b in crit[:20]:
            print(f"    0x{b.start:08X}-0x{b.end:08X}  safety={b.safety:.2f}")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(heat.to_dict(), fh, indent=2)
    if args.export_profile:
        from ..profiles import author
        regions = heat.suggest_regions(min_safety=args.min_safety)
        profile = author.new_profile(
            bf, args.profile_id, args.profile_id, platform=plat.id,
            regions=regions, notes="Draft profile from a guided-fuzz sweep "
            f"(blocks with safety >= {args.min_safety}).")
        author.save_profile(profile, args.export_profile, overwrite=True)
        _eprint(f"[INFO] Exported {len(regions)} candidate region(s) -> "
                f"{args.export_profile}")
    return 0


# --------------------------------------------------------------------------
# evolve (interactive keep/reject/regenerate)
# --------------------------------------------------------------------------
def cmd_evolve(args) -> int:
    from ..core.evolve import Evolver

    bf = binmod.load_binary(args.input)
    plat = platforms.get(args.platform) if args.platform else platforms.detect(bf.data)
    lib = ProfileLibrary()
    profile = lib.get(args.profile) if args.profile else lib.identify(bf.sha256)
    out_path = args.output or binmod.suggest_output_name(args.input, "evolve")

    evolver = Evolver(
        binary=bf, platform=plat, profile=profile,
        categories=args.target or None,
        repair_checksum=not args.no_repair,
        base_settings=MutationSettings(density=args.density, magnitude=args.magnitude,
                                       types=args.type or list(DEFAULT_TYPES)),
    )

    emu = None
    if args.launch:
        from ..emulator import CustomCommandEmulator, resolve_launch
        emu = CustomCommandEmulator(resolve_launch(args.launch))

    print("Mutation evolution. Commands:")
    print("  k = keep    r = reject/regenerate    s = save project    "
          "u = undo last kept    q = quit")
    counter = 0

    def make_candidate():
        nonlocal counter
        counter += 1
        seed = f"{args.seed_prefix}-{counter}"
        cand = evolver.propose(seed, intensity=args.intensity)
        binmod.write_output(out_path, cand.output, overwrite=True)
        applied = cand.log.summary()["applied"]
        print(f"\nGeneration {cand.generation} (seed {seed}): "
              f"{applied} total mutations across {len(evolver.kept) + 1} layer(s)")
        print(f"  wrote {out_path}")
        if emu:
            print(f"  launching: {' '.join(emu.build_args(out_path))}")
            emu.launch(out_path)
        return cand

    make_candidate()
    while True:
        try:
            choice = input("[k/r/s/u/q]> ").strip().lower()
        except EOFError:
            break
        if choice in ("q", "quit"):
            break
        elif choice in ("k", "keep"):
            evolver.keep()
            print(f"  kept. stack now {len(evolver.kept)} layer(s).")
            make_candidate()
        elif choice in ("r", "reject", "n", "new"):
            evolver.reject()
            make_candidate()
        elif choice in ("u", "undo"):
            removed = evolver.undo()
            print(f"  undid {removed.name if removed else '(nothing)'}")
            binmod.write_output(out_path, evolver.current_output(), overwrite=True)
        elif choice in ("s", "save"):
            proj_path = args.save_project or (os.path.splitext(out_path)[0] + ".ccproject")
            evolver.to_project().save(proj_path)
            print(f"  saved project -> {proj_path}")
        else:
            print("  ? commands: k keep, r regenerate, s save, u undo, q quit")

    # On exit, the file on disk should reflect the KEPT stack (what the saved
    # project reproduces), not a dangling unkept proposal.
    evolver.reject()
    binmod.write_output(out_path, evolver.current_output(), overwrite=True)
    if args.save_project:
        evolver.to_project().save(args.save_project)
        print(f"Saved evolved project -> {args.save_project}")
    print(f"Kept {len(evolver.kept)} generation(s); final output at {out_path} "
          f"(matches the saved project)")
    return 0


# --------------------------------------------------------------------------
# mkprofile / addregion (user profile authoring)
# --------------------------------------------------------------------------
def cmd_mkprofile(args) -> int:
    from ..profiles import author

    bf = binmod.load_binary(args.input)
    platform = args.platform or platforms.detect(bf.data).id
    regions = []
    for spec in args.region or []:
        try:
            regions.append(author.parse_region_spec(spec))
        except ValueError as exc:
            _eprint(f"error: {exc}")
            return 2
    if args.from_diff:
        other = binmod.load_binary(args.from_diff)
        regions.extend(author.regions_from_diff(bf.data, other.data,
                                                merge_gap=args.merge_gap))
    profile = author.new_profile(bf, args.id, args.name or args.id,
                                 platform=platform, regions=regions,
                                 notes=args.notes)
    out_path = args.output or f"{args.id}.json"
    author.save_profile(profile, out_path, overwrite=args.overwrite)
    if not args.quiet:
        _eprint(f"[INFO] Profile '{args.id}' for {bf.filename} ({platform})")
        _eprint(f"[INFO] SHA-256: {bf.sha256}")
        _eprint(f"[INFO] {len(regions)} region(s); saved -> {out_path}")
        _eprint("[INFO] Place it in a profiles dir (or set CCORRUPT_PROFILES) "
                "to auto-match this ROM.")
    print(out_path)
    return 0


def cmd_addregion(args) -> int:
    from ..profiles import author

    profile = author.load_profile(args.profile)
    if args.range:
        start, end = args.range
    else:
        _eprint("error: provide --range START:END")
        return 2
    region = Region(name=args.name, category=args.category, start=start, end=end,
                    endianness=args.endianness or "little", data_type=args.data_type,
                    tags=args.tag or [], source="user")
    author.add_region(profile, region)
    author.save_profile(profile, args.profile, overwrite=True)
    if not args.quiet:
        _eprint(f"[INFO] Added region {args.name!r} [{args.category}] "
                f"{_fmt_hex(start)}-{_fmt_hex(end)} to {profile.id}")
        _eprint(f"[INFO] Profile now has {len(profile.regions)} region(s)")
    print(args.profile)
    return 0


# --------------------------------------------------------------------------
# texture (semantic texture corruption)
# --------------------------------------------------------------------------
def cmd_texture(args) -> int:
    from ..core import texture
    from ..core.regions import subtract_intervals

    bf = binmod.load_binary(args.input)
    plat = platforms.get(args.platform) if args.platform else platforms.detect(bf.data)
    if not args.range:
        _eprint("error: provide --range START:END")
        return 2
    start, end = args.range
    protected = [r.interval for r in plat.protected_regions(bf.data)]
    safe = subtract_intervals([(start, end)], protected)
    if not safe:
        _eprint("error: requested range is entirely protected")
        return 2

    fmt = None
    if args.op in texture.CHANNEL_OPS:
        fmt = texture.get_format(args.format, endian=(args.endianness or "big"))
    settings = texture.TextureSettings(
        op=args.op, strength=args.strength, channel_a=args.a, channel_b=args.b,
        channel=args.channel, rotate_by=args.rotate_by,
        entry_size=args.entry_size, seed=args.seed)

    out = bytearray(bf.data)
    log = None
    for s, e in safe:
        log = texture.corrupt_texture(out, s, e, fmt, settings,
                                      region_name="texture", log=log)
    output = bytes(out)
    if not args.no_repair:
        output = plat.repair_checksum(output)

    out_path = args.output or binmod.suggest_output_name(args.input, args.seed)
    if os.path.abspath(out_path) == os.path.abspath(args.input) and not args.overwrite:
        _eprint("error: output would overwrite the source; use --output or --overwrite")
        return 2
    binmod.write_output(out_path, output, overwrite=args.overwrite)
    if not args.quiet:
        _eprint(f"[INFO] Texture op '{args.op}'"
                + (f" ({fmt.name})" if fmt else "") + f" on {_fmt_hex(start)}-{_fmt_hex(end)}")
        for rec in (log.records if log else []):
            _eprint(f"    {rec.describe()}")
        _eprint(f"[INFO] Saved output -> {out_path}")
    print(out_path)
    return 0


# --------------------------------------------------------------------------
# emu (emulator presets)
# --------------------------------------------------------------------------
def cmd_emu(args) -> int:
    from ..emulator import EmulatorPresets

    presets = EmulatorPresets()
    action = getattr(args, "emu_action", None) or "list"

    if action == "list":
        if not presets.names():
            print("(no emulator presets; add one with: ccorrupt emu add <name> \"<cmd> {ROM}\")")
            return 0
        default = presets.default()
        for name in presets.names():
            entry = presets.get(name)
            mark = " *" if name == default else "  "
            print(f"{mark}{name}: {entry['command']}")
        print("\n* = default. Use with --launch @<name>.")
        return 0
    if action == "add":
        presets.add(args.name, args.command, working_dir=args.working_dir,
                    timeout=args.timeout, make_default=args.default)
        presets.save()
        print(f"added preset {args.name!r}")
        return 0
    if action == "remove":
        existed = presets.remove(args.name)
        presets.save()
        print(f"removed {args.name!r}" if existed else f"no such preset {args.name!r}")
        return 0 if existed else 2
    if action == "default":
        try:
            presets.set_default(args.name)
        except KeyError as exc:
            _eprint(f"error: {exc}")
            return 2
        presets.save()
        print(f"default emulator is now {args.name!r}")
        return 0
    return 2


# --------------------------------------------------------------------------
# demo
# --------------------------------------------------------------------------
def cmd_demo(args) -> int:
    from ..demo import build_demo_rom

    data = build_demo_rom()
    binmod.write_output(args.output, data, overwrite=args.overwrite)
    bf = binmod.from_bytes(data, path=args.output)
    print(f"Wrote demo ROM -> {args.output} ({bf.size:,} bytes)")
    print(f"SHA-256: {bf.sha256}")
    print("Try:")
    print(f"    ccorrupt info {args.output}")
    print(f"    ccorrupt corrupt {args.output} --target models "
          f"--seed CODY-3491281 -o {os.path.splitext(args.output)[0]}_corrupt"
          f"{os.path.splitext(args.output)[1]}")
    return 0


# --------------------------------------------------------------------------
# argument parser
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ccorrupt",
        description="Controlled ROM Corruptor -- deterministic, region-aware "
                    "binary/ROM corruption.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command")

    # info
    pi = sub.add_parser("info", help="show file hashes, platform and profile")
    pi.add_argument("input")
    pi.add_argument("--json", action="store_true")
    pi.set_defaults(func=cmd_info)

    # corrupt
    pc = sub.add_parser("corrupt", help="produce a corrupted copy")
    _add_corrupt_args(pc)
    pc.set_defaults(func=cmd_corrupt)

    # apply
    pa = sub.add_parser("apply", help="apply a saved .ccproject to a ROM")
    pa.add_argument("project")
    pa.add_argument("input")
    pa.add_argument("-o", "--output")
    pa.add_argument("--overwrite", action="store_true")
    pa.add_argument("--force", action="store_true", help="apply despite hash mismatch")
    pa.add_argument("-q", "--quiet", action="store_true")
    pa.set_defaults(func=cmd_apply)

    # verify
    pv = sub.add_parser("verify", help="reproduce a .ccproject/.ccseed and confirm it")
    pv.add_argument("recipe", help="a .ccproject or .ccseed file")
    pv.add_argument("input", help="the source ROM/binary")
    pv.add_argument("--against", help="also compare the reproduction to this file")
    pv.set_defaults(func=cmd_verify)

    # profiles
    pp = sub.add_parser("profiles", help="list available game profiles")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(func=cmd_profiles)

    # diff
    pd = sub.add_parser("diff", help="report byte ranges that differ between two files")
    pd.add_argument("a")
    pd.add_argument("b")
    pd.add_argument("--json", action="store_true")
    pd.add_argument("--export", help="write changed ranges as a regions JSON file")
    pd.add_argument("--merge-gap", type=int, default=16)
    pd.add_argument("--limit", type=int, default=40)
    pd.set_defaults(func=cmd_diff)

    # demo
    pdm = sub.add_parser("demo", help="write the bundled synthetic demo ROM")
    pdm.add_argument("output", nargs="?", default="demo.z64")
    pdm.add_argument("--overwrite", action="store_true")
    pdm.set_defaults(func=cmd_demo)

    # hex
    ph = sub.add_parser("hex", help="hex dump, or interpret bytes at an offset")
    ph.add_argument("input")
    ph.add_argument("--offset", default="0", help="start offset (hex or dec)")
    ph.add_argument("--length", default=None, help="bytes to dump (default 256)")
    ph.add_argument("--width", type=int, default=16)
    ph.add_argument("--interpret", action="store_true",
                    help="show int/float/pointer interpretations at --offset")
    ph.add_argument("--endianness", choices=["little", "big"], default="little")
    ph.set_defaults(func=cmd_hex)

    # search
    ps = sub.add_parser("search", help="search for bytes / ascii / int / float")
    ps.add_argument("input")
    g = ps.add_mutually_exclusive_group()
    g.add_argument("--bytes", help="hex pattern, e.g. deadbeef")
    g.add_argument("--ascii", help="ascii text")
    g.add_argument("--int", type=lambda s: int(s, 0), help="integer value")
    g.add_argument("--float", type=float, help="float value")
    ps.add_argument("--size", type=int, default=4, choices=[1, 2, 4, 8],
                    help="int size in bytes")
    ps.add_argument("--signed", action="store_true")
    ps.add_argument("--double", action="store_true", help="treat --float as float64")
    ps.add_argument("--tol", type=float, default=1e-3, help="float match tolerance")
    ps.add_argument("--endianness", choices=["little", "big"], default="little")
    ps.add_argument("--limit", type=int, default=100)
    ps.add_argument("--json", action="store_true")
    ps.set_defaults(func=cmd_search)

    # strings
    pstr = sub.add_parser("strings", help="list printable ASCII strings")
    pstr.add_argument("input")
    pstr.add_argument("--min-len", type=int, default=4)
    pstr.add_argument("--limit", type=int, default=500)
    pstr.add_argument("--json", action="store_true")
    pstr.set_defaults(func=cmd_strings)

    # entropy
    pe = sub.add_parser("entropy", help="entropy sparkline across the file")
    pe.add_argument("input")
    pe.add_argument("--blocks", type=int, default=64)
    pe.add_argument("--json", action="store_true")
    pe.set_defaults(func=cmd_entropy)

    # model (semantic)
    pm = sub.add_parser("model", help="semantic corruption of a float vertex/anim array")
    pm.add_argument("input")
    pm.add_argument("-o", "--output")
    pm.add_argument("--range", type=_parse_range, metavar="START:END")
    pm.add_argument("--region", help="named region from the matched profile")
    pm.add_argument("--profile", help="force a profile id")
    pm.add_argument("--platform")
    pm.add_argument("--op", default="scale",
                    choices=["scale", "stretch", "displace", "mirror", "flatten", "reverse"])
    pm.add_argument("--stride", type=int, default=12, help="bytes per element (default 12)")
    pm.add_argument("--components", help="comma byte-offsets of floats in an element, e.g. 0,4,8")
    pm.add_argument("-x", type=float, default=0.4, help="X (component 0) strength")
    pm.add_argument("-y", type=float, default=0.4, help="Y (component 1) strength")
    pm.add_argument("-z", type=float, default=0.4, help="Z (component 2) strength")
    pm.add_argument("--seed", default="0")
    pm.add_argument("--endianness", choices=["little", "big"], default=None)
    pm.add_argument("--allow-nan", action="store_true")
    pm.add_argument("--no-repair", action="store_true")
    pm.add_argument("--overwrite", action="store_true")
    pm.add_argument("-q", "--quiet", action="store_true")
    pm.set_defaults(func=cmd_model)

    # batch
    pb = sub.add_parser("batch", help="generate many corrupted variants across seeds")
    pb.add_argument("input")
    pb.add_argument("-o", "--outdir", default="corruptions")
    pb.add_argument("--count", type=int, default=10)
    pb.add_argument("--seed", action="append", default=[], help="explicit seed (repeatable)")
    pb.add_argument("--seed-prefix", default="")
    pb.add_argument("--start-seed", type=int, default=0)
    pb.add_argument("-t", "--target", action="append", default=[])
    pb.add_argument("-m", "--type", action="append", default=[])
    pb.add_argument("--profile")
    pb.add_argument("--no-auto", action="store_true")
    pb.add_argument("--density", type=float, default=0.002)
    pb.add_argument("--magnitude", type=float, default=0.35)
    pb.add_argument("--no-repair", action="store_true")
    pb.add_argument("--manifest", help="write a JSON manifest of seed->file->summary")
    pb.add_argument("-q", "--quiet", action="store_true")
    pb.set_defaults(func=cmd_batch)

    # sweep
    psw = sub.add_parser("sweep", help="guided-fuzz region sweep (needs an emulator)")
    psw.add_argument("input")
    psw.add_argument("--launch", metavar="CMD", help='emulator command, e.g. "retroarch {ROM}"')
    psw.add_argument("--block-size", type=lambda s: int(s, 0), default=0x1000)
    psw.add_argument("--trials", type=int, default=1)
    psw.add_argument("--boot-time", type=float, default=6.0)
    psw.add_argument("--timeout", type=float, default=20.0)
    psw.add_argument("--density", type=float, default=0.05)
    psw.add_argument("--magnitude", type=float, default=0.6)
    psw.add_argument("--critical-threshold", type=float, default=0.5)
    psw.add_argument("--min-safety", type=float, default=0.9,
                     help="min block safety to treat as corruptible (for --export-profile)")
    psw.add_argument("--export-profile", metavar="PATH.json",
                     help="write a draft profile of boot-survivable regions")
    psw.add_argument("--profile-id", default="swept", help="id for --export-profile")
    psw.add_argument("--no-repair", action="store_true")
    psw.add_argument("--report", help="write the heat map as JSON")
    psw.add_argument("--json", action="store_true")
    psw.add_argument("-q", "--quiet", action="store_true")
    psw.set_defaults(func=cmd_sweep)

    # emu (emulator presets)
    pemu = sub.add_parser("emu", help="manage emulator launch presets")
    esub = pemu.add_subparsers(dest="emu_action")
    e_list = esub.add_parser("list", help="list presets")
    e_list.set_defaults(func=cmd_emu)
    e_add = esub.add_parser("add", help="add/update a preset")
    e_add.add_argument("name")
    e_add.add_argument("command", help='launch command, e.g. "retroarch {ROM}"')
    e_add.add_argument("--working-dir")
    e_add.add_argument("--timeout", type=float)
    e_add.add_argument("--default", action="store_true", help="make this the default")
    e_add.set_defaults(func=cmd_emu)
    e_rm = esub.add_parser("remove", help="remove a preset")
    e_rm.add_argument("name")
    e_rm.set_defaults(func=cmd_emu)
    e_def = esub.add_parser("default", help="set the default preset")
    e_def.add_argument("name")
    e_def.set_defaults(func=cmd_emu)
    pemu.set_defaults(func=cmd_emu)

    # texture
    pt = sub.add_parser("texture", help="semantic texture corruption (channels / palette)")
    pt.add_argument("input")
    pt.add_argument("-o", "--output")
    pt.add_argument("--range", type=_parse_range, required=True, metavar="START:END")
    pt.add_argument("--op", default="channel_swap",
                    choices=["channel_shift", "channel_swap", "channel_scale",
                             "invert", "palette_rotate", "palette_shuffle"])
    pt.add_argument("--format", default="rgba8888",
                    choices=["rgba8888", "rgb888", "rgba5551", "rgb565"])
    pt.add_argument("--endianness", choices=["little", "big"], default=None)
    pt.add_argument("--strength", type=float, default=0.5)
    pt.add_argument("-a", type=int, default=0, help="channel A for swap")
    pt.add_argument("-b", type=int, default=2, help="channel B for swap")
    pt.add_argument("--channel", type=int, default=-1, help="target channel (-1 = all)")
    pt.add_argument("--rotate-by", type=int, default=1, help="palette_rotate amount")
    pt.add_argument("--entry-size", type=int, default=0,
                    help="palette entry bytes (default = format bpp / 2)")
    pt.add_argument("--seed", default="0")
    pt.add_argument("--no-repair", action="store_true")
    pt.add_argument("--overwrite", action="store_true")
    pt.add_argument("-q", "--quiet", action="store_true")
    pt.set_defaults(func=cmd_texture)

    # mkprofile
    pmp = sub.add_parser("mkprofile", help="author a new game profile from a ROM")
    pmp.add_argument("input")
    pmp.add_argument("--id", required=True, help="profile id")
    pmp.add_argument("--name", help="human-readable name")
    pmp.add_argument("--platform", help="platform id (default: auto-detect)")
    pmp.add_argument("--region", action="append", default=[],
                     metavar="NAME:CAT:START:END[:ENDIAN[:DTYPE]]",
                     help="region spec (repeatable)")
    pmp.add_argument("--from-diff", metavar="OTHER",
                     help="seed regions from ranges that differ vs OTHER file")
    pmp.add_argument("--merge-gap", type=int, default=16)
    pmp.add_argument("--notes", default="")
    pmp.add_argument("-o", "--output", help="output JSON path (default <id>.json)")
    pmp.add_argument("--overwrite", action="store_true")
    pmp.add_argument("-q", "--quiet", action="store_true")
    pmp.set_defaults(func=cmd_mkprofile)

    # addregion
    par = sub.add_parser("addregion", help="append a region to a profile JSON")
    par.add_argument("profile")
    par.add_argument("--name", required=True)
    par.add_argument("--category", default="unknown")
    par.add_argument("--range", type=_parse_range, required=True, metavar="START:END")
    par.add_argument("--endianness", choices=["little", "big"], default=None)
    par.add_argument("--data-type", default=None)
    par.add_argument("--tag", action="append", default=[])
    par.add_argument("-q", "--quiet", action="store_true")
    par.set_defaults(func=cmd_addregion)

    # evolve
    pev = sub.add_parser("evolve", help="interactive keep/reject/regenerate evolution")
    pev.add_argument("input")
    pev.add_argument("-o", "--output")
    pev.add_argument("-t", "--target", action="append", default=[])
    pev.add_argument("-m", "--type", action="append", default=[])
    pev.add_argument("--profile")
    pev.add_argument("--platform")
    pev.add_argument("--density", type=float, default=0.005)
    pev.add_argument("--magnitude", type=float, default=0.4)
    pev.add_argument("--intensity", type=float, default=None)
    pev.add_argument("--seed-prefix", default="gen")
    pev.add_argument("--launch", metavar="CMD", help="emulator command with {ROM}")
    pev.add_argument("--no-repair", action="store_true")
    pev.add_argument("--save-project", metavar="PATH.ccproject")
    pev.set_defaults(func=cmd_evolve)

    # scan
    psc = sub.add_parser("scan", help="experimental structure guesses")
    psc.add_argument("input")
    psc.add_argument("--floats", action="store_true", help="only vertex-like floats")
    psc.add_argument("--pointers", action="store_true", help="only pointer candidates")
    psc.add_argument("--strings", action="store_true", help="only strings")
    psc.add_argument("--endianness", choices=["little", "big"], default="little")
    psc.add_argument("--limit", type=int, default=40)
    psc.add_argument("--json", action="store_true")
    psc.set_defaults(func=cmd_scan)

    return p


def _add_corrupt_args(pc: argparse.ArgumentParser) -> None:
    pc.add_argument("input")
    pc.add_argument("-o", "--output", help="output path (default: <name>_corrupt_<seed>)")
    pc.add_argument("--profile", help="force a profile id")
    pc.add_argument("--no-auto", action="store_true",
                    help="do not auto-identify a profile by hash")
    pc.add_argument("--platform", help=f"force a platform ({', '.join(platforms.available())})")
    pc.add_argument("-t", "--target", action="append", default=[],
                    help="category/tag to corrupt (repeatable)")
    pc.add_argument("--range", action="append", type=_parse_range, default=[],
                    metavar="START:END", help="raw offset range to corrupt (repeatable)")
    pc.add_argument("--protect", action="append", type=_parse_range, default=[],
                    metavar="START:END", help="extra protected range (repeatable)")
    pc.add_argument("--density", type=float, default=0.002,
                    help="fraction of mutable bytes to touch (default 0.002)")
    pc.add_argument("--magnitude", type=float, default=0.35,
                    help="0..1 strength of each mutation (default 0.35)")
    pc.add_argument("--intensity", type=float, default=None,
                    help="0..1 convenience slider (overrides density+magnitude)")
    pc.add_argument("--seed", default="0", help="deterministic seed (string or int)")
    pc.add_argument("-m", "--type", action="append", default=[],
                    metavar="TYPE", help=f"mutation type (repeatable): {', '.join(ALL_TYPES)}")
    pc.add_argument("--clamp", action="store_true",
                    help="clamp byte/int overflow instead of wrapping")
    pc.add_argument("--allow-nan", action="store_true",
                    help="allow float mutations to produce NaN/Inf")
    pc.add_argument("--block-size", type=int, default=None)
    pc.add_argument("--endianness", choices=["little", "big"], default=None)
    pc.add_argument("--no-repair", action="store_true",
                    help="do not repair platform checksums")
    pc.add_argument("--overwrite", action="store_true")
    pc.add_argument("--save-project", metavar="PATH.ccproject")
    pc.add_argument("--save-seed", metavar="PATH.ccseed")
    pc.add_argument("--report", metavar="PATH.json", help="write full mutation log")
    pc.add_argument("--launch", metavar="CMD",
                    help='launch an emulator, e.g. "retroarch {ROM}"')
    pc.add_argument("--limit", type=int, default=None, help="history lines to print")
    pc.add_argument("--dry-run", action="store_true",
                    help="compute and report the plan without writing the output")
    pc.add_argument("-q", "--quiet", action="store_true")
    pc.add_argument("-v", "--verbose", action="store_true", help="print mutation history")


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Convenience: allow `ccorrupt game.z64 --seed ...` (implicit `corrupt`).
    if argv and argv[0] not in SUBCOMMANDS and not argv[0].startswith("-"):
        argv = ["corrupt"] + argv

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except BrokenPipeError:
        # Downstream (e.g. `| head`) closed the pipe; exit quietly.
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0
    except KeyboardInterrupt:  # pragma: no cover
        _eprint("interrupted")
        return 130
    except FileNotFoundError as exc:
        _eprint(f"error: {exc}")
        return 2
    except (ValueError, FileExistsError) as exc:
        _eprint(f"error: {exc}")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
