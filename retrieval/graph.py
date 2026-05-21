# retrieval/graph.py
import json
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
            for f in chunk["metadata"]["files"].split(", "):
                f = f.strip()
                if f:
                    file_to_commits[f].append(chunk["id"])
        for file, commit_ids in file_to_commits.items():
            for i in range(len(commit_ids) - 1):
                src, tgt = commit_ids[i], commit_ids[i + 1]
                if self.graph.has_edge(src, tgt):
                    self.graph[src][tgt]["files"].append(file)
                    self.graph[src][tgt]["weight"] += 1
                else:
                    self.graph.add_edge(src, tgt, files=[file], weight=1)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def file_timeline(self, filename):
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

    def co_change_analysis(self, top_n=10):
        pair_counts = defaultdict(int)
        for chunk in self.chunks:
            files = [f.strip() for f in chunk["metadata"]["files"].split(", ") if f.strip()]
            for i in range(len(files)):
                for j in range(i+1, len(files)):
                    pair_counts[tuple(sorted([files[i], files[j]]))] += 1
        return [{"files": list(p), "co_changes": c}
                for p, c in sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]]

    def author_analysis(self):
        author_data = defaultdict(lambda: {"commits": 0, "files": defaultdict(int)})
        for chunk in self.chunks:
            a = chunk["metadata"]["author"]
            author_data[a]["commits"] += 1
            for f in chunk["metadata"]["files"].split(", "):
                f = f.strip()
                if f:
                    author_data[a]["files"][f] += 1
        results = []
        for author, data in author_data.items():
            top_files = sorted(data["files"].items(), key=lambda x: x[1], reverse=True)[:5]
            results.append({"author": author, "commits": data["commits"],
                            "top_files": [{"file": f, "changes": c} for f, c in top_files]})
        return sorted(results, key=lambda x: x["commits"], reverse=True)

    def hottest_files(self, top_n=10):
        file_counts = defaultdict(int)
        for chunk in self.chunks:
            for f in chunk["metadata"]["files"].split(", "):
                f = f.strip()
                if f:
                    file_counts[f] += 1
        return [{"file": f, "change_count": c}
                for f, c in sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]]

    # ------------------------------------------------------------------
    # Visualization A — Timeline Swimlane (pure custom HTML)
    # ------------------------------------------------------------------
    def visualize_timeline(self, output_path="./data/timeline_graph.html"):
        sorted_chunks = sorted(self.chunks, key=lambda c: c["metadata"]["timestamp"])
        if not sorted_chunks:
            return

        author_counts = defaultdict(int)
        for chunk in sorted_chunks:
            author_counts[chunk["metadata"]["author"]] += 1
        top_authors = [a for a, _ in sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:8]]

        AUTHOR_COLORS = ["#7F77DD", "#1D9E75", "#E24B4A", "#378ADD", "#D85A30", "#BA7517", "#D4537E", "#639922"]
        author_color = {a: AUTHOR_COLORS[i % len(AUTHOR_COLORS)] for i, a in enumerate(top_authors)}

        def commit_type(msg):
            m = msg.lower()
            if any(w in m for w in ["fix","bug","patch","hotfix","error","issue"]): return "fix",   "#E24B4A"
            if any(w in m for w in ["feat","feature","add","new","implement","create"]): return "feat", "#1D9E75"
            if any(w in m for w in ["refactor","clean","restructure","reorganize"]):     return "refactor", "#7F77DD"
            if any(w in m for w in ["doc","readme","comment","docs"]):                    return "docs",  "#BA7517"
            if any(w in m for w in ["chore","update","bump","upgrade","deps","merge","release"]): return "chore","#888780"
            return "other", "#378ADD"

        t_min = datetime.fromisoformat(sorted_chunks[0]["metadata"]["timestamp"])
        t_max = datetime.fromisoformat(sorted_chunks[-1]["metadata"]["timestamp"])
        t_range = max((t_max - t_min).total_seconds(), 1)

        LANE_H    = 110
        PAD_LEFT  = 170
        PAD_RIGHT = 40
        PAD_TOP   = 60
        R         = 12
        SVG_W     = 2400
        SVG_H     = PAD_TOP + len(top_authors) * LANE_H + 60

        def tx(ts):
            t = datetime.fromisoformat(ts)
            frac = (t - t_min).total_seconds() / t_range
            return PAD_LEFT + frac * (SVG_W - PAD_LEFT - PAD_RIGHT)

        # build per-author commit lists with x positions, enforce min spacing
        MIN_GAP = 34
        author_commits = defaultdict(list)
        for chunk in sorted_chunks:
            a = chunk["metadata"]["author"]
            if a in top_authors:
                author_commits[a].append(chunk)

        node_data = {}  # id -> {x, y, color, type, chunk}
        for i, author in enumerate(top_authors):
            y = PAD_TOP + i * LANE_H + LANE_H // 2
            commits = author_commits[author]
            xs = []
            for chunk in commits:
                raw_x = tx(chunk["metadata"]["timestamp"])
                if xs:
                    raw_x = max(raw_x, xs[-1] + MIN_GAP)
                xs.append(raw_x)
            for chunk, x in zip(commits, xs):
                msg = chunk["text"].split("\n")[0].replace("COMMIT: ", "")
                ctype, ccolor = commit_type(msg)
                node_data[chunk["id"]] = {
                    "x": x, "y": y,
                    "color": ccolor,
                    "acolor": author_color[author],
                    "type": ctype,
                    "sha": chunk["metadata"]["sha"],
                    "author": author,
                    "date": chunk["metadata"]["timestamp"][:10],
                    "msg": msg[:100],
                    "files": chunk["metadata"]["files"][:120],
                }

        # SVG elements
        lines_svg = []
        nodes_svg = []
        tooltip_divs = []

        # lane backgrounds + author labels
        for i, author in enumerate(top_authors):
            y_top = PAD_TOP + i * LANE_H
            bg = "#0f0f13" if i % 2 == 0 else "#0d0d0f"
            ac = author_color[author]
            lines_svg.append(
                f'<rect x="0" y="{y_top}" width="{SVG_W}" height="{LANE_H}" fill="{bg}"/>'
            )
            # left accent bar
            lines_svg.append(
                f'<rect x="0" y="{y_top}" width="4" height="{LANE_H}" fill="{ac}"/>'
            )
            cy = y_top + LANE_H // 2
            # author name
            lines_svg.append(
                f'<text x="16" y="{cy - 6}" font-family="monospace" font-size="13" '
                f'font-weight="bold" fill="{ac}">{author.split()[0]}</text>'
            )
            lines_svg.append(
                f'<text x="16" y="{cy + 12}" font-family="monospace" font-size="10" '
                f'fill="#444">{author_counts[author]} commits</text>'
            )
            # horizontal guide line
            lines_svg.append(
                f'<line x1="{PAD_LEFT}" y1="{cy}" x2="{SVG_W}" y2="{cy}" '
                f'stroke="#1a1a22" stroke-width="1"/>'
            )

        # connector lines per author
        for author in top_authors:
            commits = author_commits[author]
            for j in range(len(commits) - 1):
                a_id = commits[j]["id"]
                b_id = commits[j+1]["id"]
                if a_id in node_data and b_id in node_data:
                    x1, y1 = node_data[a_id]["x"], node_data[a_id]["y"]
                    x2, y2 = node_data[b_id]["x"], node_data[b_id]["y"]
                    lines_svg.append(
                        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                        f'stroke="#22222e" stroke-width="1.5" stroke-linecap="round"/>'
                    )
                    # arrowhead
                    mx, my = (x1+x2)/2, (y1+y2)/2
                    lines_svg.append(
                        f'<polygon points="{mx},{my-4} {mx+8},{my} {mx},{my+4}" '
                        f'fill="#333344" opacity="0.7"/>'
                    )

        # nodes
        for nid, nd in node_data.items():
            x, y = nd["x"], nd["y"]
            c = nd["color"]
            safe_id = nid.replace("-","_")
            nodes_svg.append(
                f'<circle id="n_{safe_id}" cx="{x}" cy="{y}" r="{R}" '
                f'fill="{c}" stroke="#0d0d0f" stroke-width="2" '
                f'style="cursor:pointer;filter:drop-shadow(0 0 4px {c}66);" '
                f'onmouseenter="showTip(\'{safe_id}\',evt)" '
                f'onmouseleave="hideTip()" '
                f'onclick="pinTip(\'{safe_id}\')"/>'
            )
            # sha label below node
            nodes_svg.append(
                f'<text x="{x}" y="{y + R + 11}" text-anchor="middle" '
                f'font-family="monospace" font-size="8" fill="#444">{nd["sha"][:7]}</text>'
            )
            # date label above node
            nodes_svg.append(
                f'<text x="{x}" y="{y - R - 4}" text-anchor="middle" '
                f'font-family="monospace" font-size="8" fill="#333">{nd["date"]}</text>'
            )
            # tooltip data div
            tooltip_divs.append(
                f'<div id="tip_{safe_id}" class="tip-data" '
                f'data-sha="{nd["sha"]}" '
                f'data-author="{nd["author"]}" '
                f'data-date="{nd["date"]}" '
                f'data-type="{nd["type"]}" '
                f'data-msg="{nd["msg"].replace("\"", "")}" '
                f'data-files="{nd["files"].replace("\"", "")}" '
                f'data-color="{c}"></div>'
            )

        # date axis at bottom
        axis_y = SVG_H - 20
        lines_svg.append(f'<line x1="{PAD_LEFT}" y1="{axis_y}" x2="{SVG_W - PAD_RIGHT}" y2="{axis_y}" stroke="#222" stroke-width="1"/>')
        num_ticks = 8
        for i in range(num_ticks + 1):
            frac = i / num_ticks
            tick_x = PAD_LEFT + frac * (SVG_W - PAD_LEFT - PAD_RIGHT)
            tick_t = t_min.timestamp() + frac * t_range
            tick_d = datetime.fromtimestamp(tick_t).strftime("%b %d")
            lines_svg.append(f'<line x1="{tick_x}" y1="{axis_y-4}" x2="{tick_x}" y2="{axis_y+4}" stroke="#333" stroke-width="1"/>')
            lines_svg.append(f'<text x="{tick_x}" y="{axis_y + 16}" text-anchor="middle" font-family="monospace" font-size="9" fill="#444">{tick_d}</text>')

        legend_items = [("feature","#1D9E75"),("fix","#E24B4A"),("refactor","#7F77DD"),("docs","#BA7517"),("chore","#888780"),("other","#378ADD")]
        legend_html = "".join([
            f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px;">'
            f'<span style="width:10px;height:10px;border-radius:50%;background:{c};flex-shrink:0;"></span>'
            f'<span style="font-size:11px;color:#888;">{lbl}</span></span>'
            for lbl, c in legend_items
        ])

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d0d0f; font-family: sans-serif; overflow-x: auto; overflow-y: hidden; }}
  #scroll-wrap {{ overflow-x: auto; overflow-y: hidden; width: 100vw; height: 100vh; position: relative; }}
  svg {{ display: block; }}
  #tooltip {{
    display: none;
    position: fixed;
    background: #16161e;
    border: 1px solid #2a2a3a;
    border-radius: 10px;
    padding: 12px 16px;
    min-width: 260px;
    max-width: 340px;
    pointer-events: none;
    z-index: 999;
    box-shadow: 0 8px 32px rgba(0,0,0,0.6);
  }}
  #tooltip.pinned {{ pointer-events: all; cursor: default; }}
  .tt-sha {{ font-family: monospace; font-size: 12px; color: #7F77DD; margin-bottom: 6px; }}
  .tt-row {{ font-size: 12px; color: #888; margin-bottom: 4px; line-height: 1.5; }}
  .tt-row b {{ color: #ccc; }}
  .tt-badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 600;
    margin-left: 6px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .tt-close {{
    position: absolute; top: 8px; right: 10px;
    color: #444; cursor: pointer; font-size: 14px;
  }}
  .tt-close:hover {{ color: #ccc; }}
  #legend {{
    position: fixed; bottom: 14px; left: 50%;
    transform: translateX(-50%);
    background: #111115;
    border: 1px solid #1e1e24;
    border-radius: 8px;
    padding: 8px 16px;
    display: flex; align-items: center; gap: 4px;
    flex-wrap: wrap; z-index: 100;
  }}
  #hint {{
    position: fixed; top: 12px; right: 16px;
    background: #111115; border: 1px solid #1e1e24;
    border-radius: 6px; padding: 6px 12px;
    font-size: 11px; color: #444; z-index: 100;
  }}
  .tip-data {{ display: none; }}
</style>
</head>
<body>
<div id="scroll-wrap">
  <svg width="{SVG_W}" height="{SVG_H}" xmlns="http://www.w3.org/2000/svg">
    {''.join(lines_svg)}
    {''.join(nodes_svg)}
  </svg>
</div>

{''.join(tooltip_divs)}

<div id="tooltip">
  <span class="tt-close" onclick="hideTip()">✕</span>
  <div class="tt-sha" id="tt-sha"></div>
  <div class="tt-row"><b>Author</b><span id="tt-author"></span></div>
  <div class="tt-row"><b>Date &nbsp;</b><span id="tt-date"></span></div>
  <div class="tt-row"><b>Type &nbsp;</b><span id="tt-type"></span></div>
  <div class="tt-row"><b>Message</b><br><span id="tt-msg" style="color:#aaa;font-size:11px;"></span></div>
  <div class="tt-row" style="margin-top:6px;"><b>Files</b><br><span id="tt-files" style="color:#666;font-size:10px;font-family:monospace;"></span></div>
</div>

<div id="legend">
  <span style="font-size:11px;color:#444;margin-right:6px;">Commit type:</span>
  {legend_html}
</div>
<div id="hint">Scroll to explore &nbsp;·&nbsp; Click node to pin tooltip</div>

<script>
var pinned = false;
var currentTip = null;

function getData(safe_id) {{
  var el = document.getElementById('tip_' + safe_id);
  if (!el) return null;
  return {{
    sha:    el.dataset.sha,
    author: el.dataset.author,
    date:   el.dataset.date,
    type:   el.dataset.type,
    msg:    el.dataset.msg,
    files:  el.dataset.files,
    color:  el.dataset.color
  }};
}}

function renderTip(safe_id, x, y) {{
  var d = getData(safe_id);
  if (!d) return;
  document.getElementById('tt-sha').textContent   = d.sha;
  document.getElementById('tt-author').textContent = ' ' + d.author;
  document.getElementById('tt-date').textContent   = ' ' + d.date;
  document.getElementById('tt-msg').textContent    = d.msg;
  document.getElementById('tt-files').textContent  = d.files;

  var badge = document.getElementById('tt-type');
  badge.innerHTML = '<span class="tt-badge" style="background:' + d.color + '33;color:' + d.color + '">' + d.type + '</span>';

  var tip = document.getElementById('tooltip');
  tip.style.display = 'block';
  var tx = Math.min(x + 16, window.innerWidth - 360);
  var ty = Math.max(y - 20, 10);
  tip.style.left = tx + 'px';
  tip.style.top  = ty + 'px';
}}

function showTip(safe_id, evt) {{
  if (pinned) return;
  currentTip = safe_id;
  renderTip(safe_id, evt.clientX, evt.clientY);
}}

function hideTip() {{
  if (pinned) return;
  document.getElementById('tooltip').style.display = 'none';
  currentTip = null;
}}

function pinTip(safe_id) {{
  if (pinned && currentTip === safe_id) {{
    pinned = false;
    document.getElementById('tooltip').classList.remove('pinned');
    hideTip();
    return;
  }}
  pinned = true;
  currentTip = safe_id;
  var el = document.getElementById('n_' + safe_id);
  var rect = el.getBoundingClientRect();
  renderTip(safe_id, rect.x + 20, rect.y);
  document.getElementById('tooltip').classList.add('pinned');
}}
</script>
</body>
</html>"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    # ------------------------------------------------------------------
    # Visualization B — Commit DAG (pyvis, directed, colored by author)
    # ------------------------------------------------------------------
    def visualize(self, output_path="./data/graph.html", filter_file=None, max_nodes=80):
        if filter_file:
            relevant_ids = set(
                chunk["id"] for chunk in self.chunks
                if filter_file.lower() in chunk["metadata"]["files"].lower()
            )
            subgraph = self.graph.subgraph(relevant_ids)
        else:
            nodes_by_degree = sorted(self.graph.degree(), key=lambda x: x[1], reverse=True)[:max_nodes]
            subgraph = self.graph.subgraph([n for n, _ in nodes_by_degree])

        author_counts = defaultdict(int)
        for chunk in self.chunks:
            author_counts[chunk["metadata"]["author"]] += 1
        sorted_authors = sorted(author_counts, key=lambda a: author_counts[a], reverse=True)
        palette = ["#1D9E75","#E24B4A","#7F77DD","#378ADD","#D85A30","#BA7517","#D4537E","#639922","#888780"]
        author_color = {a: palette[i % len(palette)] for i, a in enumerate(sorted_authors)}

        net = Network(height="780px", width="100%", directed=True, bgcolor="#0d0d0f", font_color="#e8e6e0")
        net.barnes_hut(gravity=-5000, central_gravity=0.2, spring_length=180, spring_strength=0.04, damping=0.95)

        for node_id in subgraph.nodes():
            data  = self.graph.nodes[node_id]
            color = author_color.get(data["author"], "#888")
            title = (
                f"<b>{data['sha']}</b><br>"
                f"<b>Author:</b> {data['author']}<br>"
                f"<b>Date:</b> {data['timestamp'][:10]}<br>"
                f"<b>Message:</b> {data['message'][:80]}<br>"
                f"<b>Files:</b> {data['files'][:100]}"
            )
            net.add_node(
                node_id,
                label=f"{data['sha'][:7]}\n{data['author'].split()[0]}\n{data['timestamp'][:10]}",
                title=title,
                color={"background": color, "border": "#0d0d0f", "highlight": {"background": color, "border": "#fff"}},
                size=18,
                font={"size": 9, "color": "#aaa", "face": "monospace"},
                borderWidth=1,
                shadow=True
            )

        for src, tgt, edata in subgraph.edges(data=True):
            net.add_edge(
                src, tgt,
                color={"color": "#1e1e2e", "highlight": "#7F77DD"},
                width=min(1 + edata["weight"] * 0.4, 3),
                title=f"Shared files: {', '.join(edata['files'][:3])}",
                arrows={"to": {"enabled": True, "scaleFactor": 0.5}}
            )

        legend_html = "".join([
            f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:12px;">'
            f'<span style="width:10px;height:10px;border-radius:50%;background:{author_color[a]};display:inline-block;"></span>'
            f'<span style="font-size:11px;color:#888;">{a.split()[0]} ({author_counts[a]})</span></span>'
            for a in sorted_authors[:8]
        ])

        net.save_graph(output_path)
        with open(output_path, "r", encoding="utf-8") as f:
            html = f.read()

        injection = f"""
        <div style="position:fixed;top:12px;left:50%;transform:translateX(-50%);
                    background:#111115;border:1px solid #1e1e24;border-radius:8px;
                    padding:8px 16px;z-index:999;display:flex;align-items:center;
                    gap:4px;flex-wrap:wrap;max-width:90vw;box-shadow:0 4px 20px rgba(0,0,0,0.5);">
            <span style="font-size:11px;color:#444;margin-right:8px;font-weight:600;">Authors</span>
            {legend_html}
        </div>
        <div style="position:fixed;bottom:12px;left:50%;transform:translateX(-50%);
                    background:#111115;border:1px solid #1e1e24;border-radius:6px;
                    padding:6px 14px;z-index:999;">
            <span style="font-size:11px;color:#444;">
                Arrow = time direction &nbsp;·&nbsp; Color = author &nbsp;·&nbsp; Hover node for details
            </span>
        </div>"""
        html = html.replace("</body>", injection + "</body>")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _author_color(self, author):
        colors = ["#1D9E75","#E24B4A","#7F77DD","#378ADD","#D85A30","#BA7517","#D4537E"]
        return colors[hash(author) % len(colors)]