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