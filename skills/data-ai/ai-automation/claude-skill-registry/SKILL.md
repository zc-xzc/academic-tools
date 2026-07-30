---
name: claude-skill-registry
description: Search and browse the community Claude Code skills registry (~158k skills). Use when the user wants to find existing Claude Code skills, discover community skill implementations, search for skills by keyword/category/author, or fetch a specific skill's source for reference or adaptation.
---

# Claude Skill Registry

Search the largest community registry of Claude Code skills aggregated from GitHub.

## Quick Start

Search for skills by keyword:

```bash
python scripts/search_registry.py "<query>" --limit 10
```

Fetch a specific skill's details:

```bash
python scripts/search_registry.py --fetch "<skill-name>"
```

## Search Workflow

### 1. Understand the User's Need

Determine what kind of skill they want: keyword, category, author, or a specific known skill name.

### 2. Run the Search

- **Broad keyword search**: `python scripts/search_registry.py "browser" --limit 15`
- **Filter by category**: add `--category development` (see `--list-categories` for options)
- **Quality filter**: add `--min-stars 100` to surface well-established skills
- **By author**: add `--author danielmiessler`
- **JSON output for parsing**: add `--json` to get machine-readable results

### 3. Inspect Results

Each result shows: name, description, stars, category, repo, author, and license. Present the most relevant matches to the user with a brief summary of what each skill does.

### 4. Fetch Details (If Needed)

When a skill looks promising, fetch its full details including the raw SKILL.md URL:

```bash
python scripts/search_registry.py --fetch "<skill-name>"
```

The output includes a `Raw SKILL.md` URL that can be fetched to read the full skill content.

### 5. Adapt for Codex

Claude Code SKILL.md files follow a different format from Codex skills. When adapting a found skill:
- Extract the core workflow/instructions from the SKILL.md body
- Translate Claude-specific patterns to Codex equivalents
- Do NOT copy the Claude skill verbatim -- adapt the procedural knowledge

## Available Filters

| Flag           | Description                          |
|----------------|--------------------------------------|
| `--limit N`    | Max results (default: 20)            |
| `--category C` | Filter by category                   |
| `--min-stars N`| Minimum GitHub stars                 |
| `--author A`   | Filter by author                     |
| `--tags T`     | Comma-separated tags                 |
| `--verbose`    | Show extra details (tags, source)    |
| `--json`       | Output as JSON for parsing           |

List available categories:
```bash
python scripts/search_registry.py --list-categories
```

## Important Notes

- The registry contains ~158k skills -- searches are fast but be specific with queries
- Skills marked `restricted` distribution have unknown licenses; verify upstream before reuse
- Skills marked `compatible` distribution are generally safe to reference
- Registry data is cached locally in `~/.codex/cache/claude-skill-registry/`
