#!/usr/bin/env python3
"""claude-packer.py

Pack Claude Code chat history (~/.claude/projects/<encoded>) and per-project
local .claude/ directories for selected sources into a portable tar.gz.

All sources are $HOME-relative. The encoded form of ~/.claude/projects/<...>
is derived from the resolved physical path (`Path.resolve()`) at pack time
and again at unpack time, so the archive survives different home dirs, mount
points, and symlinks across machines.

Run with: python3 claude-packer.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

# ── sources to pack ──────────────────────────────────────────────────────────
# $HOME-relative paths. Edit this list to add/remove projects.
SOURCES: list[str] = [
    "products/fessdyne-futura/ingest/mems-arrays/v3/firmware",
    "products/fessdyne-futura/ingest/mems-arrays/v3/hardware",
    "Downloads/tmp/various-commands",
]

OUT_DIR = Path.home() / "Downloads"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def encode_path(absolute_path: Path) -> str:
    return str(absolute_path).replace("/", "-")


def relpath_to_key(relpath: str) -> str:
    return relpath.replace("/", "-")


def main() -> int:
    home = Path.home()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_name = f"claude-backup-{timestamp}"

    with tempfile.TemporaryDirectory() as staging_str:
        staging = Path(staging_str)
        root = staging / archive_name
        (root / "projects").mkdir(parents=True)
        (root / "local").mkdir(parents=True)

        manifest = {
            "version": 1,
            "created_at": datetime.now().astimezone().isoformat(),
            "packed_from_home": str(home),
            "packed_from_phys_home": str(home.resolve()),
            "entries": [],
        }

        total = 0
        packed_projects = 0
        packed_local = 0

        for relpath in SOURCES:
            total += 1
            src_dir = home / relpath
            if not src_dir.is_dir():
                print(f"  [skip] {relpath} -- {src_dir} does not exist")
                continue

            phys = src_dir.resolve()
            encoded = encode_path(phys)
            key = relpath_to_key(relpath)

            has_projects = False
            has_local = False

            proj_src = CLAUDE_PROJECTS_DIR / encoded
            if proj_src.is_dir():
                shutil.copytree(proj_src, root / "projects" / key,
                                symlinks=False)
                has_projects = True
                packed_projects += 1

            local_src = src_dir / ".claude"
            if local_src.is_dir():
                local_parent = root / "local" / relpath
                local_parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(local_src, local_parent / ".claude",
                                symlinks=False)
                has_local = True
                packed_local += 1

            if not has_projects and not has_local:
                print(f"  [skip] {relpath} -- no chat history and "
                      f"no local .claude/")
                continue

            manifest["entries"].append({
                "relpath": relpath,
                "has_projects": has_projects,
                "has_local": has_local,
            })
            print(f"  [pack] {relpath} "
                  f"(projects={int(has_projects)}, local={int(has_local)})")

        (root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        archive_path = OUT_DIR / f"{archive_name}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(root, arcname=archive_name)

        print()
        print(f"Packed {packed_projects}/{total} project chats, "
              f"{packed_local}/{total} local .claude/.")
        print(f"Archive: {archive_path}")
        print()
        print("NOTE: This tarball contains chat transcripts and local "
              "settings.")
        print("      Treat it as private data.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
