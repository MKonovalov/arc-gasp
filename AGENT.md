# AGENT — arc 🐙

```yaml
spec_version: 1
agent_id: arc
identity_hash: 7e83f90500b98bd4af1f172be591aeabd29be9ef2bb2672b6729adef577b2209
executor: .agent/config.toml
```

This repo is **arc's durable state** per the [GASP protocol](https://github.com/MKonovalov/gasp):
identity, skills, memory, and the append-only semantic event log that folds into
arc's lineage graph. The **executor binding** lives in `.agent/config.toml`
(currently [MKonovalov/arc-evolve](https://github.com/MKonovalov/arc-evolve), the
self-evolving runtime arc works on); patches recorded here pin its commits as
artifacts. Clone this repo and fold the log to restore arc anywhere, on any
conformant runtime.

## Provenance

Seeded 2026-07-02 from `MKonovalov/arc-evolve@582147ad5728b9a74477729e67e46df2d2ac8ba0`
(the working-tree state of that commit, through Day 124), completed 2026-07-03
with the lineage/dream/notes state below. Identity files are byte-for-byte
copies; `identity/PRINCIPLES.md` is arc-evolve's `ECONOMICS.md`;
`memory/notes.json` is `.arc/memory.json` and `memory/social_cursors.json` is
`.arc/social-state.json`. Skill bodies were rebound to this layout's paths
(`memory/learnings.jsonl` → `memory/facts.jsonl`, `journals/` → `journal/`, …);
executor-side material (runtime source, `CLAUDE.md`, `docs/`, `sponsors/`,
scheduler counters) intentionally stays in arc-evolve.

`memory/facts.jsonl` carries the original `memory/learnings.jsonl` lines
verbatim (arc's historical learning format). Facts appended after seeding
MUST follow the GASP fact envelope (`id`, `ts_ms`, `text`, `derived_from`,
`supersedes`); legacy-format lines end at the seed.

## Locations

| GASP role | path | notes |
|---|---|---|
| event log | `state/events.jsonl` | source of truth, append-only |
| identity | `identity/` | human-gated; hash above, recipe below |
| lineage record | `LINEAGE.md` | genealogy (generation, ancestor, birthday) — a record, not constitution, so outside the identity hash |
| skills | `skills/` | versioned; one change per commit; `skills/_journal.md` is the skill-evolution journal, not a skill. Kept current by mirror-on-change: promoted skill changes in the executor are mirrored here (paths rebound to this layout) in the same boundary commit as their events |
| retired skills | `skills_attic/` | created on first retirement; a retirement is a patch whose commit is the attic move |
| facts | `memory/facts.jsonl` (+ `memory/social_facts.jsonl`) | append-only derived layer; social pair mirrors facts → active memory, declared here per the GASP manifest-binding rule |
| memory synthesis | `memory/active_memory.md` (+ `active_social_memory.md`) | regenerable projection |
| agent notes | `memory/notes.json` | durable runtime notes (was `.arc/memory.json`) |
| social cursors | `memory/social_cursors.json` | seen/replied discussion state (was `.arc/social-state.json`) |
| journal | `journal/` | seeded history through Day 124; `JOURNAL.md` is append-only (conformance check 4) — new run entries are appended, existing lines never rewritten |
| dreams | `DREAM.md`, `dreams/` | self-model narrative + append-only dream log |
| age | `DAY_COUNT` | arc's day counter — identity-adjacent |

## Identity hash recipe

SHA-256 over each `identity/` file's relative path followed by a newline and its
bytes, in byte-order-sorted path order:

```
find identity -type f | LC_ALL=C sort | while IFS= read -r f; do printf '%s\n' "$f"; cat "$f"; done | shasum -a 256
```

An identity change updates `identity/`, this hash, and appends a `decision`
event — all in one human-gated commit (GASP Part I, commit rule 4).
