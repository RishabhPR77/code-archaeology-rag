# retrieval/graph.py
import json
import re
import networkx as nx
from pyvis.network import Network
from collections import defaultdict
from datetime import datetime

class CommitGraph:

    def __init__(self, chunks_path: str = "./data/raw/chunks.json"):
        self.graph = nx.DiGraph()   # directed graph — time flows forward
        self.chunks = self._load_chunks(chunks_path)
        self._build(self.chunks)

    def _load_chunks(self, path: str) -> list[dict]:
        with open(path) as f:
            return json.load(f)

    def _build(self, chunks: list[dict]):
        """
        Build the graph from chunks.
        Nodes = commits
        Edges = two commits touched the same file (connected in time order)
        """
        # Sort chunks by timestamp oldest → newest
        sorted_chunks = sorted(
            chunks,
            key=lambda c: c["metadata"]["timestamp"]
        )

        # Add every commit as a node
        for chunk in sorted_chunks:
            meta = chunk["metadata"]
            self.graph.add_node(
                chunk["id"],
                sha       = meta["sha"],
                author    = meta["author"],
                timestamp = meta["timestamp"],
                files     = meta["files"],
                message   = chunk["text"].split("\n")[0].replace("COMMIT: ", ""),
                has_pr    = meta["has_pr"],
                score     = 0.0
            )

        # Build file → list of commits lookup
        file_to_commits = defaultdict(list)
        for chunk in sorted_chunks:
            files = chunk["metadata"]["files"].split(", ")
            for f in files:
                f = f.strip()
                if f:
                    file_to_commits[f].append(chunk["id"])

        # Add edges between consecutive commits on same file
        for file, commit_ids in file_to_commits.items():
            for i in range(len(commit_ids) - 1):
                src = commit_ids[i]
                tgt = commit_ids[i + 1]
                if self.graph.has_edge(src, tgt):
                    # Edge already exists — add this file to its label
                    self.graph[src][tgt]["files"].append(file)
                    self.graph[src][tgt]["weight"] += 1
                else:
                    self.graph.add_edge(
                        src, tgt,
                        files  = [file],
                        weight = 1
                    )

        print(f"Graph built: {self.graph.number_of_nodes()} nodes, "
              f"{self.graph.number_of_edges()} edges")

    # ------------------------------------------------------------------
    # Query 1: File timeline — how did a file evolve?
    # ------------------------------------------------------------------
    def file_timeline(self, filename: str) -> list[dict]:
        """
        Returns all commits that touched a file, in chronological order.
        """
        results = []
        for chunk in self.chunks:
            if filename.lower() in chunk["metadata"]["files"].lower():
                results.append({
                    "sha":       chunk["metadata"]["sha"],
                    "author":    chunk["metadata"]["author"],
                    "timestamp": chunk["metadata"]["timestamp"],
                    "message":   chunk["text"].split("\n")[0].replace("COMMIT: ", ""),
                    "files":     chunk["metadata"]["files"],
                    "has_pr":    chunk["metadata"]["has_pr"],
                })

        # Sort chronologically
        results.sort(key=lambda x: x["timestamp"])
        return results

    # ------------------------------------------------------------------
    # Query 2: Co-change analysis — which files change together?
    # ------------------------------------------------------------------
    def co_change_analysis(self, top_n: int = 10) -> list[dict]:
        """
        Finds pairs of files that are frequently changed together.
        """
        pair_counts = defaultdict(int)

        for chunk in self.chunks:
            files = [f.strip() for f in chunk["metadata"]["files"].split(", ") if f.strip()]
            # Count every pair of files changed in same commit
            for i in range(len(files)):
                for j in range(i + 1, len(files)):
                    pair = tuple(sorted([files[i], files[j]]))
                    pair_counts[pair] += 1

        sorted_pairs = sorted(
            pair_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]

        return [
            {"files": list(pair), "co_changes": count}
            for pair, count in sorted_pairs
        ]

    # ------------------------------------------------------------------
    # Query 3: Author analysis — what did each author focus on?
    # ------------------------------------------------------------------
    def author_analysis(self) -> list[dict]:
        """
        Shows each author's commit count and which files they touched most.
        """
        author_data = defaultdict(lambda: {"commits": 0, "files": defaultdict(int)})

        for chunk in self.chunks:
            author = chunk["metadata"]["author"]
            author_data[author]["commits"] += 1
            for f in chunk["metadata"]["files"].split(", "):
                f = f.strip()
                if f:
                    author_data[author]["files"][f] += 1

        results = []
        for author, data in author_data.items():
            top_files = sorted(
                data["files"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            results.append({
                "author":    author,
                "commits":   data["commits"],
                "top_files": [{"file": f, "changes": c} for f, c in top_files]
            })

        return sorted(results, key=lambda x: x["commits"], reverse=True)

    # ------------------------------------------------------------------
    # Query 4: Hottest files — most frequently changed
    # ------------------------------------------------------------------
    def hottest_files(self, top_n: int = 10) -> list[dict]:
        file_counts = defaultdict(int)

        for chunk in self.chunks:
            for f in chunk["metadata"]["files"].split(", "):
                f = f.strip()
                if f:
                    file_counts[f] += 1

        return [
            {"file": f, "change_count": c}
            for f, c in sorted(file_counts.items(),
                               key=lambda x: x[1], reverse=True)[:top_n]
        ]

    # ------------------------------------------------------------------
    # Visualization — interactive HTML graph
    # ------------------------------------------------------------------
    def visualize(
        self,
        output_path: str = "./data/graph.html",
        filter_file: str = None,
        max_nodes: int = 80
    ):
        """
        Renders the graph as an interactive HTML file.
        filter_file: if given, only show commits touching this file
        max_nodes: cap to avoid browser slowdown
        """
        if filter_file:
            # Only include nodes that touched this file
            relevant_ids = set(
                chunk["id"] for chunk in self.chunks
                if filter_file.lower() in chunk["metadata"]["files"].lower()
            )
            subgraph = self.graph.subgraph(relevant_ids)
        else:
            # Take the most connected nodes
            nodes_by_degree = sorted(
                self.graph.degree(), key=lambda x: x[1], reverse=True
            )[:max_nodes]
            top_node_ids = [n for n, _ in nodes_by_degree]
            subgraph = self.graph.subgraph(top_node_ids)

        # Build pyvis network
        net = Network(
            height="750px",
            width="100%",
            directed=True,
            bgcolor="#1a1a2e",
            font_color="white"
        )
        net.barnes_hut(gravity=-8000, spring_length=200)

        for node_id in subgraph.nodes():
            data = self.graph.nodes[node_id]
            label = f"{data['sha']}\n{data['author'].split()[0]}"
            title = (
                f"SHA: {data['sha']}\n"
                f"Author: {data['author']}\n"
                f"Date: {data['timestamp'][:10]}\n"
                f"Files: {data['files'][:100]}\n"
                f"Message: {data['message'][:80]}"
            )
            # Color by author
            color = self._author_color(data["author"])
            net.add_node(
                node_id,
                label=label,
                title=title,
                color=color,
                size=15 + subgraph.degree(node_id) * 2
            )

        for src, tgt, data in subgraph.edges(data=True):
            net.add_edge(
                src, tgt,
                title=f"Shared files: {', '.join(data['files'][:3])}",
                width=min(data["weight"] * 1.5, 6)
            )

        net.save_graph(output_path)
        print(f"Graph saved to {output_path} — open in browser")

    def _author_color(self, author: str) -> str:
        colors = [
            "#7F77DD", "#1D9E75", "#D85A30",
            "#378ADD", "#BA7517", "#D4537E",
            "#639922", "#E24B4A", "#888780"
        ]
        return colors[hash(author) % len(colors)]

    def save_graph_data(self, path: str = "./data/graph.json"):
        data = {
            "nodes": [
                {"id": n, **self.graph.nodes[n]}
                for n in self.graph.nodes()
            ],
            "edges": [
                {"src": u, "tgt": v, **d}
                for u, v, d in self.graph.edges(data=True)
            ]
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Graph data saved to {path}")
        
    # ------------------------------------------------------------------
    # Visualization A — File-centric graph
    # ------------------------------------------------------------------
    def visualize_files(
        self,
        output_path: str = "./data/file_graph.html",
        min_cochange: int = 2
    ):
        pair_counts = defaultdict(int)
        file_change_counts = defaultdict(int)

        for chunk in self.chunks:
            files = [f.strip() for f in chunk["metadata"]["files"].split(", ") if f.strip()]
            for f in files:
                file_change_counts[f] += 1
            for i in range(len(files)):
                for j in range(i + 1, len(files)):
                    pair = tuple(sorted([files[i], files[j]]))
                    pair_counts[pair] += 1

        strong_pairs = {
            pair: count for pair, count in pair_counts.items()
            if count >= min_cochange
        }

        if not strong_pairs:
            print("No co-change pairs found above threshold.")
            return

        files_in_graph = set()
        for f1, f2 in strong_pairs:
            files_in_graph.add(f1)
            files_in_graph.add(f2)

        net = Network(
            height="750px",
            width="100%",
            directed=False,
            bgcolor="#0d0d0f",
            font_color="#e8e6e0"
        )
        net.barnes_hut(gravity=-3000, spring_length=180, spring_strength=0.05)

        def file_color(filename):
            ext = filename.rsplit(".", 1)[-1] if "." in filename else "other"
            color_map = {
                "py":   "#7F77DD",
                "js":   "#BA7517",
                "jsx":  "#D85A30",
                "ts":   "#378ADD",
                "tsx":  "#1D9E75",
                "rst":  "#888780",
                "yaml": "#D4537E",
                "yml":  "#D4537E",
                "toml": "#639922",
                "json": "#E24B4A",
                "md":   "#555",
                "css":  "#4A90D9",
            }
            return color_map.get(ext, "#666")

        max_changes = max(file_change_counts.values()) if file_change_counts else 1
        for filename in files_in_graph:
            count = file_change_counts.get(filename, 1)
            size  = 10 + (count / max_changes) * 30
            label = filename.split("/")[-1]
            title = (
                f"<b>{filename}</b><br>"
                f"Changed {count}x total<br>"
                f"Appears in {sum(1 for p in strong_pairs if filename in p)} co-change pairs"
            )
            net.add_node(
                filename,
                label=label,
                title=title,
                color=file_color(filename),
                size=size,
                font={"size": 11, "color": "#e8e6e0"}
            )

        max_cochange = max(strong_pairs.values()) if strong_pairs else 1
        for (f1, f2), count in strong_pairs.items():
            width = 1 + (count / max_cochange) * 8
            net.add_edge(f1, f2, width=width, title=f"Co-changed {count}x together", color="#333344")

        net.save_graph(output_path)
        print(f"File graph saved to {output_path}")

    # ------------------------------------------------------------------
    # Visualization B — Timeline swimlane graph
    # ------------------------------------------------------------------
    def visualize_timeline(
        self,
        output_path: str = "./data/timeline_graph.html"
    ):
        sorted_chunks = sorted(
            self.chunks,
            key=lambda c: c["metadata"]["timestamp"]
        )

        author_counts = defaultdict(int)
        for chunk in sorted_chunks:
            author_counts[chunk["metadata"]["author"]] += 1
        top_authors = [
            a for a, _ in sorted(
                author_counts.items(), key=lambda x: x[1], reverse=True
            )[:8]
        ]

        author_y = {author: i * 120 for i, author in enumerate(top_authors)}

        if not sorted_chunks:
            return

        t_min = datetime.fromisoformat(sorted_chunks[0]["metadata"]["timestamp"])
        t_max = datetime.fromisoformat(sorted_chunks[-1]["metadata"]["timestamp"])
        t_range = (t_max - t_min).total_seconds() or 1
        canvas_width = 1400

        def commit_type_color(message: str) -> str:
            msg = message.lower()
            if any(w in msg for w in ["fix", "bug", "patch", "hotfix", "error", "issue"]):
                return "#E24B4A"
            elif any(w in msg for w in ["add", "feat", "feature", "new", "implement", "create"]):
                return "#1D9E75"
            elif any(w in msg for w in ["refactor", "clean", "restructure", "reorganize", "move"]):
                return "#7F77DD"
            elif any(w in msg for w in ["chore", "update", "bump", "upgrade", "deps", "dependency", "version", "release", "merge"]):
                return "#888780"
            elif any(w in msg for w in ["doc", "readme", "comment", "docs"]):
                return "#BA7517"
            else:
                return "#378ADD"

        def commit_type_label(message: str) -> str:
            msg = message.lower()
            if any(w in msg for w in ["fix", "bug", "patch", "hotfix", "error", "issue"]):
                return "bug fix"
            elif any(w in msg for w in ["add", "feat", "feature", "new", "implement", "create"]):
                return "feature"
            elif any(w in msg for w in ["refactor", "clean", "restructure", "reorganize", "move"]):
                return "refactor"
            elif any(w in msg for w in ["chore", "update", "bump", "upgrade", "deps", "dependency", "version", "release", "merge"]):
                return "chore"
            elif any(w in msg for w in ["doc", "readme", "comment", "docs"]):
                return "docs"
            else:
                return "other"

        net = Network(
            height="850px",
            width="100%",
            directed=True,
            bgcolor="#0d0d0f",
            font_color="#e8e6e0"
        )
        net.toggle_physics(False)

        added_nodes = set()

        for chunk in sorted_chunks:
            author = chunk["metadata"]["author"]
            if author not in author_y:
                continue

            t = datetime.fromisoformat(chunk["metadata"]["timestamp"])
            x = int(((t - t_min).total_seconds() / t_range) * canvas_width)
            y = author_y[author]

            msg    = chunk["text"].split("\n")[0].replace("COMMIT: ", "")
            color  = commit_type_color(msg)
            c_type = commit_type_label(msg)

            title = (
                f"<b>{chunk['metadata']['sha']}</b><br>"
                f"<b>Author:</b> {author}<br>"
                f"<b>Date:</b> {chunk['metadata']['timestamp'][:10]}<br>"
                f"<b>Type:</b> {c_type}<br>"
                f"<b>Files:</b> {chunk['metadata']['files'][:80]}<br>"
                f"<b>Message:</b> {msg[:100]}"
            )

            net.add_node(
                chunk["id"],
                label=chunk["metadata"]["sha"],
                title=title,
                color=color,
                size=14,
                x=x, y=y,
                font={"size": 9, "color": "#888"}
            )
            added_nodes.add(chunk["id"])

        author_commits = defaultdict(list)
        for chunk in sorted_chunks:
            if chunk["metadata"]["author"] in author_y:
                author_commits[chunk["metadata"]["author"]].append(chunk["id"])

        for author, commit_ids in author_commits.items():
            for i in range(len(commit_ids) - 1):
                src, tgt = commit_ids[i], commit_ids[i + 1]
                if src in added_nodes and tgt in added_nodes:
                    net.add_edge(src, tgt, color="#222233", width=1, arrows="to")

        legend_items = [
            ("bug fix",  "#E24B4A"),
            ("feature",  "#1D9E75"),
            ("refactor", "#7F77DD"),
            ("chore",    "#888780"),
            ("docs",     "#BA7517"),
            ("other",    "#378ADD"),
        ]
        legend_html = "".join([
            f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px;">'
            f'<span style="width:10px;height:10px;border-radius:50%;background:{c};display:inline-block;"></span>'
            f'<span style="font-size:11px;color:#888;">{label}</span></span>'
            for label, c in legend_items
        ])

        lane_html = "".join([
            f'<div style="position:absolute;left:8px;top:{y + 50}px;'
            f'font-family:monospace;font-size:11px;color:#555;">{author.split()[0]}</div>'
            for author, y in author_y.items()
        ])

        net.save_graph(output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            html = f.read()

        injection = f"""
        <div style="position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
                    background:#111115;border:1px solid #1e1e24;border-radius:8px;
                    padding:10px 16px;z-index:999;display:flex;align-items:center;gap:4px;">
            {legend_html}
        </div>
        <div style="position:fixed;left:0;top:0;width:130px;height:100%;
                    background:rgba(13,13,15,0.7);pointer-events:none;z-index:998;">
            {lane_html}
        </div>
        """
        html = html.replace("</body>", injection + "</body>")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"Timeline graph saved to {output_path}")