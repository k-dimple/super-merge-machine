#!/usr/bin/env python3
"""
Merges multiple documentation sources (GitHub/Discourse) into a Sphinx-ready set
of .md/.rst files, including a root index that groups sources by optional
"category" and then by "dest_dir".

New features (May 2025)
=======================
1. Recursive include support: Whenever a file cloned from a GitHub repo
   contains an `.. include::` or `.. literalinclude::` directive,
   the referenced file (recursively) is copied into the local documentation
   tree so that the directive resolves when the docs are built locally.
2. `reuse/` aggregation: For every GitHub repo that contains `docs/reuse/`
     with `links.txt` and/or `substitutions.txt`,
     the corresponding files from all repos are joined under ``reuse/``.

The rest of the behaviour is unchanged.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

import requests
import yaml
from git import Repo

###############################################################################
# Helpers                                                                     #
###############################################################################

# Global accumulator for reuse fragments
_REUSE_CACHE: Dict[str, List[Tuple[str, List[str]]]] = {"links": [], "substitutions": []}

_INCLUDE_RE = re.compile(r"^\s*\.\.\s+(?:literal)?include::\s+(.+?)\s*$")

###############################################################################
# Low-level file helpers                                                      #
###############################################################################

def copy_tree(src: str | Path, dest: str | Path) -> None:
    """Recursively copy *src* to *dest* (existing files are overwritten)."""
    src = Path(src)
    dest = Path(dest)

    if not dest.exists():
        shutil.copytree(src, dest)
        return

    for root, dirs, files in os.walk(src):
        rel_root = Path(root).relative_to(src)
        dest_root = dest / rel_root
        dest_root.mkdir(parents=True, exist_ok=True)
        for f in files:
            shutil.copy2(Path(root) / f, dest_root / f)


def copy_file(src_file: str | Path, dst_file: str | Path) -> None:
    """Copy a single file, ensuring parent directories exist."""
    dst_file = Path(dst_file)
    dst_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_file, dst_file)

###############################################################################
# include:: handling                                                          #
###############################################################################

def _scan_includes(file_path: Path) -> List[str]:
    """Return a list of *relative* paths referenced by ``.. include::`` in *file_path*."""
    if file_path.suffix.lower() not in {".rst", ".md"}:
        return []

    includes: List[str] = []
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                m = _INCLUDE_RE.match(line)
                if m:
                    includes.append(m.group(1).strip())
    except FileNotFoundError:
        pass  # ignore broken include for now
    return includes


def _copy_includes_recursive(
    source_root: Path,
    dest_root: Path,
    including_file: Path,
    seen: Set[Path],
) -> None:
    """Recursively copy all include targets needed by *including_file*.

    *source_root* is the repo folder; *dest_root* is the local copy location.
    *including_file* must already have been copied to *dest_root*.
    """
    for rel_inc in _scan_includes(including_file):
        repo_inc_path = (source_root / including_file.relative_to(dest_root).parent / rel_inc).resolve()
        local_inc_path = dest_root / including_file.relative_to(dest_root).parent / rel_inc

        repo_inc_path = repo_inc_path.resolve()
        local_inc_path = local_inc_path.resolve()

        if repo_inc_path in seen:
            continue
        if not repo_inc_path.exists():
            print(f"[include] Warning: {rel_inc} referenced from {including_file} not found in repo.")
            continue

        seen.add(repo_inc_path)
        copy_file(repo_inc_path, local_inc_path)
        _copy_includes_recursive(source_root, dest_root, local_inc_path, seen)

###############################################################################
# reuse/ aggregation                                                          #
###############################################################################

def _collect_reuse_fragments(repo_label: str, repo_root: Path) -> None:
    """Read links.txt / substitutions.txt under *repo_root*/docs/reuse/ and cache them."""
    reuse_dir = repo_root / "docs" / "reuse"
    if not reuse_dir.is_dir():
        return

    for kind in ("links", "substitutions"):
        txt = reuse_dir / f"{kind}.txt"
        if txt.is_file():
            with txt.open("r", encoding="utf-8", errors="ignore") as fh:
                lines = [ln.rstrip("\n") for ln in fh if ln.strip()]  # keep non-blank lines
            if lines:
                _REUSE_CACHE[kind].append((repo_label, lines))


def _write_reuse(output_dir: Path) -> None:
    dest_reuse = output_dir / "reuse"
    if not any(_REUSE_CACHE.values()):
        return  # nothing to write

    dest_reuse.mkdir(parents=True, exist_ok=True)

    for kind in ("links", "substitutions"):
        if not _REUSE_CACHE[kind]:
            continue
        out_file = dest_reuse / f"{kind}.txt"
        with out_file.open("w", encoding="utf-8") as fh:
            for label, lines in _REUSE_CACHE[kind]:
                fh.write(f".. {label}:\n")
                fh.write("\n".join(lines))
                fh.write("\n\n")  # blank line separator

###############################################################################
# GitHub-specific processing                                                  #
###############################################################################

def _clone_repo_shallow(repo_url: str, branch: str, clone_to: Path) -> None:
    print(f"[git] Cloning {repo_url}@{branch} → {clone_to} (depth 1)")
    Repo.clone_from(repo_url, to_path=str(clone_to), branch=branch, multi_options=["--depth=1"])


def _gather_github_top_level(dest_dir: Path) -> List[str]:
    for idx in ("index.md", "index.rst"):
        if (dest_dir / idx).is_file():
            return [idx]
    return [f.name for f in dest_dir.iterdir() if f.is_file() and f.suffix in {".md", ".rst"}]


def handle_github_source(src: Dict, full_path: str | Path) -> List[str]:
    repo_url: str = src["repo_url"]
    branch: str = src.get("branch", "main")
    doc_subdir: str = src.get("doc_subdir", "")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        _clone_repo_shallow(repo_url, branch, tmpdir)

        src_subdir = tmpdir / doc_subdir
        if not src_subdir.exists():
            print(f"[git] Warning: subdir '{doc_subdir}' not found in {repo_url}.")
            Path(full_path).mkdir(parents=True, exist_ok=True)
            return []

        # Collect reuse/ first using repo name as label (root-level docs/reuse/)
        repo_label = src.get("reuse_label") or Path(repo_url).stem  # default label
        _collect_reuse_fragments(repo_label, tmpdir)

        dest_root = Path(full_path)
        dest_root.mkdir(parents=True, exist_ok=True)

        include_seen: Set[Path] = set()
        doc_files: List[str] = []

        if "pages" in src:  # selective copy
            for page in src["pages"]:
                in_repo = src_subdir / page["doc_file"]
                if not in_repo.is_file():
                    print(f"[git] Warning: '{page['doc_file']}' missing in repo; skipping.")
                    continue
                local_name = page.get("filename") or in_repo.name
                out_file = dest_root / local_name
                copy_file(in_repo, out_file)
                doc_files.append(local_name)

                _copy_includes_recursive(src_subdir, dest_root, out_file, include_seen)
        else:  # full copy of doc_subdir
            copy_tree(src_subdir, dest_root)
            for rst in dest_root.rglob("*.rst"):
                _copy_includes_recursive(src_subdir, dest_root, rst, include_seen)
            doc_files.extend(_gather_github_top_level(dest_root))

        return doc_files

###############################################################################
# Discourse (unchanged)                                                       #
###############################################################################

def fetch_discourse_topic(base_url: str, topic_id: int, title: str) -> str:
    url = f"{base_url}/raw/{topic_id}"
    print(f"[disc] Fetch {url}")
    resp = requests.get(url)
    resp.raise_for_status()

    content = f"# {title}\n\n" + resp.text
    cutoff_index = content.find("-------------------------")
    if cutoff_index != -1:
        content = content[:cutoff_index].rstrip()
    return content


def create_discourse_index(directory: Path, section_name: str, pages: List[Dict]) -> str | None:
    if not directory.is_dir():
        return None

    lines: List[str] = [f"# {section_name}\n\n"]
    for page in pages:
        lines.append(f"## {page['title']}\n\n")
        lines.append("```{toctree}\n:maxdepth: 1\n\n")
        base, _ = os.path.splitext(page["filename"])
        lines.append(f"{base}\n")
        lines.append("```\n\n")

    index_path = directory / "index.md"
    with index_path.open("w", encoding="utf-8") as f:
        f.writelines(lines)
    return "index.md"


def handle_discourse_source(src: Dict, full_path: str | Path) -> List[str]:
    dest = Path(full_path)
    dest.mkdir(parents=True, exist_ok=True)
    for p in src.get("pages", []):
        md_text = fetch_discourse_topic(src["discourse_url"], p["topic_id"], p["title"])
        fname = p.get("filename", f"{p['topic_id']}.md")
        with (dest / fname).open("w", encoding="utf-8") as fmd:
            fmd.write(md_text)
    idx = create_discourse_index(dest, src["name"], src["pages"])
    return [idx] if idx else []


###############################################################################
# Public API                                                                  #
###############################################################################

TOC_BUILDERS = {
    "github": lambda n, d, f: [f"{d}/{df}" if d else df for df in f]
    if len(f) > 1
    else [f"{n} <{d}/{f[0]}>" if d else f"{n} <{f[0]}>"],
    "discourse": lambda n, d, f: [
        f"{n} <{d}/{df}>" if d else f"{n} <{df}>" for df in f
    ],
}

SOURCE_HANDLERS = {
    "github": handle_github_source,
    "discourse": handle_discourse_source,
}

###############################################################################
# Index generation (unchanged)                                                #
###############################################################################


def build_all_indices(output_dir: Path, source_entries: List[Dict]) -> None:
    cat_map: Dict[str | None, List[Dict]] = defaultdict(list)
    for e in source_entries:
        cat_map[e.get("category")].append(e)

    root_index = output_dir / "index.md"
    lines = ["# Related Technologies\n\n"]

    categories = sorted([c for c in cat_map if c is not None])
    if categories:
        lines.append("```{toctree}\n:maxdepth: 1\n\n")
        for cat in categories:
            lines.append(f"{cat}/index\n")
        lines.append("\n```\n\n")

    # Sources without category
    for src in cat_map.get(None, []):
        if not src["docs"]:
            continue
        builder = TOC_BUILDERS.get(src["type"])
        if not builder:
            continue
        lines.append("```{toctree}\n:maxdepth: 1\n\n")
        lines.extend(
            [ln + "\n" for ln in builder(src["name"], src["dest_dir"], src["docs"])]
        )
        lines.append("\n```\n\n")

    with root_index.open("w", encoding="utf-8") as f:
        f.writelines(lines)

    # Category sub‑indices
    for cat in categories:
        cat_dir = output_dir / cat
        (cat_dir).mkdir(parents=True, exist_ok=True)
        cat_index_path = cat_dir / "index.md"

        lines_cat: List[str] = [f"# {cat}\n\n"]
        for src in cat_map[cat]:
            if not src["docs"]:
                continue
            builder = TOC_BUILDERS.get(src["type"])
            if not builder:
                continue
            lines_cat.append("```{toctree}\n:maxdepth: 1\n\n")
            lines_cat.extend(
                [ln + "\n" for ln in builder(src["name"], src["dest_dir"], src["docs"])]
            )
            lines_cat.append("\n```\n\n")

        with cat_index_path.open("w", encoding="utf-8") as f:
            f.writelines(lines_cat)


###############################################################################
# Orchestrator                                                                #
###############################################################################


def merge_docs(manifest_path: str | Path, output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with Path(manifest_path).open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    source_entries: List[Dict] = []

    for src in config.get("sources", []):
        stype = src["type"]
        handler = SOURCE_HANDLERS.get(stype)
        if handler is None:
            print(f"[warn] No handler for source type '{stype}'. Skipping…")
            continue

        category = src.get("category")
        raw_dest = src.get("dest_dir", "").rstrip("/")
        if category:
            full_path = (
                output_dir / category / raw_dest if raw_dest else output_dir / category
            )
        else:
            full_path = output_dir / raw_dest if raw_dest else output_dir

        docs = handler(src, full_path)
        source_entries.append(
            {
                "type": stype,
                "name": src["name"],
                "category": category,
                "dest_dir": raw_dest,
                "docs": docs,
            }
        )

    build_all_indices(output_dir, source_entries)
    _write_reuse(Path("."))


def main() -> None:
    p = argparse.ArgumentParser(
        description="Merge multiple documentation sources into a Sphinx‑ready tree."
    )
    p.add_argument("--manifest", required=True, help="YAML manifest file.")
    p.add_argument(
        "--output", default="docs", help="Destination directory (default: docs/)"
    )
    args = p.parse_args()
    merge_docs(args.manifest, args.output)


if __name__ == "__main__":
    main()
