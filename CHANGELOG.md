# Changelog

技能与仓库结构的变更记录，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。每次变更一个条目：日期 / 改了什么 / 为什么。

## [未发布]
- **新增大文档高效处理方法论指南**（`docs/large-document-processing-guide.md`）：沉淀面向超大文本（几十万~几百万字论文/说明书/数据库）的 AI 高效处理架构——先导航后阅读、混合 RAG（BM25+向量+Reranker）、语义分块、结构化沉淀（读一次后入库复用）、分层摘要、阅读预算、Document Retrieval MCP。
  - 为什么：避免每次把大文档全文喂给 AI 造成 token 浪费，建立"Parse once → Index once → Retrieve many → Read only what is needed → Extract once → Reuse structured results"的可复用方法论，服务于地榆化合物数据库等科研任务。

- **移除复盘机制**（删除 `reviews/` 目录、`docs/review-workflow.md`，更新 `README.md` 目录树与章节）：删除每日轻复盘与周汇总机制及配套文档。
  - 为什么：复盘内容为个人工作记录，含账号等内部信息，不宜保留在公开仓库；技能更新流程仍按既定 `main 拉分支 → 上传 → 提交 → PR` 执行，不受影响。
- **人际交往边界指南：移除版权归属中的个人信息**（`skills/productivity/relationships-and-communication/interpersonal-boundary-guide/README.md`）：将迁移说明中的版权归属改为中性表述。
  - 为什么：公开仓库零隐私红线，避免在 README 中保留个人姓名。
- **新增视觉模型配置指南**（`docs/mcp-vision-web-bridge-guide.md`）：如何在 Claude 中配置"识图 MCP 工具"（mcp-vision-web-bridge），通过剪贴板/上传图片调用 Qwen-VL 视觉大模型。
  - 为什么：沉淀视觉桥接工具在其他电脑上的复刻与配置步骤，含 .env 模板、Claude Desktop 配置、常见问题排查与可选模型端点。
- **新增视觉桥接完整复刻提示词**（`docs/mcp-vision-web-bridge-replica-prompt.md`）：让 Claude 在新电脑上从零生成 mcp-vision-web-bridge 项目的完整提示词。
  - 为什么：沉淀可复用的"完整复刻提示词"，覆盖项目结构、逐文件代码、验证命令与配置步骤，配合配置指南使用。
- **同步本地技能到云端**（8 个技能）：新增周末短途游规划技能 `skills/productivity/travel-planning/weekend-trip-planner/`；用本地完整新版覆盖 7 个旧版（`frontend-design`、`nature-paper2ppt`、`nature-academic-search`、`nature-citation`、`schedule`、`consolidate-memory`、`qinggan-loop-planner`）。
  - 为什么：本地技能缓存在 07-30 迁移后持续更新，本次将本地最新完整版同步到云端，补齐缺失的周末游技能，保持仓库与本地一致。
- **毕业论文AI辅助写作提示词库技能扩展**（`skills/academic/academic-research/thesis-writing-ai-prompts/`）：新增"第十三章 论文审阅实战方法论"。
  - 为什么：沉淀审阅专业硕士论文的实战方法论，覆盖参考文献逐条核验、数据严谨性验证（占比自洽/公开数据核对/统计量可实现性/问卷重建）、评审清单产出格式与送审前硬性检查，使技能从"写作辅助"扩展为"写作+审阅"闭环。
  - 另：在"降 AI 率人设提示词"章节补充 AI 使用披露合规提示，提示遵守所在学校/期刊的 AI 使用披露政策，仅用于改善文风自然度。
- **消费维权方法论技能**（`skills/productivity/consumer-rights/ecommerce-consumer-rights/`）：精炼"已用部分按原价折算"表述并统一法律条款序号写法。
  - 为什么：与本地应用内技能对齐，补充"单方主张"定性，统一《产品质量法》条款序号写法。
- **毕业论文AI辅助写作提示词库技能**（`skills/academic/academic-research/thesis-writing-ai-prompts/`）：同步本地技能描述与简介，补齐"论文审阅实战方法论"与"AI使用披露合规提示"说明。
  - 为什么：使仓库 SKILL.md 的 frontmatter 描述与开头简介和本地应用内技能保持一致。


## 2026-08-22
### 更新
- **消费维权方法论技能扩展**（`skills/productivity/consumer-rights/ecommerce-consumer-rights/`）：新增"线下预付卡/次卡退费"场景（场景F），并将定位从电商购物扩展为线上线下消费维权。
  - 为什么：沉淀线下实体店办卡充值后的退费实战经验，覆盖已用部分"按原价折算"与"收手续费"的算账方法、拒绝话术、门店→公司→12315升级路径，以及微信文字留证纪律。
  - 法律依据经逐条核验：补充《消费者权益保护法》第53条（预收款）、《消费者权益保护法实施条例》第22条（国务院令第778号，2024年施行，预付式消费退款直接依据），并核实《单用途商业预付卡管理办法（试行）》适用范围为企业法人（个体户美发店不直接适用），"按原价折算已用部分"定性为"无购卡协议约定时的单方主张、格式条款需结合提示说明义务判断"，避免绝对化表述。

## 2026-08-20
### 变更
- **科研设备采购方法论技能扩展**（`skills/academic/scientific-research/research-equipment-procurement/`）：新增实战案例与应对方法。
  - 为什么：沉淀科研设备采购实战经验，覆盖多供应商竞价与同一供应商多方案并存场景下的比价、压价与成交锁单。
### 新增
- **毕业论文AI辅助写作提示词库技能**（`skills/academic/academic-research/thesis-writing-ai-prompts/`）：新增 SKILL.md 与 README.md。
  - 为什么：沉淀使用大模型辅助毕业论文/SCI/IEEE 论文写作的 50 个高阶提示词，覆盖选题、文献综述、研究方法、论文结构、内容撰写、学术润色、降 AI 率、数据分析、修改答辩与工具建议。

### 更新
- **毕业论文AI辅助写作提示词库技能扩展**（`skills/academic/academic-research/thesis-writing-ai-prompts/`）：新增"专业硕士学位论文通用写作规范"与"论文类型与审稿评审要点"两章。
  - 为什么：沉淀高校专业硕士论文写作规范的通用要求（前置部分、摘要、格式原则、参考文献、附录）与论文类型/审稿评审要点，使技能覆盖从写作到评审答辩的全流程。

## 2026-08-14

### 新增
- **复盘机制结构**：新增 `reviews/daily/`（每日轻复盘，含 `_TEMPLATE.md` 模板）、`reviews/weekly/`（每周汇总）、`docs/review-workflow.md`（流程文档）、根目录 `CHANGELOG.md`。
  - 为什么：让对话中沉淀的技能/知识可追溯地回写仓库，复盘仅作触发器，改动经用户确认后落盘。
- 首个每日复盘：`reviews/daily/2026-08-14.md`。

### 待确认（周汇总）
- `weekend-trip-planner` 技能新增到 `skills/productivity/travel-planning/`（当前仓库仅有 `qinggan-loop-planner`）。
