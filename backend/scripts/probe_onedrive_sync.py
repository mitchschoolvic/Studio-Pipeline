#!/usr/bin/env python3
"""
Probe OneDrive SyncState extended attribute codes under a directory.

Usage:
  python backend/scripts/probe_onedrive_sync.py --root \
    "/Users/mitch.anderson/Library/CloudStorage/OneDrive-Haileybury" \
    [--ext .mp4 .mov .mkv .m4v] [--max 1000]

Reports:
  - Count by SyncState code and label
  - Sample file paths per code
  - JSON summary (optional via --json)

Works on macOS. Attempts to use the Python xattr module if available,
falls back to invoking the system `xattr` command.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Optional, Tuple


# Known/assumed codes (to be validated by probe)
STATUS_MAP = {
    0: "Unknown",
    1: "Synced/UpToDate",
    2: "Syncing",
    3: "Error",
    # 4-8 unknown/reserved in our context
    9: "Online-only (placeholder)",
}

ATTR_NAME = "com.microsoft.OneDrive.SyncState"


def _get_sync_state_xattr_py(file_path: str) -> Optional[int]:
    try:
        import xattr  # type: ignore

        data: bytes = xattr.getxattr(file_path, ATTR_NAME)  # may raise
        if not data:
            return None
        # OneDrive stores an integer value, little-endian
        return int.from_bytes(data, byteorder="little", signed=False)
    except Exception:
        return None


def _get_sync_state_xattr_cmd(file_path: str) -> Optional[int]:
    try:
        # Use macOS xattr CLI to read raw value; -p prints attribute value
        res = subprocess.run(
            ["xattr", "-p", ATTR_NAME, file_path],
            capture_output=True,
            text=False,
            check=False,
        )
        if res.returncode != 0:
            return None
        data = res.stdout
        if not data:
            return None
        return int.from_bytes(data, byteorder="little", signed=False)
    except Exception:
        return None


def get_onedrive_sync_state(file_path: str) -> Optional[Tuple[int, str]]:
    """Return (code, label) for OneDrive SyncState, or None if unavailable."""
    code = _get_sync_state_xattr_py(file_path)
    if code is None:
        code = _get_sync_state_xattr_cmd(file_path)
    if code is None:
        return None
    label = STATUS_MAP.get(code, f"Unknown ({code})")
    return code, label


def is_hidden_dotfile(p: Path) -> bool:
    try:
        return p.name.startswith(".")
    except Exception:
        return False


def _list_attrs_cmd(file_path: str) -> list[str]:
    try:
        res = subprocess.run(["xattr", "-l", file_path], capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return []
        names = []
        for line in res.stdout.splitlines():
            if ":" in line:
                names.append(line.split(":", 1)[0].strip())
        return names
    except Exception:
        return []


def probe(root: str, allow_exts: list[str] | None, max_files: int, tally_attrs: bool = False) -> dict:
    root_path = Path(root).expanduser()
    if not root_path.exists():
        raise SystemExit(f"Root does not exist: {root_path}")

    counts: dict[str, int] = defaultdict(int)
    samples: dict[str, list[str]] = defaultdict(list)
    scanned = 0
    examined = 0
    attr_name_counts: dict[str, int] = defaultdict(int)

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Skip hidden folders like .tmp, .Trash, .DS_Store containers
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]

        for fn in filenames:
            if scanned >= max_files:
                break
            p = Path(dirpath) / fn
            if is_hidden_dotfile(p):
                continue
            if allow_exts:
                if p.suffix.lower() not in allow_exts:
                    continue

            examined += 1
            fp = str(p)
            state = get_onedrive_sync_state(fp)
            key: str
            if state is None:
                key = "no-attr"
            else:
                code, label = state
                key = f"{code}:{label}"

            counts[key] += 1
            if len(samples[key]) < 5:
                samples[key].append(fp)
            if tally_attrs:
                for name in _list_attrs_cmd(fp):
                    attr_name_counts[name] += 1
            scanned += 1

        if scanned >= max_files:
            break

    result = {
        "root": str(root_path),
        "scanned": scanned,
        "examined": examined,
        "counts": dict(counts),
        "samples": samples,
    }
    if tally_attrs:
        result["attr_name_counts"] = dict(attr_name_counts)
    return result


def main():
    ap = argparse.ArgumentParser(description="Probe OneDrive SyncState codes")
    ap.add_argument("--root", required=True, help="Root folder to scan")
    ap.add_argument(
        "--ext",
        nargs="*",
        default=[".mp4", ".mov", ".mkv", ".m4v"],
        help="File extensions to include (default: common video)",
    )
    ap.add_argument("--max", type=int, default=1000, help="Max files to examine")
    ap.add_argument("--json", action="store_true", help="Print JSON summary")
    ap.add_argument("--tally-attrs", action="store_true", help="Also tally xattr names found")
    args = ap.parse_args()

    summary = probe(args.root, args.ext, args.max, tally_attrs=args.tally_attrs)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Root: {summary['root']}")
        print(f"Examined: {summary['examined']} files, Included: {summary['scanned']} files")
        print("\nCounts by code:")
        for key, cnt in sorted(summary["counts"].items(), key=lambda x: x[0]):
            print(f"  {key:24s}  {cnt}")
        print("\nSamples:")
        for key, items in summary["samples"].items():
            for it in items:
                print(f"  {key:24s}  {it}")


if __name__ == "__main__":
    main()
