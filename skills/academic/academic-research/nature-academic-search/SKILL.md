---
name: nature-academic-search
description: Multi-source literature search, citation verification, MeSH search strategy, citation file management (.nbib/.ris/.bib conversion), and reference management (BibTeX, related articles, ID conversion) via MCP tools (PubMed, CrossRef, arXiv). Use when the user needs coordinated multi-step literature workflows beyond a single MCP call.
---

# Academic Search

Multi-source literature search, citation verification, citation format conversion, and reference management via MCP tools.

## MCP Tools

### Core Search

| Tool | Source | Best For |
|------|--------|----------|
| pubmed_search_articles | PubMed MCP | Biomedical, MeSH, clinical trials |
| search_crossref | paper-search MCP | Cross-disciplinary, citation counts |
| search_arxiv | paper-search MCP | Preprints (physics, math, CS, biology) |

### Extended Search

| Tool | Source | Best For |
|------|--------|----------|
| search_google_scholar | paper-search MCP | Broad academic search |
| search_semantic_scholar | paper-search MCP | Citation graph, field-of-study filters |
| search_biorxiv | paper-search MCP | Biology preprints |
| search_medrxiv | paper-search MCP | Medical preprints |
| search_webofscience | paper-search MCP | Curated index, citation reports |
| search_scopus | paper-search MCP | Broad scholarly database |

### PubMed Utilities

| Tool | Purpose |
|------|---------|
| pubmed_fetch_articles | Full metadata by PMID |
| pubmed_find_related | Related article discovery |
| pubmed_format_citations | APA / MLA / BibTeX / RIS formatting |
| pubmed_convert_ids | DOI ↔ PMID ↔ PMCID conversion |
| pubmed_lookup_mesh | MeSH term exploration and hierarchy |

## Source Routing

| User need | Primary (T1) | Secondary (T2) | Last Resort (T3) |
|-----------|-------------|-----------------|-------------------|
| Medical / clinical | PubMed | Semantic Scholar | Google Scholar |
| Cross-disciplinary | CrossRef | Semantic Scholar | Scopus |
| Preprints / CS / physics | arXiv | bioRxiv / medRxiv | — |
| Exhaustive review | PubMed + CrossRef + arXiv | Semantic Scholar + bioRxiv/medRxiv | WoS / Scopus |
| Citation count sensitive | Semantic Scholar | CrossRef | — |

## Workflows

1. Multi-Source Literature Search — coordinated search across PubMed, CrossRef, arXiv
2. Citation Verification — verify claims against source papers
3. MeSH Search Strategy — build structured PubMed queries using MeSH hierarchy
4. Citation File Management — convert between .nbib/.ris/.bib formats
5. Reference Management — BibTeX, related articles, ID conversion

## Environment Setup

### API Keys (optional)

| Service | Env Var | Register At |
|---------|---------|-------------|
| Semantic Scholar | SEMANTIC_SCHOLAR_API_KEY | api.semanticscholar.org |
| NCBI E-utilities | NCBI_API_KEY | ncbi.nlm.nih.gov/account |

### Proxy (if needed)

```bash
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
```
