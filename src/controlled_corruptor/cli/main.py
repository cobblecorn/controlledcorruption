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
from ..core import binary as binmod
from ..core.diff import diff_summary
from ..core.pipeline import corrupt as run_corrupt
from ..core.project import CorruptionProject, CorruptionSeed
from ..core.regions import Region, parse_offset
from ..core.settings import ALL_TYPES, DEFAULT_TYPES, MutationSettings
from ..profiles import ProfileLibrary
from .. import platforms

SUBCOMMANDS = {"info", "corrupt", "apply", "profiles", "diff", "demo"}


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
    if os.path.abspath(out_path) == os.path.abspath(args.input) and not args.overwrite:
        _eprint("error: output would overwrite the source; refusing "
                "(choose --output or pass --overwrite)")
        return 2
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

    # Optional emulator launch.
    if args.launch:
        from ..emulator import CustomCommandEmulator

        emu = CustomCommandEmulator(args.launch)
        _eprint(f"[INFO] Launching: {' '.join(emu.build_args(out_path))}")
        emu.launch(out_path)

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
