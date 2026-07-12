"""
P5 - Citation Graph using NetworkX
====================================
Why NetworkX over Neo4j:
  101 documents = small graph
  NetworkX in-memory, zero infrastructure
  Neo4j needs server setup, Docker container
  For 101 nodes NetworkX is 10x simpler

Graph structure:
  Nodes: each document (doc_id)
  Edge types:
    CITES: judgment cites an act
    ANALYZES: pov analyzes a judgment or act
    IMPLEMENTS: tax doc implements an act
    REFERENCES: any doc references another

Use: Query expansion
  User asks about sec162
  -> Graph finds: Welch v Helvering, Tellier, Flowers (all cite sec162)
  -> Retrieved chunks expanded to include those cases too
"""

import os
import json
import re
import pickle
import networkx as nx
from pathlib import Path

GRAPH_FILE = "data/processed/citation_graph.pkl"
RAW_DIR    = Path("data/raw")

# ─── KNOWN CITATION RELATIONSHIPS ────────────────────────
# Manually defined based on legal knowledge
# judgment -> act it primarily interprets

JUDGMENT_TO_ACT = {
    "judgment_01_commissioner_v_glenshaw_glass":              "act_sec61",
    "judgment_02_old_colony_trust_co_v_commissioner":         "act_sec61",
    "judgment_03_cesarini_v_united_states":                   "act_sec61",
    "judgment_04_welch_v_helvering":                          "act_sec162",
    "judgment_05_commissioner_v_tellier":                     "act_sec162",
    "judgment_06_indopco_v_commissioner":                     "act_sec162",
    "judgment_07_bob_jones_university_v_united_states":       "act_sec501",
    "judgment_08_gregory_v_helvering":                        "act_sec368",
    "judgment_09_cottage_savings_association_v_commissioner":  "act_sec1001",
    "judgment_10_starker_v_united_states":                    "act_sec1031",
    "judgment_11_cheek_v_united_states":                      "act_sec7201",
    "judgment_12_united_states_v_kirby_lumber":               "act_sec61",
    "judgment_13_faridessultaneh_v_commissioner":             "act_sec102",
    "judgment_14_commissioner_v_duberstein":                  "act_sec102",
    "judgment_15_crane_v_commissioner":                       "act_sec1001",
    "judgment_16_commissioner_v_tufts":                       "act_sec1001",
    "judgment_17_arrowsmith_v_commissioner":                  "act_sec1221",
    "judgment_18_corn_products_refining_v_commissioner":      "act_sec1221",
    "judgment_19_arkansas_best_corporation_v_commissioner":   "act_sec1221",
    "judgment_20_grodt_mckay_realty_v_commissioner":          "act_sec1031",
    "judgment_21_estate_of_franklin_v_commissioner":          "act_sec167",
    "judgment_22_united_states_v_gilmore":                    "act_sec165",
    "judgment_23_commissioner_v_flowers":                     "act_sec162",
    "judgment_24_hernandez_v_commissioner":                   "act_sec170",
    "judgment_25_benaglia_v_commissioner":                    "act_sec61",
    "judgment_26_moller_v_united_states":                     "act_sec183",
    "judgment_27_textron_inc_v_united_states":                "act_sec6662",
    "judgment_28_helvering_v_bruun":                          "act_sec61",
    "judgment_29_davis_v_united_states":                      "act_sec170",
    "judgment_30_commissioner_v_idaho_power":                 "act_sec263",
}

# POV documents and what acts they analyze
POV_TO_ACT = {
    "pov_crs_01_gross_income":     "act_sec61",
    "pov_crs_02_business_expense": "act_sec162",
    "pov_crs_03_charitable":       "act_sec170",
    "pov_crs_04_exempt_orgs":      "act_sec501",
    "pov_crs_05_like_kind":        "act_sec1031",
    "pov_crs_06_capital_gains":    "act_sec1221",
    "pov_crs_07_ira":              "act_sec408",
    "pov_crs_08_qbi":              "act_sec199A",
    "pov_crs_09_depreciation":     "act_sec167",
    "pov_crs_10_penalties":        "act_sec6662",
    "pov_crs_11_reorg":            "act_sec368",
    "pov_crs_12_hobby_loss":       "act_sec183",
}

POV_TO_JUDGMENT = {
    "pov_irs_01_sec162":           "judgment_04_welch_v_helvering",
    "pov_crs_02_business_expense": "judgment_04_welch_v_helvering",
    "pov_crs_03_charitable":       "judgment_24_hernandez_v_commissioner",
    "pov_crs_04_exempt_orgs":      "judgment_07_bob_jones_university_v_united_states",
    "pov_crs_05_like_kind":        "judgment_10_starker_v_united_states",
    "pov_crs_12_hobby_loss":       "judgment_26_moller_v_united_states",
}

TAX_TO_ACT = {
    "tax_pub17":   ["act_sec61",   "act_sec62",   "act_sec63"],
    "tax_pub334":  ["act_sec162",  "act_sec263"],
    "tax_pub463":  ["act_sec162"],
    "tax_pub526":  ["act_sec170"],
    "tax_pub535":  ["act_sec162",  "act_sec263"],
    "tax_pub544":  ["act_sec1001", "act_sec1221"],
    "tax_pub550":  ["act_sec1221"],
    "tax_pub590a": ["act_sec408"],
    "tax_pub946":  ["act_sec167"],
    "tax_pub15b":  ["act_sec132",  "act_sec61"],
}

# ─── AUTO-DETECT CITATIONS FROM TEXT ─────────────────────

def extract_irc_refs(text: str) -> list:
    """
    Extract IRC section references from text.
    Patterns: sec162, Section 162, IRC 162, 26 U.S.C. 162
    """
    patterns = [
        r'§\s*(\d+[A-Z]?)',
        r'[Ss]ection\s+(\d+[A-Z]?)',
        r'IRC\s+(?:§\s*)?(\d+[A-Z]?)',
        r'26\s+U\.?S\.?C\.?\s+(?:§\s*)?(\d+[A-Z]?)',
        r'I\.R\.C\.\s+§\s*(\d+[A-Z]?)',
    ]

    refs = set()
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            doc_id = f"act_sec{match}"
            refs.add(doc_id)

    return list(refs)

def extract_case_refs(text: str) -> list:
    """Extract case name references from text."""
    case_patterns = {
        "judgment_04_welch_v_helvering":                        [r"Welch v\.?\s*Helvering", r"Welch case"],
        "judgment_01_commissioner_v_glenshaw_glass":            [r"Glenshaw Glass", r"Glenshaw"],
        "judgment_07_bob_jones_university_v_united_states":     [r"Bob Jones", r"Bob Jones University"],
        "judgment_11_cheek_v_united_states":                    [r"Cheek v\.?\s*United States", r"Cheek"],
        "judgment_10_starker_v_united_states":                  [r"Starker"],
        "judgment_06_indopco_v_commissioner":                   [r"INDOPCO"],
        "judgment_08_gregory_v_helvering":                      [r"Gregory v\.?\s*Helvering"],
        "judgment_15_crane_v_commissioner":                     [r"Crane v\.?\s*Commissioner"],
        "judgment_19_arkansas_best_corporation_v_commissioner": [r"Arkansas Best"],
    }

    found = []
    for doc_id, patterns in case_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                found.append(doc_id)
                break

    return found

# ─── BUILD GRAPH ─────────────────────────────────────────

def build_citation_graph():
    """
    Build NetworkX directed graph of document relationships.

    Node attributes: doc_type, title, doc_id
    Edge attributes: relationship type, weight
    """
    G = nx.DiGraph()

    # Add all document nodes
    for f in sorted((RAW_DIR / "acts").glob("*.pdf")):
        G.add_node(f.stem, doc_type="act",      title=f.stem, filepath=str(f))

    for f in sorted((RAW_DIR / "judgments").glob("*.txt")):
        if not f.stem.startswith("judgment_"):
            continue  # skip non-judgment files (e.g. failed.txt, manifest.csv)
        G.add_node(f.stem, doc_type="judgment", title=f.stem, filepath=str(f))

    for f in sorted((RAW_DIR / "pov").glob("*.pdf")):
        G.add_node(f.stem, doc_type="pov",      title=f.stem, filepath=str(f))

    for f in sorted((RAW_DIR / "tax_docs").glob("*.pdf")):
        G.add_node(f.stem, doc_type="tax",      title=f.stem, filepath=str(f))

    print(f"Nodes added: {G.number_of_nodes()}")

    edges_added = 0

    # 1. Judgment CITES Act
    for judgment_id, act_id in JUDGMENT_TO_ACT.items():
        if judgment_id in G and act_id in G:
            G.add_edge(judgment_id, act_id, relationship="CITES", weight=1.0)
            edges_added += 1

    # 2. POV ANALYZES Act
    for pov_id, act_id in POV_TO_ACT.items():
        # match by prefix since filenames may have numbering
        pov_full = next((n for n in G.nodes if n.startswith(pov_id)), None)
        if pov_full and act_id in G:
            G.add_edge(pov_full, act_id, relationship="ANALYZES", weight=0.8)
            edges_added += 1

    # 3. POV REFERENCES Judgment
    for pov_id, judgment_id in POV_TO_JUDGMENT.items():
        pov_full = next((n for n in G.nodes if n.startswith(pov_id)), None)
        if pov_full and judgment_id in G:
            G.add_edge(pov_full, judgment_id, relationship="REFERENCES", weight=0.7)
            edges_added += 1

    # 4. Tax Doc IMPLEMENTS Act
    for tax_id, act_ids in TAX_TO_ACT.items():
        if tax_id in G:
            for act_id in act_ids:
                if act_id in G:
                    G.add_edge(tax_id, act_id, relationship="IMPLEMENTS", weight=0.6)
                    edges_added += 1

    # 5. Auto-detect IRC refs from judgment text
    print("Auto-detecting citations from judgment texts...")
    auto_cites  = 0
    auto_cases  = 0

    for filepath in sorted((RAW_DIR / "judgments").glob("*.txt")):
        doc_id = filepath.stem
        if doc_id not in G:   # skip failed.txt and any other non-judgment files
            continue
        try:
            text = filepath.read_text(encoding="utf-8", errors="ignore")[:5000]

            for ref in extract_irc_refs(text):
                if ref in G and ref != doc_id and not G.has_edge(doc_id, ref):
                    G.add_edge(doc_id, ref, relationship="CITES_AUTO", weight=0.5)
                    edges_added += 1
                    auto_cites += 1

            for ref in extract_case_refs(text):
                if ref in G and ref != doc_id and not G.has_edge(doc_id, ref):
                    G.add_edge(doc_id, ref, relationship="CITES_CASE", weight=0.4)
                    edges_added += 1
                    auto_cases += 1
        except Exception:
            pass

    print(f"  Auto IRC refs detected : {auto_cites}")
    print(f"  Auto case refs detected: {auto_cases}")
    print(f"Edges added: {edges_added}")
    return G

# ─── GRAPH QUERIES ───────────────────────────────────────

def get_related_docs(G, doc_id: str, max_hops: int = 2) -> list:
    """
    Get all documents related to a given doc within max_hops.
    Used for query expansion in retrieval.

    Example:
      get_related_docs(G, "act_sec162")
      -> returns all judgments that cite sec162
      -> returns all POV that analyze sec162
    """
    related = set()

    related.update(G.predecessors(doc_id))
    related.update(G.successors(doc_id))

    if max_hops >= 2:
        for node in list(related):
            related.update(G.predecessors(node))
            related.update(G.successors(node))

    related.discard(doc_id)
    return sorted(related)

def expand_query_with_graph(G, retrieved_doc_ids: list) -> list:
    """
    Given retrieved doc_ids, expand with graph neighbours (1 hop).
    Used after initial retrieval to add related documents.
    """
    expanded = set(retrieved_doc_ids)
    for doc_id in retrieved_doc_ids:
        if doc_id in G:
            expanded.update(get_related_docs(G, doc_id, max_hops=1))
    return sorted(expanded)

def get_graph_stats(G):
    """Print graph statistics."""
    print(f"\n{'='*50}")
    print("Citation Graph Statistics")
    print(f"{'='*50}")
    print(f"Total nodes : {G.number_of_nodes()}")
    print(f"Total edges : {G.number_of_edges()}")

    # Nodes by type
    type_counts = {}
    for node, data in G.nodes(data=True):
        t = data.get("doc_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    print("\nNodes by type:")
    for t, count in sorted(type_counts.items()):
        print(f"  {t:10}: {count}")

    # Edges by relationship
    edge_types = {}
    for u, v, data in G.edges(data=True):
        rel = data.get("relationship", "unknown")
        edge_types[rel] = edge_types.get(rel, 0) + 1

    print("\nEdges by type:")
    for rel, count in sorted(edge_types.items()):
        print(f"  {rel:20}: {count}")

    # Top 10 most connected nodes
    degrees = dict(G.degree())
    top_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:10]
    print("\nTop 10 most connected documents:")
    for node, degree in top_nodes:
        doc_type = G.nodes[node].get("doc_type", "?")
        in_deg   = G.in_degree(node)
        out_deg  = G.out_degree(node)
        print(f"  [{doc_type:8}] {node:50}  total={degree}  in={in_deg}  out={out_deg}")

def save_graph(G, filepath=GRAPH_FILE):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        pickle.dump(G, f)
    size_kb = os.path.getsize(filepath) / 1024
    print(f"\n[OK] Graph saved: {filepath}  ({size_kb:.1f} KB)")

def load_graph(filepath=GRAPH_FILE):
    with open(filepath, "rb") as f:
        return pickle.load(f)


if __name__ == "__main__":
    print("=" * 60)
    print("P5 - Citation Graph Builder")
    print("=" * 60)

    G = build_citation_graph()

    get_graph_stats(G)

    # Test 1: related docs for act_sec162
    print(f"\n{'='*50}")
    print("Test: Related docs for act_sec162 (1-hop)")
    print(f"{'='*50}")
    related = get_related_docs(G, "act_sec162", max_hops=1)
    for doc in related:
        doc_type = G.nodes[doc].get("doc_type", "?")
        rel = G.edges.get((doc, "act_sec162"), G.edges.get(("act_sec162", doc), {})).get("relationship", "?")
        print(f"  [{doc_type:8}] {doc}  ({rel})")

    # Test 2: related docs for welch v helvering
    print(f"\n{'='*50}")
    print("Test: Related docs for judgment_04_welch_v_helvering (1-hop)")
    print(f"{'='*50}")
    related2 = get_related_docs(G, "judgment_04_welch_v_helvering", max_hops=1)
    for doc in related2:
        doc_type = G.nodes[doc].get("doc_type", "?")
        jid      = "judgment_04_welch_v_helvering"
        rel = (G.edges.get((jid, doc)) or G.edges.get((doc, jid)) or {}).get("relationship", "?")
        print(f"  [{doc_type:8}] {doc}  ({rel})")

    # Test 3: query expansion demo
    print(f"\n{'='*50}")
    print("Test: Query expansion for ['act_sec162', 'act_sec1031']")
    print(f"{'='*50}")
    expanded = expand_query_with_graph(G, ["act_sec162", "act_sec1031"])
    print(f"  Input : 2 docs")
    print(f"  Output: {len(expanded)} docs after 1-hop expansion")
    for doc in expanded:
        print(f"    [{G.nodes[doc].get('doc_type','?'):8}] {doc}")

    save_graph(G)

    print("\n[OK] P5 Complete - Citation graph ready for query expansion!")
    print("Next: P6 - Golden Dataset Generation")
