#!/usr/bin/env python3
"""Maintain a lightweight lazy-loaded Markdown cache of the memory Wiki."""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

CONFIG = Path(os.environ.get("FEISHU_MEMORY_CONFIG", Path.home() / ".config/feishu-memory/config.json"))
HEADING = re.compile(r"h([1-9])$")
CORE_PREFIXES = ("知识与协作入口.md", "知识与协作入口/核心协作准则", "知识与协作入口/Agent 记忆/")


class Cli:
    def __init__(self, profile):
        self.profile = profile

    def __call__(self, *args):
        cmd = ["lark-cli", "--profile", self.profile, *args, "--as", "user"]
        for attempt in range(5):
            proc = subprocess.run(cmd, capture_output=True, text=True)
            try:
                data = json.loads(proc.stdout or proc.stderr)
            except json.JSONDecodeError:
                sys.exit(f"lark-cli {' '.join(args[:2])}: {proc.stderr.strip() or proc.stdout.strip()}")
            if data.get("ok"):
                return data["data"]
            message = str(data.get("error", {}).get("message", data))
            if "frequency limit" not in message:
                break
            time.sleep(2**attempt)
        sys.exit(f"lark-cli {' '.join(args[:2])}: {message}")


def walk(cli, space):
    nodes = []

    def fetch_level(parent):
        level = []
        token = None
        while True:
            args = ["wiki", "+node-list", "--space-id", space, "--page-size", "50"]
            if parent:
                args += ["--parent-node-token", parent]
            if token:
                args += ["--page-token", token]
            data = cli(*args)
            level.extend(data["nodes"])
            if not data.get("has_more"):
                return level
            token = data["page_token"]

    frontier = [None]
    with ThreadPoolExecutor(6) as pool:
        while frontier:
            next_frontier = []
            for batch in pool.map(fetch_level, frontier):
                for node in batch:
                    nodes.append(node)
                    if node.get("has_child"):
                        next_frontier.append(node["node_token"])
            frontier = next_frontier
    return nodes


def layout(nodes):
    """Map node tokens to mirror paths that follow the Wiki tree."""
    by_parent = {}
    for node in nodes:
        by_parent.setdefault(node.get("parent_node_token") or "", []).append(node)
    paths = {}

    def place(parent, prefix):
        used = set()
        for node in by_parent.get(parent, []):
            name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", node["title"]).strip(" .") or node["node_token"]
            if name in used:
                name = f"{name} ({node['node_token'][:6]})"
            used.add(name)
            paths[node["node_token"]] = prefix + name + ".md"
            place(node["node_token"], prefix + name + "/")

    place("", "")
    return paths


def modified_times(cli, nodes):
    times = {}
    for i in range(0, len(nodes), 100):
        docs = [{"doc_token": n["obj_token"], "doc_type": n["obj_type"]} for n in nodes[i : i + 100]]
        data = cli("drive", "metas", "batch_query", "--data", json.dumps({"request_docs": docs}))
        for meta in data.get("metas", []):
            times[meta["doc_token"]] = meta["latest_modify_time"]
    return times


def plan(old, nodes, paths, times):
    """Compare the remote tree with the manifest; return new entries, changes, and removed tokens."""
    entries = {}
    for node in nodes:
        token = node["node_token"]
        prev = old.get(token) or {}
        entries[token] = {
            "title": node["title"],
            "path": paths[token],
            "obj": node["obj_token"],
            "type": node["obj_type"],
            "modified": times.get(node["obj_token"], ""),
            "cached_modified": prev.get("cached_modified", ""),
            "revision": prev.get("revision"),
        }
    changes = []
    for token, entry in entries.items():
        before = old.get(token)
        if before is None:
            changes.append(("new", token))
        elif before.get("modified") != entry["modified"]:
            changes.append(("changed", token))
        elif before.get("path") != entry["path"]:
            changes.append(("moved", token))
    removed = [token for token in old if token not in entries]
    return entries, changes, removed


def is_core_path(path):
    return any(path == p or path.startswith(p) for p in CORE_PREFIXES)


def matches_scope(path, scopes):
    for raw in scopes:
        s = raw.strip("/")
        if not s:
            continue
        if path == s or path == f"{s}.md" or path.startswith(f"{s}/") or s in path:
            return True
    return False


def render_tree(entries, docs_dir):
    lines = ["# Wiki 实时目录与缓存状态", "", "状态：`cached` 已是最新缓存，`stale` 远端有更新，`remote` 未下载（按需 `pull --scope` 拉取）。", ""]
    for token, entry in sorted(entries.items(), key=lambda kv: kv[1]["path"]):
        path = entry["path"]
        file_path = docs_dir / path
        if entry["type"] != "docx":
            state = entry["type"]
        elif not file_path.exists():
            state = "remote"
        elif entry.get("cached_modified") == entry.get("modified"):
            state = "cached"
        else:
            state = "stale"
        depth = path.count("/")
        lines.append(f"{'  ' * depth}- `{path}` [{state}]")
    return "\n".join(lines) + "\n"


class Mirror:
    def __init__(self, config, root=None):
        self.space = config["wiki"]["space_id"]
        self.base = "{0.scheme}://{0.netloc}".format(urlparse(config["wiki"]["url"]))
        self.cli = Cli(config["profile"])
        self.root = Path(
            root or os.environ.get("FEISHU_MEMORY_MIRROR") or Path.home() / ".cache/feishu-memory" / self.space
        )
        self.manifest_path = self.root / "manifest.json"
        self.manifest = (
            json.loads(self.manifest_path.read_text(encoding="utf-8")) if self.manifest_path.exists() else {"nodes": {}}
        )

    def scan(self):
        nodes = walk(self.cli, self.space)
        return plan(self.manifest["nodes"], nodes, layout(nodes), modified_times(self.cli, nodes))

    def status(self):
        if not self.manifest_path.exists():
            print(f"未建立缓存，运行 sync：{self.root}")
            return
        entries, changes, removed = self.scan()
        for kind, token in changes:
            print(f"{kind}\t{entries[token]['path']}")
        for token in removed:
            print(f"removed\t{self.manifest['nodes'][token]['path']}")
        if not changes and not removed:
            print(f"up to date ({len(entries)} pages)")

    def _apply_structural(self, entries, removed):
        old_nodes = self.manifest["nodes"]
        docs_dir = self.root / "docs"
        removed_paths = []
        for token in removed:
            path = old_nodes[token]["path"]
            self.remove(path)
            removed_paths.append(path)
        for token, entry in entries.items():
            before = old_nodes.get(token)
            if before and before["path"] != entry["path"]:
                old_file = docs_dir / before["path"]
                if old_file.exists():
                    new_file = docs_dir / entry["path"]
                    new_file.parent.mkdir(parents=True, exist_ok=True)
                    old_file.replace(new_file)
                    self._prune_empty(old_file.parent)
        return removed_paths

    def _save(self, entries):
        self.manifest["nodes"] = entries
        self.manifest["synced_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.manifest_path)
        (self.root / "TREE.md").write_text(render_tree(entries, self.root / "docs"), encoding="utf-8")

    def sync(self):
        entries, changes, removed = self.scan()
        removed_paths = self._apply_structural(entries, removed)
        docs_dir = self.root / "docs"
        to_fetch = [
            t
            for t, e in entries.items()
            if e["type"] == "docx"
            and is_core_path(e["path"])
            and (not (docs_dir / e["path"]).exists() or e.get("cached_modified") != e["modified"])
        ]
        self._fetch_and_write(entries, to_fetch)
        self._save(entries)
        stale = sum(
            1
            for e in entries.values()
            if e["type"] == "docx" and (docs_dir / e["path"]).exists() and e.get("cached_modified") != e["modified"]
        )
        print(
            f"目录已同步（共 {len(entries)} 页，核心更新 {len(to_fetch)} 页，移除 {len(removed_paths)} 页，其余待拉取/过期待刷新 {stale} 页）；"
            f"索引：{self.root / 'TREE.md'}"
        )

    def pull(self, only=(), scopes=(), diff_lines=40, summary=False):
        entries, changes, removed = self.scan()
        removed_paths = self._apply_structural(entries, removed) if not only and not scopes else []
        docs_dir = self.root / "docs"
        if only:
            wanted = {t for s in only for t, _ in find(entries, s)}
            if not wanted:
                sys.exit(f"未找到页面：{', '.join(only)}")
            to_fetch = [t for t in wanted if entries[t]["type"] == "docx"]
        elif scopes:
            wanted = [t for t, e in entries.items() if matches_scope(e["path"], scopes)]
            if not wanted:
                sys.exit(f"未匹配范围：{', '.join(scopes)}")
            to_fetch = [
                t
                for t in wanted
                if entries[t]["type"] == "docx"
                and (not (docs_dir / entries[t]["path"]).exists() or entries[t].get("cached_modified") != entries[t]["modified"])
            ]
        else:
            to_fetch = [
                t
                for t, e in entries.items()
                if e["type"] == "docx"
                and (not (docs_dir / e["path"]).exists() or e.get("cached_modified") != e["modified"])
            ]
        report = self._fetch_and_write(entries, to_fetch)
        self._save(entries)
        if summary:
            print(f"更新 {len(report)} 页，移除 {len(removed_paths)} 页；副本：{docs_dir}")
        else:
            print_report(report, removed_paths, len(entries), docs_dir, diff_lines)

    def _fetch_and_write(self, entries, tokens):
        docs_dir = self.root / "docs"
        if not tokens:
            return []
        with ThreadPoolExecutor(6) as pool:
            bodies = dict(zip(tokens, pool.map(self.fetch, (entries[t]["obj"] for t in tokens))))
        report = []
        for token in tokens:
            entry = entries[token]
            target = docs_dir / entry["path"]
            existed = target.exists()
            old_text = strip_header(target.read_text(encoding="utf-8")) if existed else ""
            entry["revision"], body = bodies[token]
            entry["cached_modified"] = entry["modified"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(header(entry, token, self.base) + body, encoding="utf-8")
            report.append(("changed" if existed else "new", entry["path"], old_text, body))
        return report

    def fetch(self, obj):
        doc = self.cli("docs", "+fetch", "--doc", obj, "--doc-format", "markdown")["document"]
        return doc["revision_id"], doc["content"].rstrip() + "\n"

    def remove(self, path):
        target = self.root / "docs" / path
        target.unlink(missing_ok=True)
        self._prune_empty(target.parent)

    def _prune_empty(self, directory):
        docs_dir = self.root / "docs"
        for parent in (directory, *directory.parents):
            if parent == docs_dir or not parent.exists() or any(parent.iterdir()):
                break
            parent.rmdir()

    def locate(self, page, text):
        """Print block IDs for the section headed by `text`, or for blocks containing it."""
        matches = find(self.manifest["nodes"], page)
        if len(matches) != 1:
            sys.exit(f"页面匹配 {len(matches)} 个：{page}")
        token, entry = matches[0]
        doc = self.cli("docs", "+fetch", "--doc", entry["obj"], "--detail", "with-ids")["document"]
        if doc["revision_id"] != entry.get("revision"):
            print(f"注意：远端 revision {doc['revision_id']} 与缓存 {entry.get('revision')} 不同，建议运行 pull --doc {token}")
        blocks = list(ET.fromstring(f"<root>{doc['content']}</root>"))[1:]
        print(f"revision {doc['revision_id']}")
        for i, block in enumerate(blocks):
            level = HEADING.match(block.tag)
            if level and text in "".join(block.itertext()):
                end = next(
                    (
                        j
                        for j in range(i + 1, len(blocks))
                        if HEADING.match(blocks[j].tag) and int(HEADING.match(blocks[j].tag)[1]) <= int(level[1])
                    ),
                    len(blocks),
                )
                print(f"section {block.tag} {''.join(block.itertext())[:40]}")
                print_segments(blocks[i:end], end == len(blocks))
                return
        hits = [
            e
            for b in blocks
            for e in b.iter()
            if e.get("id")
            and text in "".join(e.itertext())
            and not any(c.get("id") and text in "".join(c.itertext()) for c in e.iter() if c is not e)
        ]
        if not hits:
            sys.exit(f"未找到：{text}")
        for element in hits[:10]:
            print(f"block {element.get('id')} <{element.tag}> {''.join(element.itertext())[:40]}")


def find(entries, query):
    exact = [
        (t, e)
        for t, e in entries.items()
        if query in (t, e["obj"], e["path"], e["title"]) or e["path"].endswith("/" + query)
    ]
    return exact or [(t, e) for t, e in entries.items() if query in e["title"] or query in e["path"]]


def header(entry, token, base):
    return (
        "---\n"
        f"title: {entry['title']}\n"
        f"url: {base}/wiki/{token}\n"
        f"obj: {entry['obj']}\n"
        f"type: {entry['type']}\n"
        f"revision: {entry.get('revision')}\n"
        "---\n\n"
    )


def strip_header(text):
    return text.split("---\n\n", 1)[1] if text.startswith("---\n") and "---\n\n" in text else text


def print_segments(blocks, to_end):
    run = []

    def flush():
        if len(run) == 1:
            print(f"block {run[0].get('id')} <{run[0].tag}>")
        elif run:
            print(f"range {run[0].get('id')} … {run[-1].get('id')} ({len(run)} blocks)")
        run.clear()

    for block in blocks:
        if block.get("id"):
            run.append(block)
            if block.tag == "whiteboard" and block.get("type") != "mermaid":
                flush()
                print(f"native whiteboard {block.get('id')}：留在替换范围之外")
        else:
            flush()
            items = [li.get("id") for li in block if li.get("id")]
            print(f"{block.tag} without id ({len(items)} items): {' '.join(items)}")
    flush()
    if to_end:
        print("section reaches document end: --end-block-id -1 also works")


def print_report(report, removed, total, docs, diff_lines):
    for kind, path, old, new in report:
        if kind == "new":
            print(f"new\t{path} ({len(new)} chars)")
            continue
        if old == new:
            print(f"{kind}\t{path}")
            continue
        lines = [
            line
            for line in difflib.unified_diff(old.splitlines(), new.splitlines(), n=1, lineterm="")
            if not line.startswith(("---", "+++"))
        ]
        print(f"{kind}\t{path}")
        if diff_lines > 0:
            print("\n".join(lines[:diff_lines]))
        if len(lines) > diff_lines:
            print(f"… 还有 {len(lines) - diff_lines} 行改动，见 {docs / path}")
    for path in removed:
        print(f"removed\t{path}")
    if not report and not removed:
        print(f"up to date ({total} pages)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mirror", type=Path, help="Cache directory (default ~/.cache/feishu-memory/<space>).")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="Sync Wiki tree metadata, update core pages, and write TREE.md.")
    sub.add_parser("status", help="List pages changed on the remote since the last sync.")
    pull = sub.add_parser("pull", help="Fetch changed or uncached pages (optionally scoped).")
    pull.add_argument("--scope", action="append", default=[], help="Only fetch pages matching this directory or path prefix.")
    pull.add_argument("--doc", action="append", default=[], help="Force refetch specific pages (token, URL, path or title).")
    pull.add_argument("--diff-lines", type=int, default=40)
    pull.add_argument("--summary", action="store_true", help="Print change counts without page diffs.")
    locate = sub.add_parser("locate", help="Print block IDs for a heading or text in a page.")
    locate.add_argument("page", help="Node/obj token, mirror path or title.")
    locate.add_argument("text")
    args = parser.parse_args()
    mirror = Mirror(json.loads(CONFIG.read_text(encoding="utf-8")), args.mirror)
    if args.command == "sync":
        mirror.sync()
    elif args.command == "status":
        mirror.status()
    elif args.command == "pull":
        docs = [urlparse(d).path.rstrip("/").split("/")[-1] if "://" in d else d for d in args.doc]
        mirror.pull(docs, args.scope, args.diff_lines, args.summary)
    else:
        mirror.locate(args.page, args.text)


if __name__ == "__main__":
    main()
