#!/usr/bin/env python3
"""
Claude Skill Registry — search and fetch skills from the community registry.

Usage:
    python search_registry.py <query> [--limit N] [--category CAT] [--min-stars N]
    python search_registry.py --list-categories
    python search_registry.py --fetch <skill-name> [--repo REPO] [--branch BRANCH]

The registry data is fetched from:
    https://raw.githubusercontent.com/majiayu000/claude-skill-registry/main/
"""

import argparse
import gzip
import json
import os
import sys
import urllib.request
from pathlib import Path

REGISTRY_BASE = "https://raw.githubusercontent.com/majiayu000/claude-skill-registry/main"
CACHE_DIR = Path.home() / ".codex" / "cache" / "claude-skill-registry"
MANIFEST_URL = f"{REGISTRY_BASE}/registry-manifest.json"
SUMMARY_URL = f"{REGISTRY_BASE}/registry_summary.json"


def ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def fetch_json(url):
    """Fetch JSON from URL, with local caching."""
    cache_key = url.replace("/", "_").replace(":", "_")
    cache_path = CACHE_DIR / cache_key

    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Codex/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
    except Exception as e:
        print(f"[WARN] Could not fetch {url}: {e}", file=sys.stderr)
        return None


def fetch_gz_json(url):
    """Fetch gzipped JSON, decompress, and cache the raw JSON."""
    cache_key = url.replace("/", "_").replace(":", "_") + ".json"
    cache_path = CACHE_DIR / cache_key

    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Codex/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = gzip.decompress(resp.read())
            data = json.loads(raw.decode("utf-8"))
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
    except Exception as e:
        print(f"[WARN] Could not fetch {url}: {e}", file=sys.stderr)
        return None


def get_manifest():
    return fetch_json(MANIFEST_URL)


def list_categories():
    """List categories by scanning a subset of shards."""
    manifest = get_manifest()
    if not manifest:
        return {}
    cats = {}
    shard_ids = [s["id"] for s in manifest.get("shards", [])][:8]
    for sid in shard_ids[:32]:  # Scan subset of shards for speed
        shard_url = f"{REGISTRY_BASE}/registry-shards/{sid}.json.gz"
        shard = fetch_gz_json(shard_url)
        if not shard:
            shard_url = f"{REGISTRY_BASE}/registry-shards/{sid}.json"
            shard = fetch_json(shard_url)
        if not shard:
            continue
        for skill in shard.get("skills", []):
            cat = skill.get("category", "unknown")
            cats[cat] = cats.get(cat, 0) + 1
    return dict(sorted(cats.items(), key=lambda x: x[1], reverse=True))



def search(query, limit=20, category=None, min_stars=0, author=None, tags=None):
    """Search registry for skills matching the query."""
    manifest = get_manifest()
    if not manifest:
        print("[ERROR] Could not fetch registry manifest.", file=sys.stderr)
        return []

    query_lower = query.lower() if query else ""
    shard_ids = [s["id"] for s in manifest.get("shards", [])]
    results = []

    for sid in shard_ids[:32]:  # Scan subset of shards for speed
        shard_url = f"{REGISTRY_BASE}/registry-shards/{sid}.json.gz"
        shard = fetch_gz_json(shard_url)
        if not shard:
            shard_url = f"{REGISTRY_BASE}/registry-shards/{sid}.json"
            shard = fetch_json(shard_url)
        if not shard:
            continue

        for skill in shard.get("skills", []):
            name = skill.get("name", "")
            desc = skill.get("description", "")
            skill_cat = skill.get("category", "")
            skill_author = skill.get("author", "")
            skill_tags = skill.get("tags", [])
            stars = skill.get("stars", 0)

            # Filters
            if category and skill_cat.lower() != category.lower():
                continue
            if min_stars and stars < min_stars:
                continue
            if author and author.lower() not in skill_author.lower():
                continue
            if tags:
                skill_tag_lower = [t.lower() for t in skill_tags]
                if not any(t.lower() in skill_tag_lower for t in tags):
                    continue

            # Search
            if query_lower:
                if query_lower not in name.lower() and query_lower not in desc.lower():
                    continue

            results.append(skill)

        if len(results) >= limit * 4:  # Gather more then sort
            break

    # Sort by stars descending
    results.sort(key=lambda s: s.get("stars", 0), reverse=True)
    return results[:limit]


def fetch_skill(name, repo=None, branch=None):
    """Fetch the SKILL.md content for a specific skill."""
    manifest = get_manifest()
    if not manifest:
        return None

    shard_ids = [s["id"] for s in manifest.get("shards", [])]

    for sid in shard_ids:  # Fetch scans all shards
        shard_url = f"{REGISTRY_BASE}/registry-shards/{sid}.json.gz"
        shard = fetch_gz_json(shard_url)
        if not shard:
            shard_url = f"{REGISTRY_BASE}/registry-shards/{sid}.json"
            shard = fetch_json(shard_url)
        if not shard:
            continue

        for skill in shard.get("skills", []):
            if skill.get("name") == name:
                if repo and skill.get("repo") != repo:
                    continue
                if branch and skill.get("branch") != branch:
                    continue
                return skill

    return None


def format_results(results, verbose=False):
    """Pretty-print search results."""
    for i, skill in enumerate(results):
        stars = skill.get("stars", 0)
        name = skill.get("name", "?")
        desc = skill.get("description", "")[:120]
        repo = skill.get("repo", "?")
        author = skill.get("author", "?")
        category = skill.get("category", "?")
        license_name = skill.get("license", "?")
        distribution = skill.get("distribution", "?")

        print(f"{i+1}. **{name}**  [{stars} stars] [{category}]")
        print(f"   {desc}")
        print(f"   repo: {repo} | author: {author} | license: {license_name} | dist: {distribution}")
        if verbose:
            source_url = skill.get("source_url", "")
            tags = skill.get("tags", [])
            if tags:
                print(f"   tags: {', '.join(tags)}")
            if source_url:
                print(f"   source: {source_url}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Search the Claude Skill Registry")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--min-stars", type=int, default=0, help="Minimum GitHub stars")
    parser.add_argument("--author", help="Filter by author")
    parser.add_argument("--tags", help="Comma-separated tags to match")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show extra details")
    parser.add_argument("--list-categories", action="store_true", help="List available categories")
    parser.add_argument("--fetch", help="Fetch SKILL.md URL for a specific skill name")
    parser.add_argument("--repo", help="Filter fetch by repo")
    parser.add_argument("--branch", help="Filter fetch by branch")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    ensure_cache_dir()

    if args.list_categories:
        cats = list_categories()
        if not cats:
            print("[ERROR] Could not fetch category data.", file=sys.stderr)
            sys.exit(1)
        for cat, count in cats.items():
            print(f"  {cat}: {count} skills")
        return

    if args.fetch:
        skill = fetch_skill(args.fetch, args.repo, args.branch)
        if skill:
            if args.json:
                print(json.dumps(skill, indent=2, ensure_ascii=False))
            else:
                print(f"Name: {skill['name']}")
                print(f"Description: {skill.get('description', '')}")
                print(f"Repo: {skill.get('repo', '')}")
                print(f"Branch: {skill.get('branch', '')}")
                print(f"Path: {skill.get('path', '')}")
                print(f"Source URL: {skill.get('source_url', '')}")
                print(f"Stars: {skill.get('stars', 0)}")
                print(f"Category: {skill.get('category', '')}")
                print(f"Author: {skill.get('author', '')}")
                print(f"License: {skill.get('license', '')}")
                print(f"Tags: {', '.join(skill.get('tags', []))}")

                # Construct raw URL for SKILL.md
                source = skill.get("source_url", "")
                if source:
                    raw_url = source.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
                    print(f"Raw SKILL.md: {raw_url}")
        else:
            print(f"[NOT FOUND] Skill '{args.fetch}' not found in registry.", file=sys.stderr)
            sys.exit(1)
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    tags_list = args.tags.split(",") if args.tags else None
    results = search(
        args.query,
        limit=args.limit,
        category=args.category,
        min_stars=args.min_stars,
        author=args.author,
        tags=tags_list,
    )

    if not results:
        print(f"No skills found for query: {args.query}")
        return

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        format_results(results, verbose=args.verbose)


if __name__ == "__main__":
    main()
