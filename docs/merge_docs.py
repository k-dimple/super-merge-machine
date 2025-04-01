#!/usr/bin/env python3
"""
Merges multiple documentation sources (GitHub/Discourse) into a Sphinx-ready set of .md/.rst files,
including a root index that groups sources by optional "category" and then by "dest_dir".

Changelog (refactored):
1. Allow single (or multiple) page includes from GitHub by specifying 'pages' with 'doc_file' and optional 'filename'.
2. Permit grouping sources under a named category. Sources sharing a category get a dedicated index.md in a subfolder.
3. If a source has no category, it remains at the top-level index as before (no category grouping).
"""

import os
import shutil
import tempfile
import argparse
import yaml
import requests
from git import Repo


def copy_tree(src, dest):
    """Recursively copy src to dest."""
    if not os.path.exists(dest):
        shutil.copytree(src, dest)
        return
    for root, dirs, files in os.walk(src):
        rel_path = os.path.relpath(root, src)
        dest_path = os.path.join(dest, rel_path)
        os.makedirs(dest_path, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(dest_path, f))


def copy_file(src_file, dst_file):
    """Copy a single file from src_file to dst_file, ensuring directories exist."""
    os.makedirs(os.path.dirname(dst_file), exist_ok=True)
    shutil.copy2(src_file, dst_file)


def build_github_toc(name, dest_dir, doc_files):
    """
    If multiple doc files, list them (e.g. "someDir/doc.md").
    If only 1 doc, label it as "SourceName <someDir/doc.md>".
    """
    lines = []
    if len(doc_files) > 1:
        for doc_file in doc_files:
            if dest_dir:
                lines.append(f"{dest_dir}/{doc_file}")
            else:
                lines.append(f"{doc_file}")
    else:
        for doc_file in doc_files:
            if dest_dir:
                lines.append(f"{name} <{dest_dir}/{doc_file}>")
            else:
                lines.append(f"{name} <{doc_file}>")
    return lines


def build_discourse_toc(name, dest_dir, doc_files):
    """
    For Discourse, typically there's 1 doc (an index or a single .md),
    so we always label with SourceName.
    """
    lines = []
    for doc_file in doc_files:
        if dest_dir:
            lines.append(f"{name} <{dest_dir}/{doc_file}>")
        else:
            lines.append(f"{name} <{doc_file}>")
    return lines


TOC_BUILDERS = {
    "github": build_github_toc,
    "discourse": build_discourse_toc,
}


def clone_repo_shallow(repo_url, branch, clone_to):
    """Shallow clone of a Git repo into 'clone_to' directory."""
    print(f"Cloning {repo_url} @ {branch} -> {clone_to} (shallow)…")
    Repo.clone_from(
        repo_url,
        to_path=clone_to,
        branch=branch,
        multi_options=["--depth=1"],
    )


def fetch_discourse_topic(base_url, topic_id, title):
    """
    Fetch raw Markdown from Discourse, removing content after '-------------------------'.
    The final returned text is pre-pended with '# <title>\n\n'.
    """
    url = f"{base_url}/raw/{topic_id}"
    print(f"Fetching Discourse topic {topic_id} from {url}...")
    resp = requests.get(url)
    resp.raise_for_status()

    content = f"# {title}\n\n" + resp.text
    cutoff_index = content.find("-------------------------")
    if cutoff_index != -1:
        content = content[:cutoff_index].rstrip()

    return content


def create_discourse_index(directory, section_name, pages):
    """
    Create an index.md that links to pages in this directory.
    Returns the filename of the created index.md, or None if the directory doesn't exist.
    """
    if not os.path.isdir(directory):
        return None

    lines = []
    lines.append(f"# {section_name}\n\n")
    for page in pages:
        lines.append(f"## {page['title']}\n\n")
        lines.append("```{toctree}\n:maxdepth: 1\n\n")
        base, _ = os.path.splitext(page["filename"])
        lines.append(f"{base}\n")
        lines.append("```\n\n")

    index_path = os.path.join(directory, "index.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return "index.md"


def gather_github_top_level(dest_dir):
    """
    For GitHub docs (the 'full subdir' scenario), if there's a top-level
    index.md or index.rst, return only that. Otherwise return all top-level .md/.rst files.
    """
    if not os.path.isdir(dest_dir):
        return []

    idx_md = os.path.join(dest_dir, "index.md")
    idx_rst = os.path.join(dest_dir, "index.rst")

    if os.path.isfile(idx_md):
        return ["index.md"]
    elif os.path.isfile(idx_rst):
        return ["index.rst"]

    files = []
    for name in os.listdir(dest_dir):
        path = os.path.join(dest_dir, name)
        if os.path.isfile(path) and (name.endswith(".md") or name.endswith(".rst")):
            files.append(name)
    return files


def handle_github_source(src, full_path):
    """
    Clones repo, then either:
      - If 'pages' given, copy only those listed files from repo_subdir.
      - Else copy the entire doc_subdir, returning top-level docs (like index.md).
    """
    repo_url = src["repo_url"]
    branch = src.get("branch", "main")
    doc_subdir = src.get("doc_subdir", "")

    with tempfile.TemporaryDirectory() as tmpdir:
        clone_repo_shallow(repo_url, branch, tmpdir)
        src_subdir = os.path.join(tmpdir, doc_subdir)

        if not os.path.exists(src_subdir):
            print(f"Warning: subdir '{doc_subdir}' not found in {repo_url}.")
            os.makedirs(full_path, exist_ok=True)
            return []

        # If user explicitly listed pages to include
        if "pages" in src:
            os.makedirs(full_path, exist_ok=True)
            doc_files = []
            for page in src["pages"]:
                in_repo = os.path.join(src_subdir, page["doc_file"])
                if not os.path.isfile(in_repo):
                    print(
                        f"Warning: file '{page['doc_file']}' not found in {doc_subdir}. Skipping."
                    )
                    continue
                local_name = page.get("filename") or os.path.basename(page["doc_file"])
                out_file = os.path.join(full_path, local_name)
                copy_file(in_repo, out_file)
                doc_files.append(local_name)

            return doc_files

        # Else copy entire doc_subdir
        copy_tree(src_subdir, full_path)
        return gather_github_top_level(full_path)


def handle_discourse_source(src, full_path):
    """
    Fetch Discourse topics, write them locally, then create a subdir index.
    Returns list containing the index.md (if successful).
    """
    os.makedirs(full_path, exist_ok=True)
    for p in src.get("pages", []):
        md_text = fetch_discourse_topic(src["discourse_url"], p["topic_id"], p["title"])
        fname = p.get("filename", f"{p['topic_id']}.md")
        with open(os.path.join(full_path, fname), "w", encoding="utf-8") as fmd:
            fmd.write(md_text)

    index_file = create_discourse_index(
        directory=full_path, section_name=src["name"], pages=src["pages"]
    )
    return [index_file] if index_file else []


SOURCE_HANDLERS = {
    "github": handle_github_source,
    "discourse": handle_discourse_source,
}


def merge_docs(manifest_path, output_dir):
    """
    Merges documentation from multiple sources into 'output_dir'.
    Each source is placed at output_dir/(category/)?(dest_dir)?,
    and we build the top-level index + category sub-indexes accordingly.
    """
    os.makedirs(output_dir, exist_ok=True)
    with open(manifest_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    source_entries = []

    for src in config.get("sources", []):
        stype = src["type"]
        sname = src["name"]
        category = src.get("category")  # optional
        raw_dest = src.get("dest_dir", "").rstrip("/")

        # Physical directory = output_dir / category? / dest_dir?
        if category:
            full_path = (
                os.path.join(output_dir, category, raw_dest)
                if raw_dest
                else os.path.join(output_dir, category)
            )
        else:
            full_path = os.path.join(output_dir, raw_dest) if raw_dest else output_dir

        os.makedirs(full_path, exist_ok=True)

        handler = SOURCE_HANDLERS.get(stype)
        if handler is None:
            print(f"Warning: No handler found for source type '{stype}'. Skipping...")
            continue

        doc_files = handler(src, full_path)

        source_entries.append(
            {
                "type": stype,
                "name": sname,
                "category": category,
                "dest_dir": raw_dest,  # keep the user-specified path
                "docs": doc_files,
            }
        )

    build_all_indices(output_dir, source_entries)


def build_all_indices(output_dir, source_entries):
    """
    Builds:
    1) A root index named "index.md" with heading "Related Technologies".
    2) Category subfolders each get an index referencing their sources.
    3) Sources with no category appear directly at root-level (as before).
    """

    # Group sources by category (None => no category)
    from collections import defaultdict

    cat_map = defaultdict(list)
    for e in source_entries:
        cat_map[e.get("category")].append(e)

    # Start root index
    root_index = os.path.join(output_dir, "index.md")
    lines = ["# Related Technologies\n\n"]

    # Collect categories (non-None) and sort them for consistent ordering
    categories = sorted([c for c in cat_map.keys() if c is not None])

    if categories:
        lines.append("```{toctree}\n:maxdepth: 1\n\n")
        for cat in categories:
            # We'll store the category index at output_dir/<cat>/index.md
            # So from the root's perspective, it’s "<cat>/index"
            lines.append(f"{cat}/index")
        lines.append("\n```\n\n")

    no_category_sources = cat_map.get(None, [])
    for src in no_category_sources:
        stype = src["type"]
        name = src["name"]
        doc_files = src["docs"]
        raw_dest = src["dest_dir"]

        # If no docs, skip
        if not doc_files:
            continue

        builder = TOC_BUILDERS.get(stype)
        if not builder:
            continue

        lines.append("```{toctree}\n:maxdepth: 1\n\n")

        toc_lines = map(lambda x: x + "\n", builder(name, raw_dest, doc_files))
        lines.extend(toc_lines)
        lines.append("\n```\n\n")

    with open(root_index, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Build an index per category
    for cat in categories:
        cat_dir = os.path.join(output_dir, cat)
        os.makedirs(cat_dir, exist_ok=True)
        cat_index_path = os.path.join(cat_dir, "index.md")

        lines_cat = [f"# {cat}\n\n"]
        for src in cat_map[cat]:
            stype = src["type"]
            name = src["name"]
            doc_files = src["docs"]
            raw_dest = src["dest_dir"]  # subfolder under this category

            if not doc_files:
                continue
            builder = TOC_BUILDERS.get(stype)
            if not builder:
                continue

            lines_cat.append("```{toctree}\n:maxdepth: 1\n\n")

            # If user had "raw_dest", the actual doc paths are category/dest_dir/filename
            # But from this category’s perspective, we only need "dest_dir/filename".
            # If raw_dest is empty, docs are at cat_dir/<filename>.
            # So the toctree reference is simply something like "subDir/doc.md" or "doc.md".
            toc_lines = map(lambda x: x + "\n", builder(name, raw_dest, doc_files))
            lines_cat.extend(toc_lines)
            lines_cat.append("\n```\n\n")

        with open(cat_index_path, "w", encoding="utf-8") as f:
            f.writelines(lines_cat)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="Path to the YAML manifest.")
    parser.add_argument(
        "--output", default="docs", help="Output directory for merged docs."
    )
    args = parser.parse_args()
    merge_docs(args.manifest, args.output)


if __name__ == "__main__":
    main()
