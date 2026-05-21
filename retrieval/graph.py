# retrieval/graph.py
import json
import re
import networkx as nx
from pyvis.network import Network
from collections import defaultdict
from datetime import datetime

class CommitGraph:

    def __init__(self, chunks_path: str = "./data/raw/chunks.json"):
        self.graph = nx.DiGraph()
        self.chunks = self._load_chunks(chunks_path)
        self._build(self.chunks)

    def _load_chunks(self, path: str) -> list[dict]:
        with open(path) as f:
            return json.load(f)

    def _build(self, chunks: list[dict]):
        sorted_chunks = sorted(chunks, key=lambda c: c["metadata"]["timestamp"])

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

        file_to_commits = defaultdict(list)
        for chunk in sorted_chunks:
            files = chunk["metadata"]["files"].split(", ")
            for f in files:
                f = f.strip()
                if f:
                    file_to_commits[f].append(chunk["id"])

        for file, commit_ids in file_to_commits.items():
            for i in range(len(commit_ids) - 1):
                src = commit_ids[i]
                tgt = commit_ids[i + 1]
                if self.graph.has_edge(src, tgt):
                    self.graph[src][tgt]["files"].append(file)
                    self.graph[src][tgt]["weight"] += 1
                else:
                    self.graph.add_edge(src, tgt, files=[file], weight=1)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def file_timeline(self, filename: str) -> list[dict]:
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
        results.sort(key=lambda x: x["timestamp"])
        return results

    def co_change_analysis(self, top_n: int = 10) -> list[dict]:
        pair_counts = defaultdict(int)
        for chunk in self.chunks:
            files = [f.strip() for f in chunk["metadata"]["files"].split(", ") if f.strip()]
            for i in range(len(files)):
                for j in range(i + 1, len(files)):
                    pair = tuple(sorted([files[i], files[j]]))
                    pair_counts[pair] += 1
        sorted_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return [{"files": list(pair), "co_changes": count} for pair, count in sorted_pairs]

    def author_analysis(self) -> list[dict]:
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
            top_files = sorted(data["files"].items(), key=lambda x: x[1], reverse=True)[:5]
            results.append({
                "author":    author,
                "commits":   data["commits"],
                "top_files": [{"file": f, "changes": c} for f, c in top_files]
            })
        return sorted(results, key=lambda x: x["commits"], reverse=True)

    def hottest_files(self, top_n: int = 10) -> list[dict]:
        file_counts = defaultdict(int)
        for chunk in self.chunks:
            for f in chunk["metadata"]["files"].split(", "):
                f = f.strip()
                if f:
                    file_counts[f] += 1
        return [
            {"file": f, "change_count": c}
            for f, c in sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
        ]

    # ------------------------------------------------------------------
    # Visualization A — Commit DAG (past → future, colored by author)
    # ------------------------------------------------------------------
    def visualize(
        self,
        output_path: str = "./data/graph.html",
        filter_file: str = None,
        max_nodes: int = 100
    ):
        """
        Directed commit graph. Each node = one commit.
        Arrow direction = time (older → newer).
        Color = author. Hover for full commit details.
        """
        if filter_file:
            relevant_ids = set(
                chunk["id"] for chunk in self.chunks
                if filter_file.lower() in chunk["metadata"]["files"].lower()
            )
            subgraph = self.graph.subgraph(relevant_ids)
        else:
            nodes_by_degree = sorted(
                self.graph.degree(), key=lambda x: x[1], reverse=True
            )[:max_nodes]
            top_node_ids = [n for n, _ in nodes_by_degree]
            subgraph = self.graph.subgraph(top_node_ids)

        net = Network(
            height="780px",
            width="100%",
            directed=True,
            bgcolor="#0d0d0f",
            font_color="#e8e6e0"
        )
        net.barnes_hut(
            gravity=-6000,
            central_gravity=0.3,
            spring_length=160,
            spring_strength=0.05,
            damping=0.9
        )

        # Build author → color map (stable, sorted by commit count)
        author_commit_count = defaultdict(int)
        for chunk in self.chunks:
            author_commit_count[chunk["metadata"]["author"]] += 1
        sorted_authors = sorted(author_commit_count, key=lambda a: author_commit_count[a], reverse=True)
        palette = [
            "#1D9E75", "#E24B4A", "#7F77DD", "#378ADD",
            "#D85A30", "#BA7517", "#D4537E", "#639922", "#888780"
        ]
        author_color = {a: palette[i % len(palette)] for i, a in enumerate(sorted_authors)}

        for node_id in subgraph.nodes():
            data = self.graph.nodes[node_id]
            sha     = data["sha"]
            author  = data["author"]
            date    = data["timestamp"][:10]
            msg     = data["message"][:60]
            files   = data["files"][:120]
            color   = author_color.get(author, "#888780")

            label = f"{sha}\n{author.split()[0]}\n{date}"
            title = (
                f"<b>{sha}</b><br>"
                f"<b>Author:</b> {author}<br>"
                f"<b>Date:</b> {date}<br>"
                f"<b>Message:</b> {msg}<br>"
                f"<b>Files:</b> {files}"
            )
            net.add_node(
                node_id,
                label=label,
                title=title,
                color=color,
                size=16,
                font={"size": 9, "color": "#aaa", "face": "monospace"},
                borderWidth=0,
                shadow=True
            )

        for src, tgt, edata in subgraph.edges(data=True):
            net.add_edge(
                src, tgt,
                color={"color": "#2a2a3a", "highlight": "#7F77DD"},
                width=min(1 + edata["weight"] * 0.5, 4),
                title=f"Shared: {', '.join(edata['files'][:3])}",
                arrows={"to": {"enabled": True, "scaleFactor": 0.6}}
            )

        # Build legend HTML for authors
        legend_html = "".join([
            f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:12px;">'
            f'<span style="width:10px;height:10px;border-radius:50%;background:{author_color[a]};display:inline-block;"></span>'
            f'<span style="font-size:11px;color:#888;">{a.split()[0]} ({author_commit_count[a]})</span></span>'
            for a in sorted_authors[:8]
        ])

        net.save_graph(output_path)
        with open(output_path, "r", encoding="utf-8") as f:
            html = f.read()

        injection = f"""
        <div style="position:fixed;top:12px;left:50%;transform:translateX(-50%);
                    background:#111115;border:1px solid #1e1e24;border-radius:8px;
                    padding:8px 16px;z-index:999;display:flex;align-items:center;
                    gap:4px;flex-wrap:wrap;max-width:90vw;">
            <span style="font-size:11px;color:#444;margin-right:8px;">Authors:</span>
            {legend_html}
        </div>
        <div style="position:fixed;bottom:12px;left:50%;transform:translateX(-50%);
                    background:#111115;border:1px solid #1e1e24;border-radius:6px;
                    padding:6px 14px;z-index:999;">
            <span style="font-size:11px;color:#444;">
                Arrow direction = time &nbsp;·&nbsp; 
                Node size = connectivity &nbsp;·&nbsp; 
                Hover node for commit details
            </span>
        </div>
        """
        html = html.replace("</body>", injection + "</body>")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    # ------------------------------------------------------------------
    # Visualization B — Timeline swimlane (one row per author)
    # ------------------------------------------------------------------
    def visualize_timeline(
        self,
        output_path: str = "./data/timeline_graph.html"
    ):
        """
        Swimlane graph. Each author gets a horizontal lane.
        Commits flow left (oldest) → right (newest).
        Color = commit type. Hover for full details.
        """
        sorted_chunks = sorted(self.chunks, key=lambda c: c["metadata"]["timestamp"])
        if not sorted_chunks:
            return

        # Pick top 8 authors by commit count
        author_counts = defaultdict(int)
        for chunk in sorted_chunks:
            author_counts[chunk["metadata"]["author"]] += 1
        top_authors = [a for a, _ in sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:8]]

        LANE_HEIGHT  = 160   # px between lanes
        NODE_RADIUS  = 18    # px
        CANVAS_W     = 3000  # total width — wide so commits don't crowd
        LEFT_MARGIN  = 160   # space for author labels

        author_y = {author: 80 + i * LANE_HEIGHT for i, author in enumerate(top_authors)}

        t_min = datetime.fromisoformat(sorted_chunks[0]["metadata"]["timestamp"])
        t_max = datetime.fromisoformat(sorted_chunks[-1]["metadata"]["timestamp"])
        t_range = max((t_max - t_min).total_seconds(), 1)

        def commit_color(message: str) -> str:
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

        def commit_type(message: str) -> str:
            msg = message.lower()
            if any(w in msg for w in ["fix", "bug", "patch", "hotfix", "error", "issue"]):   return "bug fix"
            elif any(w in msg for w in ["add", "feat", "feature", "new", "implement", "create"]): return "feature"
            elif any(w in msg for w in ["refactor", "clean", "restructure", "reorganize", "move"]): return "refactor"
            elif any(w in msg for w in ["chore", "update", "bump", "upgrade", "deps", "dependency", "version", "release", "merge"]): return "chore"
            elif any(w in msg for w in ["doc", "readme", "comment", "docs"]): return "docs"
            else: return "other"

        net = Network(
            height="850px",
            width="100%",
            directed=True,
            bgcolor="#0d0d0f",
            font_color="#e8e6e0"
        )
        net.toggle_physics(False)

        # Track x positions per author to avoid exact overlap
        author_last_x = defaultdict(lambda: LEFT_MARGIN - 80)
        MIN_SPACING = 80  # minimum px between two commits in same lane

        added_nodes = set()
        node_positions = {}

        for chunk in sorted_chunks:
            author = chunk["metadata"]["author"]
            if author not in author_y:
                continue

            t = datetime.fromisoformat(chunk["metadata"]["timestamp"])
            raw_x = LEFT_MARGIN + int(((t - t_min).total_seconds() / t_range) * (CANVAS_W - LEFT_MARGIN - 100))

            # Push forward if too close to last commit in this lane
            x = max(raw_x, author_last_x[author] + MIN_SPACING)
            author_last_x[author] = x
            y = author_y[author]
            node_positions[chunk["id"]] = (x, y)

            msg    = chunk["text"].split("\n")[0].replace("COMMIT: ", "")
            color  = commit_color(msg)
            ctype  = commit_type(msg)
            date   = chunk["metadata"]["timestamp"][:10]
            sha    = chunk["metadata"]["sha"]

            title = (
                f"<b>{sha}</b><br>"
                f"<b>Author:</b> {author}<br>"
                f"<b>Date:</b> {date}<br>"
                f"<b>Type:</b> {ctype}<br>"
                f"<b>Files:</b> {chunk['metadata']['files'][:100]}<br>"
                f"<b>Message:</b> {msg[:120]}"
            )

            net.add_node(
                chunk["id"],
                label=f"{sha[:7]}\n{date}",
                title=title,
                color={"background": color, "border": "#0d0d0f", "highlight": {"background": color, "border": "#fff"}},
                size=NODE_RADIUS,
                x=x, y=y,
                font={"size": 8, "color": "#777", "face": "monospace"},
                borderWidth=1,
                shadow={"enabled": True, "color": color + "44", "size": 8}
            )
            added_nodes.add(chunk["id"])

        # Connect consecutive commits per author with a line
        author_commits = defaultdict(list)
        for chunk in sorted_chunks:
            if chunk["metadata"]["author"] in author_y:
                author_commits[chunk["metadata"]["author"]].append(chunk["id"])

        for author, commit_ids in author_commits.items():
            color = "#1e1e2e"
            for i in range(len(commit_ids) - 1):
                src, tgt = commit_ids[i], commit_ids[i + 1]
                if src in added_nodes and tgt in added_nodes:
                    net.add_edge(
                        src, tgt,
                        color={"color": color, "highlight": "#444466"},
                        width=1.5,
                        arrows={"to": {"enabled": True, "scaleFactor": 0.5}}
                    )

        net.save_graph(output_path)
        with open(output_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Build legend
        legend_items = [
            ("feature",  "#1D9E75"),
            ("bug fix",  "#E24B4A"),
            ("refactor", "#7F77DD"),
            ("chore",    "#888780"),
            ("docs",     "#BA7517"),
            ("other",    "#378ADD"),
        ]
        legend_html = "".join([
            f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px;">'
            f'<span style="width:10px;height:10px;border-radius:50%;background:{c};display:inline-block;"></span>'
            f'<span style="font-size:11px;color:#888;">{lbl}</span></span>'
            for lbl, c in legend_items
        ])

        # Build author lane labels + dividers
        total_height = len(top_authors) * LANE_HEIGHT + 80
        lane_html = ""
        for author, y in author_y.items():
            count = author_counts[author]
            lane_html += (
                f'<div style="position:absolute;left:0;top:{y + 34}px;width:{LEFT_MARGIN - 10}px;'
                f'text-align:right;padding-right:12px;">'
                f'<div style="font-family:monospace;font-size:12px;color:#ccc;font-weight:500;">{author.split()[0]}</div>'
                f'<div style="font-size:10px;color:#444;">{count} commits</div>'
                f'</div>'
                f'<div style="position:absolute;left:{LEFT_MARGIN}px;top:{y + 36 + NODE_RADIUS + 4}px;'
                f'width:{CANVAS_W}px;height:1px;background:rgba(255,255,255,0.04);"></div>'
            )

        injection = f"""
        <div id="lane-overlay" style="position:absolute;left:0;top:0;width:100%;height:{total_height}px;
                    pointer-events:none;z-index:5;">
            {lane_html}
        </div>
        <div style="position:fixed;bottom:14px;left:50%;transform:translateX(-50%);
                    background:#111115;border:1px solid #1e1e24;border-radius:8px;
                    padding:8px 16px;z-index:999;display:flex;align-items:center;gap:4px;flex-wrap:wrap;">
            <span style="font-size:11px;color:#444;margin-right:6px;">Commit type:</span>
            {legend_html}
        </div>
        <div style="position:fixed;top:12px;right:16px;
                    background:#111115;border:1px solid #1e1e24;border-radius:6px;
                    padding:6px 12px;z-index:999;">
            <span style="font-size:11px;color:#444;">← older &nbsp;&nbsp; newer →</span>
        </div>
        """

        html = html.replace("</body>", injection + "</body>")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _author_color(self, author: str) -> str:
        colors = ["#1D9E75", "#E24B4A", "#7F77DD", "#378ADD", "#D85A30", "#BA7517", "#D4537E"]
        return colors[hash(author) % len(colors)]