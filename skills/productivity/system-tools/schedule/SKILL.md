---
name: "schedule"
description: "Create or update a scheduled task that runs automatically. Use when the user says things like \"every day\", \"each morning\", \"remind me in an hour\", \"run this at noon\", or wants to reschedule an existing task."
---

# Schedule — 定时任务管理

创建或修改自动运行的定时任务。适用于"每天早上"、"每小时"、"一小时后提醒我"等场景。

## 更新已有任务

如果要修改、暂停/恢复或重新调度已有任务，使用 `update_scheduled_task`。先用 `list_scheduled_tasks` 查找 taskId。

## 创建新任务

### 1. 分析会话

提取用户想要定时执行的核心任务，提炼为可重复的目标。

### 2. 编写 Prompt

未来的自动运行不会访问当前对话，Prompt 必须完全自包含：
- 清晰的目标描述
- 具体执行步骤
- 相关文件路径、URL、工具名
- 预期输出或验收标准
- 用户表达的偏好或约束

### 3. 确定调度方式

- **cronExpression**：周期性任务。在用户本地时区计算。
  - `0 9 * * *` — 每天 9:00
  - `0 9 * * 1-5` — 工作日 9:00
  - `30 8 * * 1` — 每周一 8:30
- **fireAt**：一次性任务。ISO 8601 时间戳含时区偏移。
- **两者均省略**：手动触发（ad-hoc）
