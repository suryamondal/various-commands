#!/usr/bin/env python3
"""claude-unpacker.py

Restore a tarball produced by claude-packer.py on this machine.

For each entry in the manifest, the source dir $HOME/<relpath> must exist
(real, mounted, or symlinked) on this machine so the script can resolve the
physical path and compute the correct ~/.claude/projects/<encoded>/ slot.

Run with: python3 claude-unpacker.py [-h] [--force | --rename-existing] ARCHIVE
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path


def encode_path(absolute_path: Path) -> str:
    words = re.split(r'[^a-zA-Z0-9]+', str(absolute_path))
    return '-' + '-'.join(w for w in words if w)


def relpath_to_key(relpath: str) -> str:
    return relpath.replace("/", "-")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="claude-unpacker.py",
        description=(
            "Restore a Claude Code chat-history archive produced by "
            "claude-packer.py on this machine. The encoded "
            "~/.claude/projects/<...> path is recomputed from the resolved "
            "physical path of $HOME/<relpath> on this machine, so the "
            "archive is portable across different home dirs, mounts, and "
            "symlinks."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Conflict policy:\n"
            "  default            skip-and-warn if a target already exists\n"
            "  --force            overwrite existing targets\n"
            "  --rename-existing  move an existing target aside to\n"
            "                     <target>.bak-<timestamp> before restoring\n"
        ),
    )
    parser.add_argument(
        "archive",
        type=Path,
        help="path to the .tar.gz produced by claude-packer.py",
    )
    conflict = parser.add_mutually_exclusive_group()
    conflict.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing targets",
    )
    conflict.add_argument(
        "--rename-existing",
        action="store_true",
        help="move an existing target aside to <target>.bak-<ts> "
             "before restoring",
    )
    return parser.parse_args()


def prepare_target(target: Path, *, force: bool, rename: bool, ts: str) -> bool:
    """Apply conflict policy. Return True to proceed with copy, False to skip."""
    if not target.exists():
        return True
    if force:
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
        return True
    if rename:
        backup = target.with_name(f"{target.name}.bak-{ts}")
        target.rename(backup)
        print(f"    moved existing -> {backup}")
        return True
    print(f"    [skip] target exists: {target}")
    return False


def safe_extract(tar: tarfile.TarFile, dst: Path) -> None:
    """Extract using the 'data' filter where available (Python 3.12+)."""
    try:
        tar.extractall(dst, filter="data")
    except TypeError:
        tar.extractall(dst)


def main() -> int:
    args = parse_args()

    if not args.archive.is_file():
        print(f"ERROR: archive not found: {args.archive}", file=sys.stderr)
        return 1

    home = Path.home()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    with tempfile.TemporaryDirectory() as work_str:
        work = Path(work_str)
        try:
            with tarfile.open(args.archive, "r:gz") as tar:
                safe_extract(tar, work)
        except tarfile.TarError as exc:
            print(f"ERROR: failed to extract archive: {exc}", file=sys.stderr)
            return 1

        top_dirs = [p for p in work.iterdir() if p.is_dir()]
        if len(top_dirs) != 1:
            print(f"ERROR: expected one top-level directory in archive, "
                  f"found {len(top_dirs)}", file=sys.stderr)
            return 1
        root_dir = top_dirs[0]

        manifest_path = root_dir / "manifest.json"
        if not manifest_path.is_file():
            print("ERROR: manifest.json missing in archive", file=sys.stderr)
            return 1

        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as exc:
            print(f"ERROR: failed to parse manifest.json: {exc}",
                  file=sys.stderr)
            return 1

        restored_projects = 0
        restored_local = 0
        skipped = 0
        missing_src = 0

        for entry in manifest.get("entries", []):
            relpath = entry["relpath"]
            has_projects = entry.get("has_projects", False)
            has_local = entry.get("has_local", False)

            src_dir = home / relpath
            if not src_dir.is_dir():
                print(f"  [missing] {relpath} -- {src_dir} does not exist on "
                      f"this machine; skipping")
                missing_src += 1
                continue

            phys = src_dir.resolve()
            encoded = encode_path(phys)
            key = relpath_to_key(relpath)

            print(f"  [restore] {relpath}")

            if has_projects:
                proj_src = root_dir / "projects" / key
                proj_dst = home / ".claude" / "projects" / encoded
                if proj_src.is_dir():
                    proj_dst.parent.mkdir(parents=True, exist_ok=True)
                    if prepare_target(proj_dst, force=args.force,
                                      rename=args.rename_existing, ts=ts):
                        shutil.copytree(proj_src, proj_dst, symlinks=False)
                        restored_projects += 1
                        print(f"    chat history -> {proj_dst}")
                    else:
                        skipped += 1

            if has_local:
                local_src = root_dir / "local" / relpath / ".claude"
                local_dst = src_dir / ".claude"
                if local_src.is_dir():
                    if prepare_target(local_dst, force=args.force,
                                      rename=args.rename_existing, ts=ts):
                        shutil.copytree(local_src, local_dst, symlinks=False)
                        restored_local += 1
                        print(f"    local .claude/ -> {local_dst}")
                    else:
                        skipped += 1

        print()
        print(f"Restored: {restored_projects} chat histories, "
              f"{restored_local} local .claude/")
        if skipped:
            print(f"Skipped:  {skipped} (target exists -- rerun with "
                  f"--force or --rename-existing)")
        if missing_src:
            print(f"Missing:  {missing_src} source dir(s) on this machine")

    return 0


if __name__ == "__main__":
    sys.exit(main())
