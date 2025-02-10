#!/usr/bin/env python3
"""
Reads a YAML manifest of doc sources (GitHub/Discourse),
merges them into a Sphinx project, and overwrites the root index.

- GitHub:
  - If there's only 1 doc file, use "SourceName <someDir/doc.md>" label format
  - If multiple doc files, just list them (e.g. "someDir/index.md", no label).
- Discourse:
  - We create an index.md in the subdir; references remain labeled with SourceName.
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
    Always label with SourceName, typically only 1 doc (index.md).
    TODO: reuse Discourse offline helper to preserve entire sections
          https://github.com/s-makin/discourse-offline-helper/
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
    # TODO: handle arbitrary HTML with BeautifulSoup / pandoc
    # TODO: handle Google Docs via the Google API, whatever that may be
}


def build_root_index(output_dir, source_entries):
    """
    Overwrite root `index.md`. For each source, we delegate to the appropriate
    builder function in TOC_BUILDERS to create the lines for the toctree.
    """
    index_md = os.path.join(output_dir, "index.md")
    lines = ["# Merged Documentation\n\n"]

    for entry in source_entries:
        stype = entry["type"]
        name = entry["name"]
        dest_dir = entry["dest_dir"].rstrip("/")
        doc_files = entry["docs"]

        builder = TOC_BUILDERS.get(stype)
        if builder is None:
            print(
                f"Warning: No TOC builder found for source type '{stype}'. Skipping..."
            )
            continue

        lines.append("```{toctree}\n:maxdepth: 1\n\n")

        toc_lines = builder(name, dest_dir, doc_files)
        lines.extend(toc_lines)
        lines.append("\n```\n\n")

    with open(index_md, "w", encoding="utf-8") as f:
        f.writelines(lines)


def clone_and_copy(repo_url, branch, doc_subdir, dest):
    """Clone a Git repo, copy the specified subdir into dest."""
    with tempfile.TemporaryDirectory() as tmp:
        print(f"Cloning {repo_url} @ {branch}...")
        Repo.clone_from(
            repo_url, to_path=tmp, branch=branch, multi_options=["--depth=1"]
        )
        src = os.path.join(tmp, doc_subdir) if doc_subdir else tmp
        if not os.path.exists(src):
            print(f"Warning: subdir '{doc_subdir}' not found in {repo_url}.")
            return
        copy_tree(src, dest)


def gather_github_top_level(dest_dir):
    """
    For GitHub docs, if there's a top-level index.md or index.rst, return only that.
    Otherwise return all top-level .md/.rst files.
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
    Clones the repo and gathers top-level docs. Returns a list of doc files.
    """
    clone_and_copy(
        repo_url=src["repo_url"],
        branch=src.get("branch", "main"),
        doc_subdir=src.get("doc_subdir", ""),
        dest=full_path,
    )
    return gather_github_top_level(full_path)


def fetch_discourse_topic(base_url, topic_id, title):
    """Fetch raw Markdown from Discourse, removing content after '-------------------------'."""
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


def handle_discourse_source(src, full_path):
    """
    Fetches Discourse topics, writes them to local MD files, and
    creates a subdir index.md referencing them. Returns a list of doc files (the index).
    """
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
    Merges documentation from multiple sources into a single directory
    and overwrites the root index.md.
    """
    os.makedirs(output_dir, exist_ok=True)
    with open(manifest_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    source_entries = []

    for src in config.get("sources", []):
        stype = src["type"]
        sname = src["name"]
        raw_dest = src["dest_dir"].rstrip("/")
        full_path = os.path.join(output_dir, raw_dest) if raw_dest else output_dir
        os.makedirs(full_path, exist_ok=True)

        handler = SOURCE_HANDLERS.get(stype)
        if handler is None:
            print(f"Warning: No handler found for source type '{stype}'. Skipping...")
            continue

        doc_files = handler(src, full_path)

        source_entries.append(
            {"type": stype, "name": sname, "dest_dir": raw_dest, "docs": doc_files}
        )

    build_root_index(output_dir, source_entries)


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
