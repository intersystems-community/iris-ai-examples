"""
CareConnect — IVG ↔ Obsidian Knowledge Layer Sync

Bidirectional sync between the IVG persistent knowledge graph and an Obsidian
vault folder. Implements the "human inspection layer" from the article:
  https://towardsdatascience.com/designing-a-persistent-knowledge-layer-that-refuses-to-guess/

Vault structure written under $OBSIDIAN_VAULT_PATH/KnowledgeGraph/:
  Concepts/     — one note per SDoHConcept node
  Decisions/    — one note per SDoHDecision node
  Contradictions/ — one note per Contradiction node (human edits status here)

Export (IVG → Obsidian):
  Reads all three node types from IVG, writes/updates Markdown with YAML
  frontmatter. Non-destructive: human-editable fields (status, resolved_by,
  resolution_rationale) are preserved if already present.

Import (Obsidian → IVG):
  Scans Contradiction notes for frontmatter changes the human made.
  Writes status transitions and resolutions back to IVG. Only fields the
  human explicitly filled in are written — unmodified fields are left alone.
  Provenance chain stays intact: IVG node still traces to its original source.

Authoritative direction: IVG is the graph-of-record. Obsidian is
inspection + human-proposal. Import never overwrites source/rationale fields
that were set programmatically.

Usage (standalone):
    python obsidian_sync.py export   # IVG → Obsidian
    python obsidian_sync.py import   # Obsidian → IVG (dry-run by default)
    python obsidian_sync.py import --apply   # commit changes to IVG

Usage (from bolt API):
    POST /api/knowledge/obsidian-export
    POST /api/knowledge/obsidian-import  {"dry_run": false}
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Vault / IVG config
# ---------------------------------------------------------------------------

# Point OBSIDIAN_VAULT_PATH at your own vault. The default is a directory inside
# the container, which the compose file mounts, so the sync works out of the box
# without assuming anything about the host's filesystem.
VAULT_PATH = Path(os.environ.get("OBSIDIAN_VAULT_PATH", "/vault"))
KG_ROOT = VAULT_PATH / "KnowledgeGraph"
CONCEPTS_DIR = KG_ROOT / "Concepts"
DECISIONS_DIR = KG_ROOT / "Decisions"
CONTRADICTIONS_DIR = KG_ROOT / "Contradictions"

_IVG_HOST = os.environ.get("IVG_HOST", "careconnect-ivg-bolt")
_IVG_PORT = int(os.environ.get("IVG_PORT", "8000"))
_IVG_API_KEY = os.environ.get("IVG_API_KEY", "changeme")
_IVG_BASE = f"http://{_IVG_HOST}:{_IVG_PORT}"

# Fields the human owns in Contradiction notes — never overwritten on export
# if already set to a non-empty value by a human
_HUMAN_FIELDS = {"status", "resolved_by", "resolution_rationale"}

# Valid human-editable status transitions
_ALLOWED_TRANSITIONS = {
    ("UNRESOLVED", "RESOLVED"),
    ("UNRESOLVED", "DEFERRED"),
    ("DEFERRED", "RESOLVED"),
}


# ---------------------------------------------------------------------------
# Bolt API helpers
# ---------------------------------------------------------------------------

def _bolt_get(path: str) -> dict:
    import httpx
    try:
        resp = httpx.get(
            f"{_IVG_BASE}{path}",
            headers={"X-API-Key": _IVG_API_KEY},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        raise RuntimeError(
            f"IVG bolt unavailable at {_IVG_BASE}. "
            "Start with: docker compose --profile ivg up -d"
        )


def _bolt_post(path: str, payload: dict) -> dict:
    import httpx
    try:
        resp = httpx.post(
            f"{_IVG_BASE}{path}",
            json=payload,
            headers={"X-API-Key": _IVG_API_KEY},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        raise RuntimeError(
            f"IVG bolt unavailable at {_IVG_BASE}. "
            "Start with: docker compose --profile ivg up -d"
        )


def _cypher(query: str, params: dict | None = None) -> list[dict]:
    """Run a Cypher query via bolt API; return list of row dicts."""
    payload: dict[str, Any] = {"query": query}
    if params:
        payload["parameters"] = params
    result = _bolt_post("/api/cypher", payload)
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    return [dict(zip(columns, r)) for r in rows]


# ---------------------------------------------------------------------------
# YAML frontmatter helpers (stdlib only — no PyYAML dependency)
# ---------------------------------------------------------------------------

_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_after_fm). Simple key: value parser."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    body = text[m.end():]
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, body


def _render_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _read_note(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, ""
    text = path.read_text(encoding="utf-8")
    return _parse_frontmatter(text)


def _write_note(path: Path, fm: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_frontmatter(fm) + body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Export: IVG → Obsidian
# ---------------------------------------------------------------------------

def _export_concepts() -> list[str]:
    rows = _cypher(
        "MATCH (c:SDoHConcept) "
        "RETURN c.id AS id, c.name AS name, c.domain AS domain, c.aliases AS aliases"
    )
    written = []
    for row in rows:
        cid = row.get("id", "")
        path = CONCEPTS_DIR / f"{cid}.md"
        existing_fm, _ = _read_note(path)

        fm = {
            "id": cid,
            "type": "SDoHConcept",
            "name": row.get("name", cid),
            "domain": row.get("domain", ""),
            "aliases": row.get("aliases") or "",
        }
        # Preserve any human additions in existing frontmatter
        for k, v in existing_fm.items():
            if k not in fm:
                fm[k] = v

        body = f"\n## {row.get('name', cid)}\n\n"
        body += f"**Domain:** {row.get('domain', '')}\n\n"
        aliases = row.get("aliases") or []
        if aliases:
            body += "**Also known as:** " + ", ".join(aliases) + "\n\n"
        body += "## Related Decisions\n\n"
        body += f"See [[Decisions/decision_{cid}_*]] for governing protocol decisions.\n\n"
        body += "## Notes\n\n"

        _write_note(path, fm, body)
        written.append(str(path))
    return written


def _export_decisions() -> list[str]:
    rows = _cypher(
        "MATCH (d:SDoHDecision)-[:GOVERNS]->(c:SDoHConcept) "
        "RETURN d.id AS id, d.concept AS concept, d.domain AS domain, "
        "       d.rule AS rule, d.source AS source, d.rationale AS rationale, "
        "       d.effective_date AS effective_date, c.name AS concept_name"
    )
    written = []
    for row in rows:
        did = row.get("id", "")
        path = DECISIONS_DIR / f"{did}.md"
        existing_fm, _ = _read_note(path)

        fm = {
            "id": did,
            "type": "SDoHDecision",
            "concept": row.get("concept", ""),
            "domain": row.get("domain", ""),
            "source": row.get("source", ""),
            "effective_date": row.get("effective_date", ""),
        }
        for k, v in existing_fm.items():
            if k not in fm:
                fm[k] = v

        concept_name = row.get("concept_name") or row.get("concept", "")
        body = f"\n## {row.get('source', did)}\n\n"
        body += f"**Concept:** [[Concepts/{row.get('concept', '')}|{concept_name}]]\n\n"
        body += f"**Effective:** {row.get('effective_date', '')}\n\n"
        body += "### Rule\n\n"
        body += f"{row.get('rule', '')}\n\n"
        body += "### Rationale\n\n"
        body += f"{row.get('rationale', '')}\n\n"

        _write_note(path, fm, body)
        written.append(str(path))
    return written


def _export_contradictions() -> list[str]:
    rows = _cypher(
        "MATCH (ct:Contradiction)-[:CONFLICTS_WITH]->(c:SDoHConcept) "
        "RETURN ct.id AS id, ct.concept AS concept, "
        "       ct.statement_a AS statement_a, ct.source_a AS source_a, "
        "       ct.statement_b AS statement_b, ct.source_b AS source_b, "
        "       ct.status AS status, ct.owner AS owner, "
        "       c.name AS concept_name"
    )
    written = []
    for row in rows:
        ctid = row.get("id", "")
        path = CONTRADICTIONS_DIR / f"{ctid}.md"
        existing_fm, existing_body = _read_note(path)

        graph_status = row.get("status", "UNRESOLVED")

        fm: dict = {
            "id": ctid,
            "type": "Contradiction",
            "concept": row.get("concept", ""),
            "status": graph_status,
            "owner": row.get("owner", ""),
            # Human-editable fields — preserve existing values if set
            "resolved_by": existing_fm.get("resolved_by", ""),
            "resolution_rationale": existing_fm.get("resolution_rationale", ""),
        }

        # If human already changed status, keep their value (import handles the write-back)
        if existing_fm.get("status") and existing_fm["status"] != graph_status:
            fm["status"] = existing_fm["status"]
            fm["resolved_by"] = existing_fm.get("resolved_by", "")
            fm["resolution_rationale"] = existing_fm.get("resolution_rationale", "")

        # Preserve any other human additions
        for k, v in existing_fm.items():
            if k not in fm:
                fm[k] = v

        concept_name = row.get("concept_name") or row.get("concept", "")
        body = f"\n## {ctid}\n\n"
        body += f"**Concept:** [[Concepts/{row.get('concept', '')}|{concept_name}]]\n\n"
        body += f"**Owner:** {row.get('owner', '')}\n\n"
        body += "## Conflicting Statements\n\n"
        body += f"**A:** {row.get('statement_a', '')}\n"
        body += f"*Source: {row.get('source_a', '')}*\n\n"
        body += f"**B:** {row.get('statement_b', '')}\n"
        body += f"*Source: {row.get('source_b', '')}*\n\n"
        body += "## Resolution\n\n"
        if fm.get("resolved_by"):
            body += f"Resolved by decision: [[Decisions/{fm['resolved_by']}]]\n\n"
            if fm.get("resolution_rationale"):
                body += f"**Rationale:** {fm['resolution_rationale']}\n\n"
        else:
            body += (
                "_Fill in `resolved_by` (decision ID) and `resolution_rationale` "
                "in the frontmatter above, then change `status` to `RESOLVED`._\n\n"
            )
        body += "## Notes\n\n"

        _write_note(path, fm, body)
        written.append(str(path))
    return written


def export_to_obsidian() -> dict:
    """Export all IVG knowledge nodes to Obsidian vault. Returns summary dict."""
    if not VAULT_PATH.exists():
        return {"error": f"Vault not found at {VAULT_PATH}"}
    concepts = _export_concepts()
    decisions = _export_decisions()
    contradictions = _export_contradictions()
    return {
        "status": "ok",
        "concepts": len(concepts),
        "decisions": len(decisions),
        "contradictions": len(contradictions),
        "vault_root": str(KG_ROOT),
    }


# ---------------------------------------------------------------------------
# Import: Obsidian → IVG
# ---------------------------------------------------------------------------

def _import_contradictions(dry_run: bool = True) -> list[dict]:
    """
    Scan Contradiction notes for human edits. For each note where:
      - status changed to RESOLVED or DEFERRED
      - resolved_by or resolution_rationale filled in
    write the change back to IVG (unless dry_run).
    """
    if not CONTRADICTIONS_DIR.exists():
        return []

    # Fetch current graph state for comparison
    graph_rows = _cypher(
        "MATCH (ct:Contradiction) "
        "RETURN ct.id AS id, ct.status AS status, "
        "       ct.resolved_by AS resolved_by, ct.resolution_rationale AS resolution_rationale"
    )
    graph_state = {r["id"]: r for r in graph_rows}

    changes = []
    for note_path in CONTRADICTIONS_DIR.glob("*.md"):
        fm, _ = _read_note(note_path)
        ctid = fm.get("id")
        if not ctid:
            continue

        note_status = fm.get("status", "UNRESOLVED")
        note_resolved_by = fm.get("resolved_by", "").strip()
        note_rationale = fm.get("resolution_rationale", "").strip()

        graph = graph_state.get(ctid, {})
        graph_status = graph.get("status", "UNRESOLVED")
        graph_resolved_by = (graph.get("resolved_by") or "").strip()
        graph_rationale = (graph.get("resolution_rationale") or "").strip()

        status_changed = note_status != graph_status
        resolved_by_changed = note_resolved_by and note_resolved_by != graph_resolved_by
        rationale_changed = note_rationale and note_rationale != graph_rationale

        if not (status_changed or resolved_by_changed or rationale_changed):
            continue

        # Validate status transition
        if status_changed and (graph_status, note_status) not in _ALLOWED_TRANSITIONS:
            changes.append({
                "id": ctid,
                "action": "REJECTED",
                "reason": f"Invalid transition {graph_status} → {note_status}",
            })
            continue

        change = {
            "id": ctid,
            "action": "UPDATE",
            "status": note_status if status_changed else graph_status,
            "resolved_by": note_resolved_by or graph_resolved_by,
            "resolution_rationale": note_rationale or graph_rationale,
            "dry_run": dry_run,
        }

        if not dry_run:
            try:
                _cypher(
                    "MATCH (ct:Contradiction {id: $id}) "
                    "SET ct.status = $status, "
                    "    ct.resolved_by = $resolved_by, "
                    "    ct.resolution_rationale = $resolution_rationale",
                    {
                        "id": ctid,
                        "status": change["status"],
                        "resolved_by": change["resolved_by"],
                        "resolution_rationale": change["resolution_rationale"],
                    },
                )
                change["written"] = True
            except Exception as exc:
                change["error"] = str(exc)
                change["written"] = False

        changes.append(change)

    return changes


def import_from_obsidian(dry_run: bool = True) -> dict:
    """
    Scan vault for human edits and write changes back to IVG.
    dry_run=True (default) reports what would change without writing.
    """
    if not VAULT_PATH.exists():
        return {"error": f"Vault not found at {VAULT_PATH}"}

    contradiction_changes = _import_contradictions(dry_run=dry_run)

    applied = [c for c in contradiction_changes if c.get("action") == "UPDATE" and not dry_run]
    rejected = [c for c in contradiction_changes if c.get("action") == "REJECTED"]
    pending = [c for c in contradiction_changes if dry_run and c.get("action") == "UPDATE"]

    return {
        "status": "ok",
        "dry_run": dry_run,
        "contradiction_changes": contradiction_changes,
        "summary": {
            "applied": len(applied),
            "rejected": len(rejected),
            "pending_dry_run": len(pending),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="IVG ↔ Obsidian knowledge layer sync")
    parser.add_argument("direction", choices=["export", "import"], help="Sync direction")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="For import: commit changes to IVG (default is dry-run)",
    )
    args = parser.parse_args()

    if args.direction == "export":
        print("Exporting IVG knowledge layer → Obsidian vault...", flush=True)
        result = export_to_obsidian()
        if "error" in result:
            print(f"ERROR: {result['error']}", file=sys.stderr)
            sys.exit(1)
        print(
            f"  Concepts:       {result['concepts']}\n"
            f"  Decisions:      {result['decisions']}\n"
            f"  Contradictions: {result['contradictions']}\n"
            f"  Vault root:     {result['vault_root']}"
        )

    else:
        dry_run = not args.apply
        mode = "DRY RUN" if dry_run else "APPLYING"
        print(f"Importing Obsidian → IVG ({mode})...", flush=True)
        result = import_from_obsidian(dry_run=dry_run)
        if "error" in result:
            print(f"ERROR: {result['error']}", file=sys.stderr)
            sys.exit(1)

        summary = result["summary"]
        if dry_run:
            pending = summary["pending_dry_run"]
            rejected = summary["rejected"]
            print(f"  Changes detected: {pending}")
            print(f"  Rejected (invalid transitions): {rejected}")
            if pending:
                print("\n  Would apply:")
                for c in result["contradiction_changes"]:
                    if c.get("action") == "UPDATE":
                        print(f"    {c['id']}: status → {c['status']}")
                        if c.get("resolved_by"):
                            print(f"      resolved_by: {c['resolved_by']}")
                print("\n  Re-run with --apply to commit.")
        else:
            print(f"  Applied: {summary['applied']}")
            print(f"  Rejected: {summary['rejected']}")
            for c in result["contradiction_changes"]:
                if c.get("error"):
                    print(f"  ERROR {c['id']}: {c['error']}", file=sys.stderr)


if __name__ == "__main__":
    main()
