# 大文档高效处理方法论（AI 长文本处理指南）

> 一句话核心：**不要优化「AI 怎么读完大文本」，而要设计出让 AI 根本不需要读完大文本的架构。**
>
> `Parse once → Index once → Retrieve many → Read only what is needed → Extract once → Reuse structured results`

适用场景：上百页论文、几十万字说明书、百万字数据库、多篇论文语料库的反复提问。目标：**省 token、省钱、更稳定**。

---

## 一、核心原则：先导航，后阅读

不要在开始时让 AI 读全文。第一步只建立一个极小的"文档地图"：

```
Paper_001
  Title
  Abstract
  Section 1 Introduction
  Section 2 Materials
  Section 3 Results
    3.1 HPLC analysis
    3.2 Compound identification
    3.3 Biological activity
  Table 1 Chemical constituents
  Table 2 MS/MS data
  Figure 3 TIC chromatogram
  Supplementary Table S1 / S2
```

然后让 AI 判断"答案可能在哪几节"，**只读取候选区域**。

- ❌ 传统做法：读全文 → 找答案
- ✅ 正确做法：看目录/标题/图表题注 → 定位 → 精读

---

## 二、方法对比一览

| 方法 | 核心思想 | 适合场景 | 推荐度 |
|---|---|---|---|
| RAG 检索 | 文本切块后做向量索引，只取相关段落 | 大量论文、数据库、说明书 | ★★★★★ |
| 分层摘要 | 章节→小结→总摘要，先读摘要再下钻 | 单篇超长论文/报告 | ★★★★★ |
| 目录/索引导航 | AI 先看目录、标题、关键词，不看正文 | 结构清晰的大文本 | ★★★★★ |
| Agent 分阶段读取 | 第一步定位，第二步精读，第三步抽取 | 科研资料整理 | ★★★★★ |
| KV Cache / Prompt Cache | 重复前缀不用重新计算 | API 长上下文反复提问 | ★★★★ |
| 数据库存储 | 把已抽取信息结构化保存 | 化合物数据库这类任务 | ★★★★★ |

---

## 三、推荐主路线：混合 RAG

纯向量检索对科研文本不够好（`m/z 301.0354`、`C14H6O8`、`Compound 37` 这类精确词向量化效果差）。用 **BM25 关键词 + 向量语义 + Reranker**：

```
用户问题
   ↓
Query expansion
   ↓
┌─────────────┬──────────────┐
│ BM25        │ Vector       │
│ 精确关键词   │ 语义相似      │
└─────────────┴──────────────┘
          ↓
       Merge
          ↓
      Reranker
          ↓
      Top 5 chunks
          ↓
         LLM
```

向量库可选：FAISS / Chroma / Milvus / Qdrant / pgvector。

---

## 四、分块原则：按语义结构切，不按字数切

不要每 500 token 机械切一刀——会切断表格、化合物描述、MS/MS 数据。按文档结构切：

```
Document → Section → Subsection → Paragraph → Table → Table row
```

每个 chunk 带 metadata，便于回溯原文：

```json
{
  "paper_id": "REF001",
  "section": "3.2",
  "page": 8,
  "table": "Table 1",
  "compound": "Ellagic acid"
}
```

---

## 五、最重要的一步：读过一次以后不要再读

AI 已确认的信息写入结构化数据库，后续优先查库，只有缺字段/冲突/证据不足时才回原文：

```
原始论文
   ↓
第一次解析
   ↓
结构化数据库（Compound Master）
   ↓
后续任务优先查数据库
   ↓
仅当缺字段/冲突/证据不足 → 回原文检索
```

这就是"第一遍贵，之后便宜"。

---

## 六、层级摘要（Hierarchical Retrieval）

单篇超长文档做树状摘要：

```
Document
├── Chapter 1
│   ├── Section 1.1 summary
│   ├── Section 1.2 summary
│   └── Chapter summary
├── Chapter 2 ...
└── Global summary
```

提问时逐层下钻：Global summary → 相关 Chapter → 相关 Section → 原文段落。适合几十万到几百万字文本。

---

## 七、给 Agent 设"阅读预算"

不要把"读完全文再回答"交给模型。显式约束：

```
最大初始读取预算：3000 tokens
Stage 1: 仅获取目录、标题、章节结构、表格标题、关键词
Stage 2: 根据问题定位最多 5 个候选区域
Stage 3: 仅读取候选区域
Stage 4: 证据不足时可扩展，每次最多增加 2 个相邻 chunk
Stage 5: 证据足够立即停止
```

让 AI 从 Reader 变成 Retriever + Reader（渐进式信息开放 Progressive Disclosure）。

---

## 八、面向科研数据库的三层架构

以「地榆化合物数据库」为例：

### Layer 1: Raw Evidence
保存 `Paper ID / Page / Section / Table / Raw text`

### Layer 2: Retrieval Index
建立 `BM25 index / Vector index / Compound-name index / Formula index / m/z index`

### Layer 3: Compound Master
只留核心字段：`Molecule name / Molecular Formula / Monoisotopic mass (Da) / Database ID`

查询流程：

```
Compound Master
  ├─ 已有 → 直接返回
  └─ 没有/存疑
        ↓
    Retrieval Index
        ↓
    相关原文
        ↓
    AI 验证
```

---

## 九、Document Retrieval MCP（工具层强制省上下文）

在 Claude / MCP 场景下，做一个文档检索 MCP，暴露这些工具，让 AI 永远不直接拥有整个 PDF：

```text
index_document(file)
search_document(query, top_k=5)
read_chunk(chunk_id)
read_neighbors(chunk_id, before=1, after=1)
search_table(keyword)
get_document_outline(document_id)
```

AI 只能：`search_document → 拿 chunk_id → read_chunk → 证据不足 → read_neighbors`。这是在工具层强制 AI 不浪费上下文，比单纯写 prompt 更可靠。

---

## 十、落地路线总结

对科研资料整理场景，最终选择：

> **MCP + 混合 RAG（BM25+Vector）+ 分层文档索引 + 结构化数据库 + 按需回溯原文**

不依赖单纯加大上下文窗口。

---

*本文档由 2026-08-22 科研对话整理，服务于地榆化合物数据库等大文档科研任务。*
