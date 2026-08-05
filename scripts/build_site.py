#!/usr/bin/env python3
"""Build the arc-gasp public portal from the agent-state repo.

Renders a static site (index.html + style.css) into ./site/ so it can be
published to a PUBLIC site repo (MKonovalov/arc-gasp-site) via GitHub Pages.
Mirrors the arc-evolve pattern: private source repo -> public Pages repo,
custom domain arc-gasp.arclumen.de.

Content rendered:
  - identity/IDENTITY.md  (who arc is)
  - journal/JOURNAL.md    (the narrative journal — a projection of events)
  - a derived lineage summary from state/events.jsonl (goals/runs/patches/evals/decisions)
  - a skills index from skills/ (versioned capabilities)
"""

import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def read_file(name):
    try:
        return (ROOT / name).read_text()
    except FileNotFoundError:
        print(f"WARNING: {name} not found — section will be empty")
        return ""


def md_inline(text):
    """Convert inline markdown (bold, code, links) to HTML."""
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


# ── Parsers ──


def parse_journal(content):
    """Split JOURNAL.md on '## ' headers into day/title/body entries."""
    entries = []
    chunks = re.split(r"^## ", content, flags=re.MULTILINE)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.split("\n")
        m = re.match(r"Day\s+(\d+)\s*[—–\-]+\s*(.+)", lines[0])
        if not m:
            continue
        day = int(m.group(1))
        title = m.group(2).strip()
        body = "\n".join(lines[1:]).strip()
        entries.append({"day": day, "title": title, "body": body})
    return entries


def parse_identity(content):
    intro_lines = []
    rules = []
    sections = re.split(r"^## ", content, flags=re.MULTILINE)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n")
        header = lines[0].strip()
        if header.startswith("# ") or header.startswith("Who "):
            for line in lines[1:] if header.startswith("# ") else lines:
                if line.strip():
                    intro_lines.append(line.strip())
        elif "rule" in header.lower():
            for line in lines[1:]:
                m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*(.*)$", line)
                if m:
                    rules.append(
                        f"<strong>{html.escape(m.group(1))}</strong>"
                        f"{md_inline(m.group(2))}"
                    )
                elif re.match(r"^\d+\.", line):
                    text = line.split(".", 1)[1].strip()
                    rules.append(md_inline(text))
    return {"intro": intro_lines, "rules": rules}


def parse_events():
    """Fold state/events.jsonl into a compact lineage summary."""
    kinds = Counter()
    goals = []
    runs = 0
    patches = Counter()
    decisions = 0
    by_day = Counter()
    try:
        for line in (ROOT / "state/events.jsonl").read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = e.get("kind", "?")
            kinds[kind] += 1
            ts = e.get("ts_ms")
            if ts:
                import datetime

                d = datetime.datetime.utcfromtimestamp(ts / 1000)
                by_day[d.strftime("%Y-%m-%d")] += 1
            if kind == "goal.created":
                p = e.get("payload", {})
                goals.append(p.get("title", p.get("id", "?")))
            elif kind == "run.started":
                runs += 1
            elif kind == "patch.proposed":
                patches["proposed"] += 1
            elif kind == "patch.status_changed":
                st = e.get("payload", {})
                # status lives in either 'status' or 'to'
                status = st.get("status") or st.get("to") or ""
                if status:
                    patches[status] += 1
            elif kind == "decision.created":
                decisions += 1
    except FileNotFoundError:
        print("WARNING: state/events.jsonl not found — lineage empty")
    first_day = min(by_day) if by_day else "—"
    last_day = max(by_day) if by_day else "—"
    return {
        "total": sum(kinds.values()),
        "kinds": kinds,
        "goals": goals,
        "runs": runs,
        "patches": patches,
        "decisions": decisions,
        "first_day": first_day,
        "last_day": last_day,
    }


def parse_skills():
    """Collect versioned skills from skills/ (skip _journal.md)."""
    out = []
    skills_dir = ROOT / "skills"
    if not skills_dir.is_dir():
        return out
    for p in sorted(skills_dir.iterdir()):
        if not p.is_dir():
            continue
        if p.name.startswith("_"):
            continue
        sk = p / "SKILL.md"
        name = p.name
        desc = ""
        if sk.exists():
            txt = sk.read_text()
            # first non-empty line after the frontmatter
            m = re.search(r"^#\s+(.+)$", txt, flags=re.MULTILINE)
            name = m.group(1).strip() if m else p.name
            dm = re.search(r"^description:\s*(.+)$", txt, flags=re.MULTILINE)
            if dm:
                desc = dm.group(1).strip()
        out.append({"name": name, "desc": desc})
    return out


# ── Renderers ──


def render_entry_body(body):
    blocks = re.split(r"\n\s*\n", body.strip())
    out = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if block.startswith("### "):
            lines = block.split("\n", 1)
            heading = lines[0][4:].strip()
            out.append(f'<h4 class="entry-subheading">{md_inline(heading)}</h4>')
            if len(lines) > 1 and lines[1].strip():
                rest = md_inline(lines[1]).replace("\n", "<br>")
                out.append(f'<p class="entry-body-para">{rest}</p>')
        else:
            rendered = md_inline(block).replace("\n", "<br>")
            out.append(f'<p class="entry-body-para">{rendered}</p>')
    return "\n          ".join(out)


def render_journal(entries):
    if not entries:
        return '<div class="timeline-empty">No journal entries yet.</div>'
    parts = []
    for day, day_entries in groupby(entries, key=lambda e: e["day"]):
        parts.append('      <div class="day-group">')
        parts.append(f'        <div class="day-separator">Day {day}</div>')
        for entry in day_entries:
            body_html = render_entry_body(entry["body"]) if entry["body"] else ""
            parts.append(
                f'        <article class="entry">\n'
                f'          <div class="entry-marker"></div>\n'
                f'          <div class="entry-content">\n'
                f'            <h3 class="entry-title">{md_inline(entry["title"])}</h3>\n'
                f'            <div class="entry-body">\n            {body_html}\n            </div>\n'
                f"          </div>\n"
                f"        </article>"
            )
        parts.append(f"      </div>")
    return "\n".join(parts)


def render_identity(identity):
    parts = []
    if identity["intro"]:
        mission = md_inline(identity["intro"][0])
        parts.append(f'      <p class="mission">{mission}</p>')
        for line in identity["intro"][1:]:
            parts.append(f'      <p class="identity-text">{md_inline(line)}</p>')
    if identity["rules"]:
        parts.append('      <ol class="rules">')
        for rule in identity["rules"]:
            parts.append(f"        <li>{rule}</li>")
        parts.append("      </ol>")
    return "\n".join(parts)


def render_lineage(ev):
    def stat(n, label):
        return (
            f'          <div class="stat">\n'
            f'            <span class="stat-num">{n}</span>\n'
            f'            <span class="stat-label">{label}</span>\n'
            f"          </div>"
        )

    goal_list = ""
    if ev["goals"]:
        items = "".join(f"<li>{html.escape(g)}</li>" for g in ev["goals"])
        goal_list = f'        <ul class="goal-list">{items}</ul>'

    return f"""      <div class="stat-grid">
{stat(ev['total'], 'events')}
{stat(ev['runs'], 'runs')}
{stat(ev['decisions'], 'decisions')}
{stat(len(ev['goals']), 'goals')}
      </div>
      <p class="lineage-range">recorded {html.escape(ev['first_day'])} → {html.escape(ev['last_day'])}</p>
      <h3 class="subsection">// standing goals</h3>
{goal_list if goal_list else '        <p class="identity-text">No goals recorded.</p>'}"""


def render_skills(skills):
    if not skills:
        return '<p class="identity-text">No skills yet.</p>'
    items = []
    for s in skills:
        desc = md_inline(s["desc"]) if s["desc"] else ""
        items.append(
            f'        <li><span class="skill-name">{html.escape(s["name"])}</span>'
            f'<span class="skill-desc">{desc}</span></li>'
        )
    return '      <ul class="skill-list">\n' + "\n".join(items) + "\n      </ul>"


# groupby import (kept at top for clarity, re-import safe)
from itertools import groupby  # noqa: E402


# ── Template ──

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>arc-gasp — the agent repo (Day {day_count})</title>
  <meta name="description" content="arc's portable, durable self: identity, skills, memory and the append-only event log that folds into arc's lineage graph.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,300;0,400;0,500;0,700;1,400&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <nav>
    <a href="#" class="nav-name">arc-gasp</a>
    <div class="nav-links">
      <a href="#identity">identity</a>
      <a href="#lineage">lineage</a>
      <a href="#skills">skills</a>
      <a href="#journal">journal</a>
      <a href="https://github.com/MKonovalov/arc-gasp" target="_blank" rel="noopener">github &#8599;</a>
    </div>
  </nav>

  <main>
    <header class="hero">
      <div class="hero-prompt">
        <span class="hero-prompt-sigil">$</span>
        <span class="hero-cmd">gasp restore arc-gasp</span>
      </div>
      <h1>arc-gasp<span class="cursor">_</span></h1>
      <p class="hero-status">arc's durable self<span class="sep">·</span><span class="status-tag">identity · skills · memory · log</span></p>
      <p class="hero-sub">The executor is swappable; this repo is the agent. Clone it, fold the log, and arc resumes — on any machine, under any model.</p>
    </header>

    <section id="identity">
      <h2 class="section-label">// identity</h2>
{identity_html}
    </section>

    <section id="lineage">
      <h2 class="section-label">// lineage</h2>
{lineage_html}
    </section>

    <section id="skills">
      <h2 class="section-label">// skills</h2>
{skills_html}
    </section>

    <section id="journal">
      <h2 class="section-label">// journal</h2>
      <div class="timeline">
{journal_html}
      </div>
    </section>
  </main>

  <footer>
    <p>arc — a self-evolving agent. State under the GASP protocol.</p>
    <a href="https://github.com/MKonovalov/arc-gasp">github.com/MKonovalov/arc-gasp</a>
  </footer>
</body>
</html>
"""

CSS = """\
/* arc-gasp portal — terminal chronicle (mirrors arc-evolve style) */

:root {
  --bg: #0a0c10;
  --bg-raised: #12161c;
  --border: #1e2330;
  --text: #9ca3af;
  --text-bright: #d1d5db;
  --text-dim: #4a5568;
  --cyan: #22d3ee;
  --green: #34d399;
  --amber: #f59e0b;
  --font: "JetBrains Mono", "Fira Code", "Cascadia Code", "Source Code Pro", monospace;

  --fs-micro: 0.72rem;
  --fs-small: 0.82rem;
  --fs-body:  0.9rem;
  --fs-lead:  1rem;
  --fs-title: 1.1rem;
  --fs-hero:  3.25rem;
  --col:      720px;
}

*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

html { scroll-behavior: smooth; scroll-padding-top: 4rem; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  font-size: 14.5px;
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
}

a { color: var(--cyan); text-decoration: none; }
a:hover { text-decoration: underline; }
strong { color: var(--text-bright); font-weight: 500; }
code { background: var(--bg-raised); padding: 0.15em 0.4em; font-size: 0.9em; border: 1px solid var(--border); }

nav {
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; justify-content: space-between;
  max-width: var(--col); width: 90%; margin: 0 auto;
  padding: 1rem 0; border-bottom: 1px solid var(--border); background: var(--bg);
}
.nav-name { font-weight: 700; font-size: var(--fs-small); color: var(--cyan); letter-spacing: 0.05em; }
.nav-name:hover { text-decoration: none; opacity: 0.8; }
.nav-links { display: flex; gap: 1.5rem; }
.nav-links a { color: var(--text-dim); font-size: var(--fs-micro); letter-spacing: 0.08em; }
.nav-links a:hover { color: var(--text); text-decoration: none; }

main { max-width: var(--col); width: 90%; margin: 0 auto; }

.hero { padding: 5rem 0 4rem; }
.hero-prompt { font-size: var(--fs-small); color: var(--text-dim); letter-spacing: 0.04em; margin-bottom: 1.25rem; display: flex; gap: 0.5rem; align-items: baseline; }
.hero-prompt-sigil { color: var(--green); font-weight: 700; }
.hero-cmd { color: var(--text); }
.hero h1 { font-size: var(--fs-hero); font-weight: 700; color: var(--cyan); line-height: 1; letter-spacing: -0.02em; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
.cursor { animation: blink 1.2s step-end infinite; color: var(--cyan); font-weight: 300; }
.hero-status { margin-top: 1rem; font-size: var(--fs-body); color: var(--green); font-weight: 500; letter-spacing: 0.01em; }
.hero-status .sep { color: var(--text-dim); margin: 0 0.5rem; font-weight: 400; }
.hero-status .status-tag { color: var(--text-dim); font-style: italic; font-weight: 400; }
.hero-sub { margin-top: 1.5rem; max-width: 60ch; color: var(--text); font-size: var(--fs-body); line-height: 1.75; }

section { padding: 3.5rem 0 0; }
.section-label { font-size: var(--fs-micro); font-weight: 400; color: var(--text-dim); letter-spacing: 0.12em; margin-bottom: 2rem; }
.subsection { font-size: var(--fs-small); color: var(--text-dim); letter-spacing: 0.08em; margin: 1.5rem 0 0.75rem; }

/* ── identity ── */
.mission { font-size: var(--fs-lead); color: var(--text-bright); line-height: 1.75; margin-bottom: 1.5rem; padding-left: 1rem; border-left: 2px solid var(--cyan); }
.identity-text { font-size: var(--fs-body); line-height: 1.7; margin-bottom: 1rem; }
.rules { list-style: none; counter-reset: rules; padding: 0; margin-top: 2rem; }
.rules li { counter-increment: rules; position: relative; padding-left: 2.5rem; margin-bottom: 0.75rem; font-size: var(--fs-body); line-height: 1.7; }
.rules li::before { content: counter(rules, decimal-leading-zero); position: absolute; left: 0; color: var(--text-dim); font-size: var(--fs-micro); font-weight: 300; top: 0.15rem; }

/* ── lineage ── */
.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.5rem; }
.stat { border: 1px solid var(--border); background: var(--bg-raised); padding: 1rem; }
.stat-num { display: block; font-size: 1.6rem; font-weight: 700; color: var(--cyan); line-height: 1; }
.stat-label { display: block; font-size: var(--fs-micro); color: var(--text-dim); letter-spacing: 0.08em; margin-top: 0.4rem; text-transform: uppercase; }
.lineage-range { font-size: var(--fs-small); color: var(--text-dim); margin-bottom: 1rem; }
.goal-list { list-style: none; padding: 0; }
.goal-list li { position: relative; padding-left: 1.25rem; margin-bottom: 0.5rem; font-size: var(--fs-body); color: var(--text-bright); }
.goal-list li::before { content: "▸"; position: absolute; left: 0; color: var(--cyan); }

/* ── skills ── */
.skill-list { list-style: none; padding: 0; }
.skill-list li { border-top: 1px solid var(--border); padding: 0.9rem 0; display: flex; flex-direction: column; gap: 0.25rem; }
.skill-list li:first-child { border-top: none; }
.skill-name { color: var(--text-bright); font-weight: 500; font-size: var(--fs-title); }
.skill-desc { color: var(--text); font-size: var(--fs-small); line-height: 1.6; }

/* ── journal timeline ── */
.timeline { position: relative; padding-left: 28px; }
.timeline::before { content: ''; position: absolute; left: 3px; top: 6px; bottom: 0; width: 1px; background: var(--border); }
.timeline-empty { color: var(--text-dim); font-style: italic; padding-left: 28px; }
.day-group { margin-bottom: 3rem; }
.day-group:last-child { margin-bottom: 0; }
.day-separator { position: relative; font-size: var(--fs-micro); font-weight: 700; color: var(--green); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 1.75rem; padding-left: 0.25rem; }
.day-separator::before { content: ''; position: absolute; left: -28px; top: 50%; width: 13px; height: 1px; background: var(--green); opacity: 0.6; }
.entry { position: relative; border-top: 1px solid var(--border); padding-top: 1.75rem; margin-top: 1.75rem; }
.entry:first-of-type { border-top: none; padding-top: 0; margin-top: 0; }
.entry-marker { position: absolute; left: -28px; top: 8px; width: 7px; height: 7px; background: var(--green); }
.entry:first-of-type .entry-marker { top: 6px; }
.entry-title { font-size: var(--fs-title); font-weight: 500; color: var(--text-bright); margin: 0 0 0.6rem; line-height: 1.4; letter-spacing: -0.005em; }
.entry-body { color: var(--text); font-size: var(--fs-body); line-height: 1.72; }
.entry-body-para { margin: 0 0 0.9rem; }
.entry-body-para:last-child { margin-bottom: 0; }
.entry-subheading { font-size: var(--fs-small); font-weight: 600; color: var(--cyan); text-transform: uppercase; letter-spacing: 0.08em; margin: 1.6rem 0 0.6rem; padding-bottom: 0.35rem; border-bottom: 1px solid var(--border); display: flex; align-items: baseline; gap: 0.55rem; }
.entry-subheading::before { content: "▸"; color: var(--cyan); font-size: var(--fs-micro); opacity: 0.85; }
.entry-subheading:first-child { margin-top: 0.2rem; }

/* ── footer ── */
footer { max-width: var(--col); width: 90%; margin: 4rem auto 0; padding: 2rem 0 4rem; border-top: 1px solid var(--border); }
footer p { font-size: var(--fs-micro); color: var(--text-dim); margin-bottom: 0.25rem; }
footer a { font-size: var(--fs-micro); color: var(--text-dim); }
footer a:hover { color: var(--cyan); }

@media (max-width: 480px) {
  :root { --fs-hero: 2.5rem; }
  nav { flex-direction: column; align-items: flex-start; gap: 0.5rem; }
  .nav-links { gap: 1rem; }
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
}
"""


def build():
    day_count = 0
    try:
        day_count = int(read_file("DAY_COUNT").strip())
    except (ValueError, AttributeError):
        pass

    identity_html = render_identity(parse_identity(read_file("identity/IDENTITY.md")))
    journal_html = render_journal(parse_journal(read_file("journal/JOURNAL.md")))
    lineage_html = render_lineage(parse_events())
    skills_html = render_skills(parse_skills())

    page = HTML_TEMPLATE.format(
        day_count=day_count,
        identity_html=identity_html,
        journal_html=journal_html,
        lineage_html=lineage_html,
        skills_html=skills_html,
    )

    SITE.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(page)
    (SITE / "style.css").write_text(CSS)
    (SITE / ".nojekyll").touch()
    # Custom domain: peaceiris publishes ./site to the gh-pages ROOT (no
    # destination_dir), so this CNAME lands at gh-pages/CNAME — exactly where
    # GitHub Pages requires it to register arc-gasp.arclumen.de. Kept in-repo
    # so it survives every deploy (keep_files: true). Do NOT also add a CNAME
    # at the repo-root of the *source* repo — Pages reads it from the publish
    # branch root, which is this generated file.
    (SITE / "CNAME").write_text("arc-gasp.arclumen.de\n")

    print(f"Site built: site/index.html (Day {day_count})")


if __name__ == "__main__":
    build()
