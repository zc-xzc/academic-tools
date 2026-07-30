---
name: nature-paper2ppt
description: Build a complete but efficient Nature-style Chinese PPTX presentation from a scientific paper, preprint, PDF, article text, abstract, figure legends, or reading notes. Use this skill whenever the user asks to make slides/PPT/PPTX for journal club, group meeting, paper sharing, thesis seminar, lab meeting, department report, or academic presentation from a research paper, not only medical papers. It identifies the paper type and argument, selects only the figures needed for the story, writes Chinese slide content and speaker notes, creates the actual .pptx deck, and performs lightweight verification with cross-platform Python tooling by default.
---

# Purpose

Transform a scientific paper or paper-derived notes into a complete Chinese, figure-integrated PPTX presentation package with a Nature-style reporting logic.

The skill must not stop at an outline or script. The expected end product is a real `.pptx` deck.

Use this skill for papers across scientific fields, including:
- life sciences and medicine
- chemistry and materials science
- environmental and earth sciences
- physics and engineering
- computational biology, AI, and methods papers
- interdisciplinary Nature-family style research
- reviews, perspectives, resources, datasets, and benchmark papers

# Core Principle

Use the paper's scientific argument as the presentation spine.

The default slide logic should help the audience answer, in order:
1. Why does this problem matter?
2. What gap or bottleneck does the paper address?
3. What did the authors do?
4. What is the key evidence?
5. Why should we trust the result?
6. What is new, reusable, or broadly meaningful?
7. Where are the boundaries and open questions?

# Lean Operating Mode

Default to the lowest-overhead workflow that still produces a usable PPTX.

Do:
- read only the source material needed to understand the paper's argument
- extract only figures/tables that will actually appear in the deck
- create the PPTX as the primary deliverable
- run lightweight structural checks on the PPTX package
- write a short QA report

Avoid by default:
- exhaustive extraction of every figure, page, image, table, or supplement
- full OCR unless normal text extraction fails or the PDF is scanned
- saving full raw extracted paper text unless needed for debugging
- installing new dependencies when an existing tool can complete the task
- launching GUI apps or desktop automation just to render previews

## Toolchain Policy

Use a cross-platform Python-first stack:
- PyMuPDF for metadata, text extraction, page rendering, and page-level crops
- Pillow for figure crops, contact sheets, and lightweight preview images
- python-pptx for slide authoring and PPTX-safe editing
- zipfile plus a reopen pass through python-pptx for package validation

# Accepted Inputs

The skill may receive:
- a full paper PDF
- supplementary figures or tables
- Word or markdown converted paper text
- abstract + results + figure legends
- structured reading notes
- manually pasted article content

Default output language is simplified Chinese.

# Default Fast Path

For a normal selectable-text paper PDF:
1. Extract metadata, abstract, headings, figure legends, and table captions with PyMuPDF
2. Identify the paper type, argument, and candidate figures
3. Render low-resolution contact sheets when figure locations are unclear
4. Render high-resolution images only for selected figure/table pages
5. Build the PPTX directly with python-pptx
6. Verify by reopening the PPTX and inspecting package structure

# Workflow

## Step 1. Read and extract source material

Extract, when available: title, authors, journal, year, DOI, field, paper type, central problem, main claim, study design, key methods, main results, key figures, validation approaches, limitations, broader meaning.

## Step 2. Classify the paper

Identify the primary paper type:
- discovery / mechanism paper
- translational or applied science paper
- clinical or population study
- methods / algorithm / tool paper
- resource / dataset / atlas paper
- omics, single-cell, spatial, or multi-modal study
- materials / chemistry / engineering performance study
- review / perspective / commentary

Then choose the best presentation logic:
- `claim-first`: one strong central claim
- `question-to-evidence`: mechanism and discovery papers
- `problem-to-solution`: methods, tools, and engineering papers
- `workflow-to-validation`: datasets, atlases, omics, and benchmarks
- `evidence-map`: reviews and perspectives

## Step 3. Build the Chinese presentation plan

Default: 12-16 slides for a 15-20 minute report.

Default structure:
1. 标题页
2. 研究背景：为什么这个问题重要
3. 知识缺口 / 技术瓶颈
4. 论文核心问题与主张
5. 研究设计 / 技术路线 / 分析框架
6-8. 关键证据（3 slides）
9. 验证、对照或稳健性证据
10. 机制模型 / 方法优势 / 综合框架
11. 创新点与可复用价值
12. 局限性与未解决问题
13. 总结与讨论

## Step 4. Select figures as evidence

Prioritize figures that carry the paper's argument:
1. design/workflow
2. main evidence
3. validation or robustness
4. mechanism/model/synthesis
5. practical or conceptual implication

## Step 5. Build the PPTX deck

Create a real `.pptx` file using `python-pptx`:
- 16:9 widescreen layout
- selected original figures
- Chinese titles, bullets, captions, and speaker notes
- source labels for figure slides
- consistent typography and spacing

## Step 6. Verify

Reopen the PPTX and check:
- slide count
- embedded media count
- speaker notes presence
- obvious shape bounds

Write `qa_report.md` documenting known limitations.

# Style Rules

Use a restrained Nature-style academic presentation design:
- clean white or very light background
- dark readable text
- one or two muted accent colors
- figure-first result slides
- concise captions
- no decorative stock images

Use conclusion-style titles whenever possible.

# Paper-Type Guidance

## Discovery / mechanism papers
Use a question-to-evidence arc.

## Methods, AI, tool papers
Use a problem-to-solution arc.

## Resource, dataset, benchmark papers
Use a workflow-to-validation arc.

## Clinical, population studies
Use a design-to-inference arc.

## Reviews and perspectives
Use an evidence-map arc.
