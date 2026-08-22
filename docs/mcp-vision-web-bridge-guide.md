# mcp-vision-web-bridge 完整复刻指南

> 目标：在其他电脑上复刻"识图 MCP 工具"，让该电脑的 Claude 也能通过剪贴板/上传图片调用 Qwen-VL 视觉大模型。
> 本指南以 Windows 为例，使用阿里云百炼的 OpenAI 兼容接口调用 Qwen-VL 视觉大模型。若你开通了阿里云百炼专属模型服务，请将 `MODEL_BASE_URL` 换成你自己的专属端点。

---

## 一、你需要准备的东西

| 物品 | 说明 |
|---|---|
| 本复刻包 | 文件夹 `mcp-vision-web-bridge-replica`（或 zip 压缩包） |
| 目标电脑 | Windows 10/11（macOS/Linux 也可，步骤略不同） |
| Node.js ≥ 20 | 到 https://nodejs.org 下载 LTS 版 |
| API Key | 你原电脑 `.env` 里的 `MODEL_API_KEY`（形如 `sk-ws-xxx`） |

> ⚠️ 本复刻包**不含** API Key，也不含 `node_modules`。两者都需要在目标电脑上重新配置/安装。

---

## 二、在目标电脑上安装（Windows 为例）

### 第 1 步：安装 Node.js

1. 到 https://nodejs.org 下载 **LTS 版本**（20 以上）
2. 双击安装，一路默认即可
3. 打开终端验证：

```bash
node -v    # 应显示 v20.x.x 或更高
npm -v     # 应显示 10.x.x 或更高
```

### 第 2 步：拷贝项目文件

将 `mcp-vision-web-bridge-replica` 整个文件夹拷贝到目标电脑，例如放到：

```
<你的项目绝对路径>
```

> 路径任意，但必须是**绝对路径**，且**不含中文和空格**最稳妥（避免 MCP 启动问题）。

### 第 3 步：安装依赖

```bash
cd <你的项目绝对路径>
npm install
```

> 会自动安装 `@modelcontextprotocol/sdk` 和 `zod` 两个依赖。

### 第 4 步：创建 `.env` 并填入 API Key

复制模板：

```bash
copy .env.aliyun.example .env
```

编辑 `.env`，把 `MODEL_API_KEY` 改成你原电脑上的真实 Key：

```
MODEL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL_API_KEY=sk-ws-你的真实Key
MODEL_NAME=qwen-vl-max

ALLOW_LOCAL_IMAGE_PATHS=true
ALLOW_CLIPBOARD_IMAGES=true
ALLOW_PRIVATE_NETWORK_URLS=false
USE_JINA_READER=false
MAX_IMAGE_BYTES=10485760
```

> 保存时用 **UTF-8 无 BOM** 编码（VS Code 默认即可，记事本另存时选 UTF-8）。

### 第 5 步：配置 Claude Desktop

找到配置文件 `claude_desktop_config.json`：

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- 或在 Claude Desktop → 设置 → Developer → Edit Config 打开

加入以下内容（**路径替换成你的实际路径**）：

```json
{
  "mcpServers": {
    "vision-web-bridge": {
      "command": "node",
      "args": [
        "--env-file-if-exists=<你的项目绝对路径>\\.env",
        "<你的项目绝对路径>\\src\\server.mjs"
      ]
    }
  }
}
```

> ⚠️ Windows 中反斜杠要写成 `\\`（JSON 转义）。若已有其他 MCP server，直接合并到 `mcpServers` 里即可，别覆盖其他配置。

### 第 6 步：重启并验证

1. 从系统托盘**完全退出** Claude Desktop，再重新打开
2. 设置 → Developer → Local MCP servers，确认 `vision-web-bridge` 出现且 Arguments 指向正确路径
3. 新建对话，粘贴一张图片，或在对话中直接 **Ctrl+V** 粘贴图片
4. 如果工具生效，模型会自动调用 `read_image_with_model`

---

## 三、独立验证（不依赖 Claude）

如果你要确认服务器本身能跑通，不启动 Claude 也能测试：

```bash
# 在项目目录下直接启动（会读取 .env）
node --env-file-if-exists=.env src/server.mjs
```

正常情况会保持运行不报错（stdio 模式等待 MCP 握手）。Ctrl+C 退出。

---

## 四、常见问题排查

| 现象 | 原因与解决 |
|---|---|
| MCP server 列表没有 vision-web-bridge | ① 配置文件编码不是 UTF-8 无 BOM ② 路径不对 ③ 没完全重启 Claude（要从托盘退出） |
| 工具报 401/403 | API Key 错误或已失效，检查 `.env` 的 `MODEL_API_KEY` |
| 报 404 | `MODEL_BASE_URL` 或 `MODEL_NAME` 拼写有误 |
| 报 413 | 图片超过 `MAX_IMAGE_BYTES`（默认 10MB） |
| 报 400 | 模型不支持该图片格式，或图片太小（<10px 会被拒） |
| 剪贴板读图失败 | 确认 `.env` 里 `ALLOW_CLIPBOARD_IMAGES=true`；Windows 依赖 PowerShell + Windows Forms，一般无需额外安装 |
| "No recent uploaded image found" | 上传目录探测失败，手动配置 `CLAUDE_UPLOAD_DIRS`（见 `.env.aliyun.example` 注释） |

---

## 五、其他模型端点（可选）

如果不走阿里云百炼，可换成任意 OpenAI 兼容的视觉模型：

| 服务商 | MODEL_BASE_URL | MODEL_NAME 示例 |
|---|---|---|
| 阿里云百炼（专属模型服务） | 你的专属端点（形如 `https://llm-xxx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`） | `qwen-vl-max` |
| 阿里云百炼（公网） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen2.5-vl-72b-instruct` |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `Qwen/Qwen3-VL-8B-Instruct` |

---

## 六、本复刻包包含的文件

```
mcp-vision-web-bridge-replica/
├── src/
│   ├── server.mjs          # MCP 服务器入口（注册工具/提示词）
│   ├── model-client.mjs    # 视觉/文本模型调用（OpenAI 兼容）
│   └── web-reader.mjs      # 网页链接抓取与正文提取
├── test/                   # 单元测试（node --test）
├── scripts/check-secrets.mjs  # 密钥泄露检查脚本
├── .github/workflows/ci.yml   # CI 配置
├── package.json            # 项目定义与依赖
├── package-lock.json
├── .env.example            # 通用环境变量模板
├── .env.aliyun.example     # 阿里云百炼专属环境变量模板（推荐）
├── README.md               # 官方英文说明
├── Windows环境说明.md       # 官方 Windows 中文说明
├── CHANGELOG.md
├── SECURITY_REVIEW.md
└── LICENSE                 # MIT
```
