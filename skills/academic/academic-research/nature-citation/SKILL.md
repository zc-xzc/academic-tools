---
name: nature-citation
description: Add strict Nature/CNS citations to manuscript text by splitting long passages into citable segments, searching only accepted flagship and subjournal titles from Nature Portfolio, the AAAS Science family, and Cell Press, filtering by publication time range, and exporting one reference-manager-ready output by default.
---

# Nature Citation

Turn manuscript text into a defensible citation export: segmented text with citation candidates, a reference-manager import file (.enw/.ris/Zotero RDF), and conservative evidence notes.

## Chinese-user operating mode

- Accept text in Chinese, search using English concept queries
- Return segment notes and evidence notes in Chinese
- Flag overclaiming: 强支撑 / 部分支撑 / 背景支撑 / 不建议引用

## Default scope

- Nature系列: Nature Portfolio journals (Nature, Nature [field], Nature Comms, Comms [field], Sci Rep, npj)
- CNS: Cell, Nature, Science + major sister journals
- CNS及其子刊: Nature Portfolio + AAAS Science family + Cell Press
- 只要正刊: Nature, Science, Cell only

## Workflow

### 1. Segment the text

Split long text into citable segments at paragraph boundaries. Keep each segment focused on one citable idea.

### 2. Parse each segment

For each segment:
- Extract core claim
- Identify claim type: mechanism, association, method, clinical, background, definition
- Convert claim into 2-4 English search queries

### 3. Search candidate papers

Use structured search via MCP tools (PubMed, CrossRef) with journal filters.

### 4. Evaluate support

- strong support: directly tests the same relationship, result supports the segment
- partial support: supports part of the segment or a narrower condition
- background support: supports field context, not the specific claim
- contradictory/limiting: conflicts with or narrows the claim

### 5. Export reference-manager file

Default: `.enw` (EndNote). Also supports `.ris` and Zotero `.rdf`.

### 6. Report results

Return segmented text with citation candidates, support grade, and export file path.

## Search quality rules

- Prefer precision over volume (3-8 good candidates, not 50 loose matches)
- Check journal identity — many journals contain "nature" but are not Nature Portfolio
- Capture retractions, corrections when visible in metadata
- For medical/clinical claims, state that citations don't replace systematic review
