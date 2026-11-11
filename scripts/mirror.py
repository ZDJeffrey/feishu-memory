#!/usr/bin/env python3
"""Keep a read-only local Markdown mirror of the memory Wiki."""

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

CONFIG = Path(os.environ.get("FEISHU_MEMORY_CONFIG", Path.home() / ".config/feishu-memory/config.json"))
HEADING = re.compile(r"h([1-9])$")
WHITEBOARD = re.compile(r'^\s*<whiteboard\s+token="([A-Za-z0-9_-]+)"\s*>\s*</whiteboard>\s*$')
RESOURCE = re.compile(r"\[飞书画板 ([^\]]+)\]\(assets/([^/\)]+)/description\.md\)")


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

    def children(parent):
        token = None
        while True:
            args = ["wiki", "+node-list", "--space-id", space, "--page-size", "50"]
            if parent:
                args += ["--parent-node-token", parent]
            if token:
                args += ["--page-token", token]
            data = cli(*args)
            for node in data["nodes"]:
                nodes.append(node)
                if node["has_child"]:
                    children(node["node_token"])
            if not data.get("has_more"):
                return
            token = data["page_token"]

    children(None)
    return nodes


def layout(nodes):
    """Map node tokens to mirror paths that follow the Wiki tree: a page is
    `<title>.md` and its children live in the sibling directory `<title>/`."""
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
    """Compare the remote tree with the manifest; return the new entries,
    `(kind, node)` changes with kind in new/changed/moved, and removed nodes."""
    entries = {}
    for node in nodes:
        entries[node["node_token"]] = {
            "title": node["title"],
            "path": paths[node["node_token"]],
            "obj": node["obj_token"],
            "type": node["obj_type"],
            "modified": times.get(node["obj_token"], ""),
        }
    changes = []
    for token, entry in entries.items():
        before = old.get(token)
        if before is None:
            changes.append(("new", token))
        elif before["modified"] != entry["modified"]:
            changes.append(("changed", token))
        elif before["path"] != entry["path"]:
            changes.append(("moved", token))
    removed = [token for token in old if token not in entries]
    return entries, changes, removed


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
            print(f"未建立副本，运行 pull：{self.root}")
            return
        entries, changes, removed = self.scan()
        for kind, token in changes:
            print(f"{kind}\t{entries[token]['path']}")
        for token in removed:
            print(f"removed\t{self.manifest['nodes'][token]['path']}")
        if not changes and not removed:
            print(f"up to date ({len(entries)} pages)")

    def pull(self, only=(), diff_lines=40, summary=False):
        entries, changes, removed = self.scan()
        if only:
            wanted = {t for s in only for t, _ in find(entries, s)}
            if not wanted:
                sys.exit(f"未找到页面：{', '.join(only)}")
            changes = [(k, t) for k, t in changes if t in wanted]
            changes += [("changed", t) for t in wanted if t not in {c[1] for c in changes}]
            removed = []
        fetch = [t for k, t in changes if k != "moved" and entries[t]["type"] == "docx"]
        with ThreadPoolExecutor(2) as pool:
            bodies = dict(zip(fetch, pool.map(self.fetch, (entries[t]["obj"] for t in fetch))))
        nodes = self.manifest["nodes"]
        removed = [nodes.pop(token)["path"] for token in removed]
        for path in removed:
            self.remove(path)
        report = []
        for kind, token in changes:
            entry = entries[token]
            before = nodes.get(token)
            old_text = ""
            if before:
                old_file = self.root / "docs" / before["path"]
                old_text = old_file.read_text(encoding="utf-8") if old_file.exists() else ""
                if before["path"] != entry["path"]:
                    self.remove(before["path"])
            if token in bodies:
                entry["revision"], body = bodies[token]
            elif entry["type"] != "docx":
                body = f"{entry['type']} 节点，正文不镜像，按对应官方技能读取。\n"
            else:
                entry["revision"] = before.get("revision") if before else None
                body = strip_header(old_text)
            target = self.root / "docs" / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(header(entry, token, self.base) + body, encoding="utf-8")
            nodes[token] = entry
            report.append((kind, entry["path"], strip_header(old_text), body))
        self.manifest["synced_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.manifest_path)
        if summary:
            print(f"更新 {len(report)} 页，移除 {len(removed)} 页；副本：{self.root / 'docs'}")
        else:
            print_report(report, removed, len(nodes), self.root / "docs", diff_lines)

    def checkout(self, page):
        matches = find(self.manifest["nodes"], page)
        if len(matches) != 1:
            sys.exit(f"页面匹配 {len(matches)} 个：{page}")
        token, entry = matches[0]
        if entry["type"] != "docx":
            sys.exit(f"页面类型不是 docx：{entry['type']}")
        source = self.root / "docs" / entry["path"]
        text = source.read_text(encoding="utf-8")
        body, resources = work_view(strip_header(text))
        directory = Path(tempfile.mkdtemp(prefix="feishu-memory-work-"))
        (directory / "baseline.md").write_text(body, encoding="utf-8")
        (directory / "working.md").write_text(body, encoding="utf-8")
        for resource in resources:
            asset = directory / "assets" / resource["token"]
            asset.mkdir(parents=True, exist_ok=True)
            (asset / "description.md").write_text(
                f"# 飞书画板 {resource['token']}\n\n尚未导出或读取画板内容。\n", encoding="utf-8"
            )
        task = {
            "node_token": token,
            "obj_token": entry["obj"],
            "url": f"{self.base}/wiki/{token}",
            "revision": entry.get("revision"),
            "mirror_root": str(self.root.resolve()),
            "mirror_path": entry["path"],
            "mirror_sha256": digest(text),
            "baseline_sha256": digest(body),
            "resources": resources,
        }
        (directory / "task.json").write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(directory)

    def work_status(self, directory):
        directory = Path(directory)
        task = json.loads((directory / "task.json").read_text(encoding="utf-8"))
        baseline = (directory / "baseline.md").read_text(encoding="utf-8")
        working = (directory / "working.md").read_text(encoding="utf-8")
        valid = digest(baseline) == task["baseline_sha256"]
        print(f"baseline: {'ok' if valid else 'modified'}")
        entry = (
            self.manifest["nodes"].get(task["node_token"]) if str(self.root.resolve()) == task["mirror_root"] else None
        )
        if entry is None:
            print("mirror: page missing")
        else:
            source = self.root / "docs" / entry["path"]
            same = (
                entry.get("revision") == task["revision"]
                and digest(source.read_text(encoding="utf-8")) == task["mirror_sha256"]
            )
            print(f"mirror: {'unchanged' if same else 'changed'}")
        expected = [(r["token"], r["token"]) for r in task["resources"]]
        actual = RESOURCE.findall(working)
        if expected != actual:
            added = list((Counter(actual) - Counter(expected)).elements())
            removed = list((Counter(expected) - Counter(actual)).elements())
            print(
                f"whiteboard references changed: added={added}, removed={removed}, "
                f"reordered={not added and not removed}"
            )
        else:
            print(f"whiteboard references: unchanged ({len(expected)})")
        for resource in task["resources"]:
            if not (directory / "assets" / resource["token"] / "description.md").exists():
                print(f"whiteboard description missing: {resource['token']}")
        diff = difflib.unified_diff(
            baseline.splitlines(), working.splitlines(), fromfile="baseline.md", tofile="working.md", lineterm=""
        )
        print("\n".join(diff))
        if not valid:
            sys.exit(1)

    def fetch(self, obj):
        doc = self.cli("docs", "+fetch", "--doc", obj, "--doc-format", "markdown")["document"]
        return doc["revision_id"], doc["content"].rstrip() + "\n"

    def remove(self, path):
        target = self.root / "docs" / path
        target.unlink(missing_ok=True)
        for parent in target.parents:
            if parent == self.root / "docs" or any(parent.iterdir()):
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
            print(
                f"注意：远端 revision {doc['revision_id']} 与副本 {entry.get('revision')} 不同，"
                f"先运行 pull --doc {token}"
            )
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
    """Match a page by token, URL tail, mirror path or title; fall back to a substring."""
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


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def work_view(text):
    resources = []
    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = re.match(r"^(`{3,}|~{3,})", stripped)
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
        match = WHITEBOARD.fullmatch(line.rstrip("\r\n")) if fence is None else None
        if match:
            token = match[1]
            resources.append({"token": token, "original": line.rstrip("\r\n")})
            newline = "\n" if line.endswith("\n") else ""
            line = f"[飞书画板 {token}](assets/{token}/description.md){newline}"
        lines.append(line)
    return "".join(lines), resources


def print_segments(blocks, to_end):
    """Group blocks into ranges usable by block_replace; lists have no block ID."""
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
        if kind == "moved" or old == new:
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
    parser.add_argument("--mirror", type=Path, help="Mirror directory (default ~/.cache/feishu-memory/<space>).")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="List pages changed on the remote since the last pull.")
    pull = sub.add_parser("pull", help="Fetch changed pages and print their diffs.")
    pull.add_argument(
        "--doc",
        action="append",
        default=[],
        help="Only these pages (node/obj token, URL, path or title); always refetched.",
    )
    pull.add_argument("--diff-lines", type=int, default=40)
    pull.add_argument("--summary", action="store_true", help="Print change counts without page diffs.")
    checkout = sub.add_parser("checkout", help="Create an independent local Markdown working copy.")
    checkout.add_argument("page", help="Node/obj token, URL, mirror path or title.")
    work_status = sub.add_parser("work-status", help="Compare a working copy to its baseline.")
    work_status.add_argument("directory", type=Path)
    locate = sub.add_parser("locate", help="Print block IDs for a heading or text in a page.")
    locate.add_argument("page", help="Node/obj token, mirror path or title.")
    locate.add_argument("text")
    args = parser.parse_args()
    mirror = Mirror(json.loads(CONFIG.read_text(encoding="utf-8")), args.mirror)
    if args.command == "status":
        mirror.status()
    elif args.command == "pull":
        docs = [urlparse(d).path.rstrip("/").split("/")[-1] if "://" in d else d for d in args.doc]
        mirror.pull(docs, args.diff_lines, args.summary)
    elif args.command == "locate":
        mirror.locate(args.page, args.text)
    elif args.command == "checkout":
        page = urlparse(args.page).path.rstrip("/").split("/")[-1] if "://" in args.page else args.page
        mirror.checkout(page)
    else:
        mirror.work_status(args.directory)


if __name__ == "__main__":
    main()
