# retrieval/graph.py
import json
import networkx as nx
from collections import defaultdict
from datetime import datetime

class CommitGraph:

    def __init__(self, chunks_path: str = "./data/raw/chunks.json"):
        self.graph = nx.DiGraph()
        self.chunks = self._load_chunks(chunks_path)
        self._build(self.chunks)

    def _load_chunks(self, path):
        with open(path) as f:
            return json.load(f)

    def _build(self, chunks):
        sorted_chunks = sorted(chunks, key=lambda c: c["metadata"]["timestamp"])
        for chunk in sorted_chunks:
            meta = chunk["metadata"]
            self.graph.add_node(chunk["id"],
                sha=meta["sha"], author=meta["author"],
                timestamp=meta["timestamp"], files=meta["files"],
                message=chunk["text"].split("\n")[0].replace("COMMIT: ", ""),
                has_pr=meta["has_pr"], score=0.0)
        file_to_commits = defaultdict(list)
        for chunk in sorted_chunks:
            for f in chunk["metadata"]["files"].split(", "):
                f = f.strip()
                if f:
                    file_to_commits[f].append(chunk["id"])
        for file, commit_ids in file_to_commits.items():
            for i in range(len(commit_ids) - 1):
                src, tgt = commit_ids[i], commit_ids[i+1]
                if self.graph.has_edge(src, tgt):
                    self.graph[src][tgt]["files"].append(file)
                    self.graph[src][tgt]["weight"] += 1
                else:
                    self.graph.add_edge(src, tgt, files=[file], weight=1)

    # ── Query helpers ──────────────────────────────────────────────
    def file_timeline(self, filename):
        results = [{"sha": c["metadata"]["sha"], "author": c["metadata"]["author"],
                    "timestamp": c["metadata"]["timestamp"],
                    "message": c["text"].split("\n")[0].replace("COMMIT: ", ""),
                    "files": c["metadata"]["files"], "has_pr": c["metadata"]["has_pr"]}
                   for c in self.chunks if filename.lower() in c["metadata"]["files"].lower()]
        return sorted(results, key=lambda x: x["timestamp"])

    def co_change_analysis(self, top_n=10):
        pc = defaultdict(int)
        for chunk in self.chunks:
            files = [f.strip() for f in chunk["metadata"]["files"].split(", ") if f.strip()]
            for i in range(len(files)):
                for j in range(i+1, len(files)):
                    pc[tuple(sorted([files[i], files[j]]))] += 1
        return [{"files": list(p), "co_changes": c}
                for p, c in sorted(pc.items(), key=lambda x: x[1], reverse=True)[:top_n]]

    def author_analysis(self):
        ad = defaultdict(lambda: {"commits": 0, "files": defaultdict(int)})
        for chunk in self.chunks:
            a = chunk["metadata"]["author"]
            ad[a]["commits"] += 1
            for f in chunk["metadata"]["files"].split(", "):
                f = f.strip()
                if f: ad[a]["files"][f] += 1
        return sorted([{"author": a, "commits": d["commits"],
                        "top_files": [{"file": f, "changes": c} for f, c in
                                      sorted(d["files"].items(), key=lambda x: x[1], reverse=True)[:5]]}
                       for a, d in ad.items()], key=lambda x: x["commits"], reverse=True)

    def hottest_files(self, top_n=10):
        fc = defaultdict(int)
        for chunk in self.chunks:
            for f in chunk["metadata"]["files"].split(", "):
                f = f.strip()
                if f: fc[f] += 1
        return [{"file": f, "change_count": c}
                for f, c in sorted(fc.items(), key=lambda x: x[1], reverse=True)[:top_n]]

    # ── Helpers ────────────────────────────────────────────────────
    @staticmethod
    def _commit_type(msg):
        m = msg.lower()
        if any(w in m for w in ["fix","bug","patch","hotfix","error","issue"]):
            return "fix", "#E24B4A"
        if any(w in m for w in ["feat","feature","add","new","implement","create"]):
            return "feat", "#1D9E75"
        if any(w in m for w in ["refactor","clean","restructure","reorganize"]):
            return "refactor", "#7F77DD"
        if any(w in m for w in ["doc","readme","comment","docs"]):
            return "docs", "#BA7517"
        if any(w in m for w in ["chore","update","bump","upgrade","deps","merge","release"]):
            return "chore", "#888780"
        return "other", "#378ADD"

    # ── Visualization A — Timeline Swimlane ────────────────────────
    def visualize_timeline(self, output_path="./data/timeline_graph.html"):
        sorted_chunks = sorted(self.chunks, key=lambda c: c["metadata"]["timestamp"])
        if not sorted_chunks:
            return

        author_counts = defaultdict(int)
        for c in sorted_chunks:
            author_counts[c["metadata"]["author"]] += 1
        top_authors = [a for a, _ in sorted(author_counts.items(),
                                             key=lambda x: x[1], reverse=True)[:8]]

        PALETTE = ["#7F77DD","#1D9E75","#E24B4A","#378ADD","#D85A30","#BA7517","#D4537E","#639922"]
        author_color = {a: PALETTE[i % len(PALETTE)] for i, a in enumerate(top_authors)}

        t_min = datetime.fromisoformat(sorted_chunks[0]["metadata"]["timestamp"])
        t_max = datetime.fromisoformat(sorted_chunks[-1]["metadata"]["timestamp"])
        t_range = max((t_max - t_min).total_seconds(), 1)

        LANE_H   = 130
        PAD_L    = 180
        PAD_R    = 60
        PAD_T    = 50
        R        = 14
        SVG_W    = 2800
        MIN_GAP  = 38
        SVG_H    = PAD_T + len(top_authors) * LANE_H + 70

        def tx(ts):
            t = datetime.fromisoformat(ts)
            return PAD_L + int(((t - t_min).total_seconds() / t_range) * (SVG_W - PAD_L - PAD_R))

        # Compute positions, enforce min gap
        author_commits = defaultdict(list)
        for chunk in sorted_chunks:
            if chunk["metadata"]["author"] in top_authors:
                author_commits[chunk["metadata"]["author"]].append(chunk)

        node_data = {}
        for i, author in enumerate(top_authors):
            y = PAD_T + i * LANE_H + LANE_H // 2
            commits = author_commits[author]
            last_x = PAD_L - MIN_GAP
            for chunk in commits:
                x = max(tx(chunk["metadata"]["timestamp"]), last_x + MIN_GAP)
                last_x = x
                msg = chunk["text"].split("\n")[0].replace("COMMIT: ", "")
                ctype, ccolor = self._commit_type(msg)
                safe_id = chunk["id"].replace("-", "_")
                node_data[chunk["id"]] = {
                    "safe": safe_id, "x": x, "y": y,
                    "color": ccolor, "acolor": author_color[author],
                    "type": ctype, "sha": chunk["metadata"]["sha"],
                    "author": author, "date": chunk["metadata"]["timestamp"][:10],
                    "msg": msg[:120].replace('"', "'"),
                    "files": chunk["metadata"]["files"][:150].replace('"', "'"),
                }

        lines = []
        nodes = []
        tips  = []

        # Lane backgrounds + left accent + author label
        for i, author in enumerate(top_authors):
            y0 = PAD_T + i * LANE_H
            ac = author_color[author]
            bg = "#0f0f14" if i % 2 == 0 else "#0d0d0f"
            cy = y0 + LANE_H // 2
            lines.append(f'<rect x="0" y="{y0}" width="{SVG_W}" height="{LANE_H}" fill="{bg}"/>')
            lines.append(f'<rect x="0" y="{y0}" width="5" height="{LANE_H}" fill="{ac}"/>')
            # guide line
            lines.append(f'<line x1="{PAD_L}" y1="{cy}" x2="{SVG_W}" y2="{cy}" stroke="#18181f" stroke-width="1.5" stroke-dasharray="6,6"/>')
            # author name (large)
            lines.append(f'<text x="14" y="{cy - 8}" font-family="ui-monospace,monospace" font-size="14" font-weight="700" fill="{ac}">{author.split()[0]}</text>')
            lines.append(f'<text x="14" y="{cy + 10}" font-family="ui-monospace,monospace" font-size="10" fill="#444">{author_counts[author]} commits</text>')

        # Connector lines with arrows
        for author in top_authors:
            commits = author_commits[author]
            for j in range(len(commits) - 1):
                a = commits[j]["id"]
                b = commits[j+1]["id"]
                if a in node_data and b in node_data:
                    x1,y1 = node_data[a]["x"], node_data[a]["y"]
                    x2,y2 = node_data[b]["x"], node_data[b]["y"]
                    # draw line
                    lines.append(f'<line x1="{x1+R}" y1="{y1}" x2="{x2-R}" y2="{y2}" stroke="#252530" stroke-width="2"/>')
                    # arrowhead at midpoint
                    mx = (x1 + x2) / 2
                    lines.append(f'<polygon points="{mx-4},{y1-4} {mx+6},{y1} {mx-4},{y1+4}" fill="#333344"/>')

        # Nodes
        for nid, nd in node_data.items():
            x, y, c, sid = nd["x"], nd["y"], nd["color"], nd["safe"]
            nodes.append(
                f'<circle id="n_{sid}" cx="{x}" cy="{y}" r="{R}" '
                f'fill="{c}" stroke="#0d0d0f" stroke-width="2.5" '
                f'style="cursor:pointer;filter:drop-shadow(0 2px 6px {c}55);" '
                f'onmouseenter="showTip(\'{sid}\',event)" onmouseleave="hideTip()" '
                f'onclick="pinTip(\'{sid}\')"/>'
            )
            # SHA only — no date label (too cluttered)
            nodes.append(
                f'<text x="{x}" y="{y+R+13}" text-anchor="middle" '
                f'font-family="ui-monospace,monospace" font-size="9" fill="#3a3a4a" '
                f'pointer-events="none">{nd["sha"][:7]}</text>'
            )
            # tooltip data
            tips.append(
                f'<div id="tip_{sid}" class="td" '
                f'data-sha="{nd["sha"]}" data-author="{nd["author"]}" '
                f'data-date="{nd["date"]}" data-type="{nd["type"]}" '
                f'data-color="{c}" data-msg="{nd["msg"]}" data-files="{nd["files"]}"></div>'
            )

        # Date axis
        axis_y = SVG_H - 24
        lines.append(f'<line x1="{PAD_L}" y1="{axis_y}" x2="{SVG_W-PAD_R}" y2="{axis_y}" stroke="#1e1e2a" stroke-width="1.5"/>')
        for i in range(9):
            frac = i / 8
            tx2 = PAD_L + frac * (SVG_W - PAD_L - PAD_R)
            ts2 = t_min.timestamp() + frac * t_range
            d = datetime.fromtimestamp(ts2).strftime("%b %d")
            lines.append(f'<line x1="{tx2}" y1="{axis_y-5}" x2="{tx2}" y2="{axis_y+5}" stroke="#333" stroke-width="1"/>')
            lines.append(f'<text x="{tx2}" y="{axis_y+18}" text-anchor="middle" font-family="ui-monospace,monospace" font-size="10" fill="#555">{d}</text>')

        legend_items = [("feat","#1D9E75"),("fix","#E24B4A"),("refactor","#7F77DD"),
                        ("docs","#BA7517"),("chore","#888780"),("other","#378ADD")]
        legend_html = "".join([
            f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:16px;">'
            f'<span style="width:11px;height:11px;border-radius:50%;background:{c};flex-shrink:0;'
            f'box-shadow:0 0 6px {c}66;"></span>'
            f'<span style="font-size:12px;color:#888;font-family:monospace;">{lbl}</span></span>'
            for lbl, c in legend_items
        ])

        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d0d0f;overflow-x:auto;overflow-y:hidden;font-family:sans-serif}}
#wrap{{overflow-x:auto;overflow-y:hidden;width:100vw;height:100vh}}
svg{{display:block}}
.td{{display:none}}
#tt{{
  display:none;position:fixed;z-index:999;
  background:#13131a;border:1px solid #2a2a3e;border-radius:12px;
  padding:14px 18px;min-width:280px;max-width:360px;
  box-shadow:0 12px 40px rgba(0,0,0,0.7);pointer-events:none;
}}
#tt.pinned{{pointer-events:all}}
.t-sha{{font-family:monospace;font-size:13px;color:#7F77DD;margin-bottom:8px;font-weight:600;word-break:break-all}}
.t-row{{font-size:12px;color:#666;margin-bottom:5px;line-height:1.5}}
.t-row b{{color:#bbb;margin-right:4px}}
.t-badge{{display:inline-block;padding:2px 9px;border-radius:20px;font-size:10px;
  font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-left:4px}}
.t-close{{position:absolute;top:10px;right:12px;color:#444;cursor:pointer;font-size:16px;line-height:1}}
.t-close:hover{{color:#ccc}}
.t-msg{{font-size:12px;color:#aaa;margin-top:4px;line-height:1.6}}
.t-files{{font-size:10px;color:#555;font-family:monospace;margin-top:4px;line-height:1.7;word-break:break-all}}
#legend{{
  position:fixed;bottom:16px;left:50%;transform:translateX(-50%);
  background:#111118;border:1px solid #1e1e28;border-radius:10px;
  padding:10px 20px;display:flex;align-items:center;gap:2px;z-index:100;
  box-shadow:0 4px 20px rgba(0,0,0,0.5);
}}
#hint{{position:fixed;top:14px;right:18px;background:#111118;border:1px solid #1e1e28;
  border-radius:8px;padding:8px 14px;font-size:11px;color:#444;z-index:100}}
</style></head><body>
<div id="wrap">
<svg width="{SVG_W}" height="{SVG_H}" xmlns="http://www.w3.org/2000/svg">
{''.join(lines)}
{''.join(nodes)}
</svg>
</div>
{''.join(tips)}
<div id="tt">
  <span class="t-close" onclick="hideTip()">&#x2715;</span>
  <div class="t-sha" id="t-sha"></div>
  <div class="t-row"><b>Author</b><span id="t-author"></span></div>
  <div class="t-row"><b>Date</b><span id="t-date"></span></div>
  <div class="t-row"><b>Type</b><span id="t-type"></span></div>
  <div class="t-row"><b>Message</b><div class="t-msg" id="t-msg"></div></div>
  <div class="t-row" style="margin-top:6px"><b>Files</b><div class="t-files" id="t-files"></div></div>
</div>
<div id="legend">
  <span style="font-size:11px;color:#444;margin-right:10px;font-family:monospace;">commit type</span>
  {legend_html}
</div>
<div id="hint">Scroll &#8594; to explore &nbsp;&#183;&nbsp; Click node to pin tooltip</div>
<script>
var pinned=false, cur=null;
function D(id){{return document.getElementById('tip_'+id)}}
function fill(id){{
  var d=D(id); if(!d) return;
  document.getElementById('t-sha').textContent=d.dataset.sha;
  document.getElementById('t-author').textContent=' '+d.dataset.author;
  document.getElementById('t-date').textContent=' '+d.dataset.date;
  document.getElementById('t-msg').textContent=d.dataset.msg;
  document.getElementById('t-files').textContent=d.dataset.files;
  document.getElementById('t-type').innerHTML=
    '<span class="t-badge" style="background:'+d.dataset.color+'22;color:'+d.dataset.color+'">'+d.dataset.type+'</span>';
}}
function pos(tt,x,y){{
  tt.style.left=Math.min(x+14,window.innerWidth-370)+'px';
  tt.style.top=Math.max(y-10,8)+'px';
}}
function showTip(id,e){{if(pinned)return;cur=id;fill(id);var tt=document.getElementById('tt');tt.style.display='block';pos(tt,e.clientX,e.clientY);}}
function hideTip(){{if(pinned)return;document.getElementById('tt').style.display='none';cur=null;}}
function pinTip(id){{
  var tt=document.getElementById('tt');
  if(pinned&&cur===id){{pinned=false;tt.classList.remove('pinned');tt.style.display='none';cur=null;return;}}
  pinned=true;cur=id;fill(id);
  var el=document.getElementById('n_'+id);
  var r=el.getBoundingClientRect();
  tt.style.display='block';tt.classList.add('pinned');pos(tt,r.x+20,r.y);
}}
</script>
</body></html>"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    # ── Visualization B — Commit Log (searchable table) ────────────
    def visualize_commit_log(self, output_path="./data/commit_log.html"):
        sorted_chunks = sorted(self.chunks, key=lambda c: c["metadata"]["timestamp"], reverse=True)

        author_counts = defaultdict(int)
        for c in sorted_chunks:
            author_counts[c["metadata"]["author"]] += 1
        sorted_authors = sorted(author_counts, key=lambda a: author_counts[a], reverse=True)
        PALETTE = ["#7F77DD","#1D9E75","#E24B4A","#378ADD","#D85A30","#BA7517","#D4537E","#639922"]
        author_color = {a: PALETTE[i % len(PALETTE)] for i, a in enumerate(sorted_authors)}

        rows = []
        for chunk in sorted_chunks:
            meta  = chunk["metadata"]
            msg   = chunk["text"].split("\n")[0].replace("COMMIT: ", "")
            ctype, ccolor = self._commit_type(msg)
            a     = meta["author"]
            ac    = author_color.get(a, "#888")
            files = [f.strip() for f in meta["files"].split(", ") if f.strip()]
            file_badges = " ".join(
                f'<span class="fb">{f.split("/")[-1]}</span>'
                for f in files[:6]
            ) + (" ..." if len(files) > 6 else "")

            rows.append(f"""
<tr class="cr" data-author="{a}" data-type="{ctype}">
  <td class="td-sha"><span class="sha">{meta["sha"][:8]}</span></td>
  <td class="td-date"><span class="date">{meta["timestamp"][:10]}</span></td>
  <td class="td-author"><span class="author-dot" style="background:{ac}"></span><span class="aname">{a.split()[0]}</span></td>
  <td class="td-type"><span class="badge" style="background:{ccolor}22;color:{ccolor}">{ctype}</span></td>
  <td class="td-msg">{msg[:90].replace('<','&lt;').replace('>','&gt;')}</td>
  <td class="td-files">{file_badges}</td>
</tr>""")

        author_filter_opts = "".join(
            f'<button class="fbtn" data-filter-author="{a}" onclick="filterAuthor(this)">'
            f'<span style="background:{author_color[a]};width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:5px;"></span>'
            f'{a.split()[0]} <span class="cnt">({author_counts[a]})</span></button>'
            for a in sorted_authors
        )
        type_filter_opts = "".join(
            f'<button class="fbtn" data-filter-type="{t}" onclick="filterType(this)">'
            f'<span style="background:{c};width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:5px;"></span>{t}</button>'
            for t, c in [("feat","#1D9E75"),("fix","#E24B4A"),("refactor","#7F77DD"),
                          ("docs","#BA7517"),("chore","#888780"),("other","#378ADD")]
        )

        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d0d0f;color:#ccc;font-family:ui-sans-serif,sans-serif;padding:20px 28px;}}
h2{{font-size:15px;color:#888;font-weight:500;margin-bottom:16px;font-family:monospace;}}
.controls{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:16px;}}
#search{{background:#111118;border:1px solid #222230;border-radius:8px;
  padding:8px 14px;font-size:13px;color:#ccc;outline:none;width:260px;font-family:monospace;}}
#search:focus{{border-color:#7F77DD55;}}
#search::placeholder{{color:#333}}
.fgroup{{display:flex;gap:6px;flex-wrap:wrap;align-items:center;}}
.flabel{{font-size:11px;color:#444;font-family:monospace;}}
.fbtn{{background:#111118;border:1px solid #1e1e28;border-radius:20px;
  padding:4px 12px;font-size:11px;color:#666;cursor:pointer;display:inline-flex;
  align-items:center;transition:all .15s;font-family:monospace;}}
.fbtn:hover,.fbtn.active{{border-color:#7F77DD55;color:#ccc;background:#1a1a24;}}
.fbtn .cnt{{color:#444;margin-left:2px;}}
.fbtn.active .cnt{{color:#888;}}
#clear-btn{{background:none;border:1px solid #1e1e28;border-radius:6px;
  padding:4px 10px;font-size:11px;color:#444;cursor:pointer;}}
#clear-btn:hover{{color:#ccc;border-color:#333;}}
table{{width:100%;border-collapse:collapse;font-size:12px;}}
th{{text-align:left;font-size:10px;font-weight:600;color:#444;
  letter-spacing:.07em;text-transform:uppercase;padding:6px 10px;
  border-bottom:1px solid #1a1a22;font-family:monospace;}}
.cr{{border-bottom:1px solid #111118;transition:background .1s;}}
.cr:hover{{background:#111118;}}
td{{padding:10px 10px;vertical-align:middle;}}
.sha{{font-family:monospace;font-size:12px;color:#7F77DD;background:#7F77DD11;
  padding:2px 7px;border-radius:4px;}}
.date{{font-family:monospace;font-size:11px;color:#555;white-space:nowrap;}}
.author-dot{{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px;flex-shrink:0;}}
.aname{{font-family:monospace;font-size:12px;color:#bbb;}}
.badge{{padding:2px 8px;border-radius:20px;font-size:10px;font-weight:700;
  letter-spacing:.05em;text-transform:uppercase;white-space:nowrap;font-family:monospace;}}
.td-msg{{max-width:320px;color:#999;font-size:12px;line-height:1.5;}}
.fb{{display:inline-block;background:#1a1a22;border:1px solid #222;border-radius:4px;
  padding:1px 6px;font-size:10px;color:#555;font-family:monospace;margin:1px 2px 1px 0;}}
#count{{font-size:11px;color:#444;font-family:monospace;margin-left:auto;}}
.hidden{{display:none!important;}}
</style></head><body>
<h2>&#9679; Commit Log &nbsp;&mdash;&nbsp; {len(sorted_chunks)} commits total</h2>
<div class="controls">
  <input id="search" placeholder="Search commits, files, authors..." oninput="applyFilters()">
  <div class="fgroup">
    <span class="flabel">Author:</span>
    {author_filter_opts}
  </div>
  <div class="fgroup">
    <span class="flabel">Type:</span>
    {type_filter_opts}
  </div>
  <button id="clear-btn" onclick="clearFilters()">Clear</button>
  <span id="count"></span>
</div>
<table>
<thead><tr>
  <th>SHA</th><th>Date</th><th>Author</th><th>Type</th><th>Message</th><th>Files</th>
</tr></thead>
<tbody id="tbody">
{''.join(rows)}
</tbody>
</table>
<script>
var activeAuthor=null, activeType=null;
function applyFilters(){{
  var q=document.getElementById('search').value.toLowerCase();
  var rows=document.querySelectorAll('.cr');
  var vis=0;
  rows.forEach(function(r){{
    var au=r.dataset.author, ty=r.dataset.type;
    var txt=r.textContent.toLowerCase();
    var ok=true;
    if(activeAuthor&&au!==activeAuthor) ok=false;
    if(activeType&&ty!==activeType) ok=false;
    if(q&&!txt.includes(q)) ok=false;
    r.classList.toggle('hidden',!ok);
    if(ok) vis++;
  }});
  document.getElementById('count').textContent=vis+' commits shown';
}}
function filterAuthor(btn){{
  var a=btn.dataset.filterAuthor;
  if(activeAuthor===a){{activeAuthor=null;btn.classList.remove('active');}}
  else{{
    document.querySelectorAll('[data-filter-author]').forEach(function(b){{b.classList.remove('active');}});
    activeAuthor=a;btn.classList.add('active');
  }}
  applyFilters();
}}
function filterType(btn){{
  var t=btn.dataset.filterType;
  if(activeType===t){{activeType=null;btn.classList.remove('active');}}
  else{{
    document.querySelectorAll('[data-filter-type]').forEach(function(b){{b.classList.remove('active');}});
    activeType=t;btn.classList.add('active');
  }}
  applyFilters();
}}
function clearFilters(){{
  activeAuthor=null;activeType=null;
  document.getElementById('search').value='';
  document.querySelectorAll('.fbtn').forEach(function(b){{b.classList.remove('active');}});
  applyFilters();
}}
applyFilters();
</script>
</body></html>"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _author_color(self, author):
        colors = ["#7F77DD","#1D9E75","#E24B4A","#378ADD","#D85A30","#BA7517","#D4537E"]
        return colors[hash(author) % len(colors)]