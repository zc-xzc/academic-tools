# mcp-vision-web-bridge 完整复刻提示词

你是资深 Node.js / MCP 开发助手。请在一台新电脑上，从零创建并验证一个名为 `mcp-vision-web-bridge` 的本地 MCP 服务。严格按本提示词生成全部文件，不要省略任何文件、不要添加额外运行时依赖、不要写入真实 API Key 或个人本机路径。

## 一、目标

- 一个基于 Node.js 20+ 的 stdio MCP 服务器，可接入 Claude Desktop / Claude Code / 其他 MCP 客户端。
- 提供两个工具：`read_image_with_model`（识图）和 `read_links_with_model`（读网页后总结）。
- 支持图片来源：最新 Claude 上传、公开图片 URL、base64、data URL、显式本地路径（需开关）、剪贴板（需开关）。
- 默认安全：本地路径、剪贴板、私网 URL、Jina Reader 均默认关闭；不记录密钥、图片、Prompt 或网页正文。

## 二、项目结构

```text
mcp-vision-web-bridge/
├── package.json
├── .env.example
├── .gitignore
├── README.md
├── CHANGELOG.md
├── SECURITY_REVIEW.md
├── LICENSE
├── Windows环境说明.md
├── claude_desktop_config_ready.json
├── vision.mjs
├── setup.ps1
├── setup.bat
├── src/
│   ├── server.mjs
│   ├── model-client.mjs
│   └── web-reader.mjs
├── scripts/
│   └── check-secrets.mjs
└── test/
    ├── model-client.test.mjs
    └── web-reader.test.mjs
```

## 三、逐文件创建（内容必须与代码块完全一致）

### package.json

````javascript
{
  "name": "mcp-vision-web-bridge",
  "version": "0.2.0",
  "type": "module",
  "description": "A local MCP server that adds image understanding and web-page reading through an OpenAI-compatible model API.",
  "files": [
    "src",
    "README.md",
    "CHANGELOG.md",
    "SECURITY_REVIEW.md",
    "LICENSE",
    ".env.example",
    "scripts"
  ],
  "bin": {
    "mcp-vision-web-bridge": "src/server.mjs"
  },
  "scripts": {
    "start": "node --env-file-if-exists=.env src/server.mjs",
    "test": "node --test",
    "check:secrets": "node scripts/check-secrets.mjs",
    "prepack": "npm test && npm run check:secrets"
  },
  "engines": {
    "node": ">=20"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.29.0",
    "zod": "^4.4.1"
  },
  "devDependencies": {}
}
````

### .env.example

````javascript
# mcp-vision-web-bridge configuration
# Copy this file to .env and fill in your own provider values.

# OpenAI-compatible endpoint. Must be a /v1 endpoint.
MODEL_BASE_URL=https://api.example.com/v1
MODEL_API_KEY=replace-with-your-own-key
MODEL_NAME=replace-with-your-vision-model

# Feature switches. Keep false unless you understand the risk.
ALLOW_LOCAL_IMAGE_PATHS=false
ALLOW_CLIPBOARD_IMAGES=false
ALLOW_PRIVATE_NETWORK_URLS=false
USE_JINA_READER=false

# Limits
MAX_IMAGE_BYTES=10485760

# Optional: override Claude upload directories (platform-specific).
# CLAUDE_UPLOAD_DIRS=
# CLAUDE_UPLOAD_DIRS_DELIMITER=
````

### .gitignore

````javascript
node_modules/
.env
work/
outputs/
*.log
*.tgz
.DS_Store
````

### src/server.mjs

````javascript
#!/usr/bin/env node
import { readFile } from 'node:fs/promises';

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';

import { askModel, askModelWithImage } from './model-client.mjs';
import { buildWebContext, extractUrls } from './web-reader.mjs';

const DEFAULT_MODEL = process.env.MODEL_NAME || 'replace-with-your-vision-model';
const packageInfo = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));

const server = new McpServer({
  name: 'mcp-vision-web-bridge',
  version: packageInfo.version
});

server.registerTool(
  'read_image_with_model',
  {
    title: 'Read Image With Model',
    description:
      'Read an image from the latest Claude upload, an image URL, base64, an allowed local path, or clipboard, then send it to the configured vision-capable model.',
    inputSchema: {
      prompt: z.string().default('Please describe this image. If it contains text, extract the text.'),
      image_path: z.string().optional().describe('Local image path. Disabled unless ALLOW_LOCAL_IMAGE_PATHS=true.'),
      image_url: z.string().optional().describe('HTTP/HTTPS image URL or data URL.'),
      image_base64: z.string().optional().describe('Raw base64 or data URL.'),
      mime_type: z.string().default('image/png').describe('MIME type for raw base64 input.'),
      use_latest_upload: z.boolean().default(true).describe('When no image source is provided, read the newest recent Claude upload.'),
      use_clipboard: z.boolean().default(false).describe('Read macOS clipboard image. Disabled unless ALLOW_CLIPBOARD_IMAGES=true.'),
      max_age_minutes: z.number().int().min(1).max(1440).default(240),
      model: z.string().default(DEFAULT_MODEL),
      max_tokens: z.number().int().min(64).max(32768).default(8192),
      temperature: z.number().min(0).max(2).optional()
    }
  },
  async ({
    prompt,
    image_path: imagePath,
    image_url: imageUrl,
    image_base64: imageBase64,
    mime_type: mimeType,
    use_latest_upload: useLatestUpload,
    use_clipboard: useClipboard,
    max_age_minutes: maxAgeMinutes,
    model,
    max_tokens: maxTokens,
    temperature
  }) => {
    const hasExplicitImage = Boolean(imagePath || imageUrl || imageBase64 || useClipboard);
    const result = await askModelWithImage({
      prompt,
      imagePath,
      imageUrl,
      imageBase64,
      mimeType,
      fromClipboard: useClipboard,
      latestClaudeUpload: !hasExplicitImage && useLatestUpload,
      maxAgeMinutes,
      model,
      maxTokens,
      temperature
    });

    return {
      content: [
        {
          type: 'text',
          text: [`Image source: ${formatImageSource(result.source)}`, '', result.text].join('\n')
        }
      ]
    };
  }
);

server.registerPrompt(
  'img',
  {
    title: 'Read latest uploaded image',
    description: 'Ask the vision MCP tool to read the latest image uploaded to the client.',
    argsSchema: {
      prompt: z.string().optional().describe('What to analyze in the image')
    }
  },
  async ({ prompt }) => ({
    messages: [
      {
        role: 'user',
        content: {
          type: 'text',
          text: [
            'Use the MCP tool `read_image_with_model` with `use_latest_upload=true` and `use_clipboard=false`.',
            `Prompt: ${prompt || 'Please describe this image. If it contains text, extract the text.'}`
          ].join('\n')
        }
      }
    ]
  })
);

server.registerPrompt(
  'clipboard-image',
  {
    title: 'Read clipboard image',
    description: 'Ask the vision MCP tool to read the current clipboard image.',
    argsSchema: {
      prompt: z.string().optional().describe('What to analyze in the image')
    }
  },
  async ({ prompt }) => ({
    messages: [
      {
        role: 'user',
        content: {
          type: 'text',
          text: [
            'Use the MCP tool `read_image_with_model` with `use_clipboard=true` and `use_latest_upload=false`.',
            `Prompt: ${prompt || 'Please describe this image. If it contains text, extract the text.'}`
          ].join('\n')
        }
      }
    ]
  })
);

server.registerTool(
  'read_links_with_model',
  {
    title: 'Read Links With Model',
    description:
      'Extract web links from user input, fetch readable page content locally, then ask the configured model to summarize, translate, or answer questions.',
    inputSchema: {
      input: z.string().min(1).describe('User request containing one or more URLs.'),
      instruction: z.string().default('Please read these links, summarize the main points, and answer the user request.'),
      max_urls: z.number().int().min(1).max(8).default(5),
      max_chars_per_url: z.number().int().min(1000).max(60000).default(24000),
      model: z.string().default(DEFAULT_MODEL),
      max_tokens: z.number().int().min(64).max(32768).default(8192),
      temperature: z.number().min(0).max(2).optional()
    }
  },
  async ({
    input,
    instruction,
    max_urls: maxUrls,
    max_chars_per_url: maxCharsPerUrl,
    model,
    max_tokens: maxTokens,
    temperature
  }) => {
    const urls = extractUrls(input);
    if (!urls.length) {
      throw new Error('No URLs found in input');
    }

    const webContext = await buildWebContext(input, {
      maxUrls,
      maxCharsPerUrl
    });
    const prompt = [
      instruction,
      '',
      'User request:',
      input,
      '',
      'Fetched web content:',
      webContext.text
    ].join('\n');
    const text = await askModel({
      prompt,
      model,
      maxTokens,
      temperature
    });

    return {
      content: [
        {
          type: 'text',
          text
        }
      ]
    };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);

function formatImageSource(source) {
  if (!source?.type) return 'unknown';
  if (source.type === 'latest_upload') return 'latest uploaded image';
  if (source.type === 'clipboard') return 'clipboard image';
  if (source.type === 'local_path') return 'local image path';
  if (source.type === 'image_url') return 'image URL';
  if (source.type === 'data_url') return 'data URL';
  if (source.type === 'base64') return 'base64 image';
  return source.type;
}
````

### src/model-client.mjs

````javascript
import { execFile as execFileCallback } from 'node:child_process';
import { readFile, mkdtemp, readdir, rm, stat } from 'node:fs/promises';
import { isIP } from 'node:net';
import { homedir, platform, tmpdir } from 'node:os';
import { extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const execFile = promisify(execFileCallback);

const DEFAULT_SYSTEM_PROMPT = [
  'You are a helpful assistant.',
  'Answer clearly and avoid exposing private data unless the user explicitly included it.'
].join('\n');

const DEFAULT_IMAGE_PROMPT = 'Please describe this image. If it contains text, extract the text.';
const DEFAULT_MODEL = process.env.MODEL_NAME || 'replace-with-your-vision-model';
const DEFAULT_BASE_URL = process.env.MODEL_BASE_URL || process.env.OPENAI_BASE_URL || 'https://api.example.com/v1';
const DEFAULT_MAX_IMAGE_BYTES = Number.parseInt(process.env.MAX_IMAGE_BYTES || '10485760', 10);

const MIME_BY_EXTENSION = new Map([
  ['.png', 'image/png'],
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.gif', 'image/gif'],
  ['.webp', 'image/webp'],
  ['.tif', 'image/tiff'],
  ['.tiff', 'image/tiff']
]);

const MACOS_CLIPBOARD_IMAGE_SCRIPT = `
ObjC.import("AppKit");
ObjC.import("Foundation");

const out = ObjC.unwrap($.NSProcessInfo.processInfo.environment.objectForKey("OUT"));
const pb = $.NSPasteboard.generalPasteboard;
const types = ObjC.deepUnwrap(pb.types) || [];
const candidates = ["public.png", "public.jpeg", "public.tiff", "com.compuserve.gif"];
const chosen = candidates.find((type) => types.includes(type));

if (!chosen) {
  throw new Error("No image found in clipboard");
}

const data = pb.dataForType(chosen);
if (!data) {
  throw new Error("Clipboard image data is empty");
}

if (!data.writeToFileAtomically(out, true)) {
  throw new Error("Failed to write clipboard image");
}

console.log(chosen);
`;

const WINDOWS_CLIPBOARD_IMAGE_SCRIPT = `
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$image = [System.Windows.Forms.Clipboard]::GetImage()
if ($null -eq $image) {
  throw "No image found in clipboard"
}
$image.Save($env:OUT, [System.Drawing.Imaging.ImageFormat]::Png)
`;

export function buildChatMessages({ prompt, system = DEFAULT_SYSTEM_PROMPT }) {
  if (!prompt || typeof prompt !== 'string') {
    throw new Error('prompt is required');
  }

  const messages = [];
  if (system) {
    messages.push({
      role: 'system',
      content: system
    });
  }
  messages.push({
    role: 'user',
    content: prompt
  });

  return messages;
}

export function buildChatRequest({
  messages,
  model = DEFAULT_MODEL,
  maxTokens = 8192,
  temperature
}) {
  const request = {
    model,
    messages,
    max_tokens: maxTokens,
    stream: false
  };

  if (typeof temperature === 'number') {
    request.temperature = temperature;
  }

  return request;
}

export async function askModel({
  prompt,
  system,
  model = DEFAULT_MODEL,
  baseUrl = DEFAULT_BASE_URL,
  apiKey = process.env.MODEL_API_KEY,
  maxTokens = 8192,
  temperature,
  fetchImpl = fetch
}) {
  if (!apiKey) {
    throw new Error('Missing MODEL_API_KEY');
  }

  const url = new URL('chat/completions', normalizeBaseUrl(baseUrl));
  const request = buildChatRequest({
    messages: buildChatMessages({
      prompt,
      system
    }),
    model,
    maxTokens,
    temperature
  });

  const response = await fetchImpl(url, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${apiKey}`,
      'content-type': 'application/json'
    },
    body: JSON.stringify(request)
  });

  const payload = await safeJson(response);
  if (!response.ok) {
    throw new Error(formatModelError(response, payload, 'Model request'));
  }

  return extractChatText(payload);
}

export async function askModelWithImage({
  prompt = DEFAULT_IMAGE_PROMPT,
  system,
  imagePath,
  imageUrl,
  imageBase64,
  mimeType = 'image/png',
  fromClipboard = false,
  latestClaudeUpload = false,
  maxAgeMinutes = 240,
  model = DEFAULT_MODEL,
  baseUrl = DEFAULT_BASE_URL,
  apiKey = process.env.MODEL_API_KEY,
  maxTokens = 8192,
  temperature,
  fetchImpl = fetch
}) {
  if (!apiKey) {
    throw new Error('Missing MODEL_API_KEY');
  }

  const imageInput = await resolveImageInput({
    imagePath,
    imageUrl,
    imageBase64,
    mimeType,
    fromClipboard,
    latestClaudeUpload,
    maxAgeMinutes
  });
  const messages = [];

  if (system) {
    messages.push({
      role: 'system',
      content: system
    });
  }

  messages.push({
    role: 'user',
    content: [
      {
        type: 'text',
        text: prompt
      },
      {
        type: 'image_url',
        image_url: {
          url: imageInput.url
        }
      }
    ]
  });

  const url = new URL('chat/completions', normalizeBaseUrl(baseUrl));
  const response = await fetchImpl(url, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${apiKey}`,
      'content-type': 'application/json'
    },
    body: JSON.stringify(buildChatRequest({
      messages,
      model,
      maxTokens,
      temperature
    }))
  });

  const payload = await safeJson(response);
  if (!response.ok) {
    throw new Error(formatModelError(response, payload, 'Vision request'));
  }

  return {
    text: extractChatText(payload),
    source: imageInput.source
  };
}

export async function buildImageUrl({
  imagePath,
  imageUrl,
  imageBase64,
  mimeType = 'image/png',
  fromClipboard = false,
  latestClaudeUpload = false,
  maxAgeMinutes = 240
}) {
  const imageInput = await resolveImageInput({
    imagePath,
    imageUrl,
    imageBase64,
    mimeType,
    fromClipboard,
    latestClaudeUpload,
    maxAgeMinutes
  });

  return imageInput.url;
}

export async function resolveImageInput({
  imagePath,
  imageUrl,
  imageBase64,
  mimeType = 'image/png',
  fromClipboard = false,
  latestClaudeUpload = false,
  maxAgeMinutes = 240,
  allowPrivateNetworkUrls = process.env.ALLOW_PRIVATE_NETWORK_URLS === 'true'
}) {
  const provided = [
    imagePath,
    imageUrl,
    imageBase64,
    fromClipboard ? 'clipboard' : '',
    latestClaudeUpload ? 'latestClaudeUpload' : ''
  ].filter(Boolean).length;

  if (provided !== 1) {
    throw new Error('Provide exactly one image source');
  }

  if (imageUrl) {
    validateImageUrl(imageUrl, {
      allowPrivateNetworkUrls
    });
    return {
      url: imageUrl,
      source: {
        type: imageUrl.startsWith('data:') ? 'data_url' : 'image_url'
      }
    };
  }

  if (imageBase64) {
    return {
      url: normalizeBase64Image(imageBase64, mimeType),
      source: {
        type: 'base64',
        mimeType
      }
    };
  }

  if (fromClipboard) {
    assertEnabled('ALLOW_CLIPBOARD_IMAGES', 'Clipboard image reading is disabled by default');
    return {
      url: await readClipboardImageAsDataUrl(),
      source: {
        type: 'clipboard'
      }
    };
  }

  if (latestClaudeUpload) {
    const latest = await findLatestClaudeUpload({
      maxAgeMinutes
    });
    return {
      url: await readLocalImageAsDataUrl(latest.path),
      source: {
        type: 'latest_upload',
        mimeType: latest.mimeType,
        size: latest.size
      }
    };
  }

  assertEnabled('ALLOW_LOCAL_IMAGE_PATHS', 'Local image path reading is disabled by default');
  return {
    url: await readLocalImageAsDataUrl(imagePath),
    source: {
      type: 'local_path'
    }
  };
}

export async function findLatestClaudeUpload({
  uploadDirs = parseClaudeUploadDirs(),
  maxAgeMinutes = 240,
  now = Date.now()
} = {}) {
  const maxAgeMs = maxAgeMinutes * 60 * 1000;
  const candidates = [];

  for (const dir of uploadDirs) {
    const resolvedDir = resolveLocalPath(dir);
    let entries;

    try {
      entries = await readdir(resolvedDir, {
        withFileTypes: true
      });
    } catch (error) {
      if (error?.code === 'ENOENT') continue;
      throw error;
    }

    for (const entry of entries) {
      if (!entry.isFile()) continue;

      const path = join(resolvedDir, entry.name);
      const info = await stat(path);
      const ageMs = now - info.mtimeMs;

      if (ageMs < 0 || ageMs > maxAgeMs) continue;
      if (info.size > getMaxImageBytes()) continue;

      const mimeType = await detectImageMimeTypeFromFile(path);
      if (!mimeType?.startsWith('image/')) continue;

      candidates.push({
        path,
        mimeType,
        mtimeMs: info.mtimeMs,
        size: info.size
      });
    }
  }

  candidates.sort((a, b) => b.mtimeMs - a.mtimeMs);

  if (!candidates.length) {
    throw new Error('No recent uploaded image found');
  }

  return candidates[0];
}

export function getDefaultClaudeUploadDirs(osPlatform = platform()) {
  if (osPlatform === 'darwin') {
    return [
      '~/Library/Application Support/Claude-3p/pending-uploads',
      '~/Library/Application Support/Claude/pending-uploads'
    ];
  }

  if (osPlatform === 'win32') {
    return [
      '%APPDATA%\\Claude-3p\\pending-uploads',
      '%APPDATA%\\Claude\\pending-uploads',
      '%LOCALAPPDATA%\\Claude-3p\\pending-uploads',
      '%LOCALAPPDATA%\\Claude\\pending-uploads'
    ];
  }

  return [
    '~/.config/Claude-3p/pending-uploads',
    '~/.config/Claude/pending-uploads',
    '~/.local/share/Claude-3p/pending-uploads',
    '~/.local/share/Claude/pending-uploads'
  ];
}

export function extractChatText(payload) {
  const content = payload?.choices?.[0]?.message?.content;

  if (typeof content === 'string') {
    return content;
  }

  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === 'string') return part;
        if (part?.type === 'text' && typeof part.text === 'string') return part.text;
        return '';
      })
      .filter(Boolean)
      .join('\n');
  }

  const errorMessage = payload?.error?.message;
  if (errorMessage) {
    throw new Error(errorMessage);
  }

  throw new Error('No text returned from model');
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function formatModelError(response, payload, label) {
  const providerMessage = sanitizeErrorMessage(payload?.error?.message || payload?.message || '');
  const statusHint = getStatusHint(response.status);
  const details = [statusHint, providerMessage].filter(Boolean).join(' ');

  return details ? `${label} failed with ${response.status}. ${details}` : `${label} failed with ${response.status}`;
}

function getStatusHint(status) {
  if (status === 400) return 'Check whether the selected model supports vision and whether the image is a valid supported format.';
  if (status === 401 || status === 403) return 'Check MODEL_API_KEY and provider permissions.';
  if (status === 404) return 'Check MODEL_BASE_URL and MODEL_NAME.';
  if (status === 413) return 'The image or request is too large.';
  if (status === 429) return 'The provider rate limit or quota was reached.';
  if (status >= 500) return 'The provider endpoint returned a server error.';
  return '';
}

function sanitizeErrorMessage(value) {
  if (!value || typeof value !== 'string') {
    return '';
  }

  let sanitized = value;
  for (const secret of [process.env.MODEL_API_KEY, process.env.OPENAI_API_KEY]) {
    if (secret) {
      sanitized = sanitized.split(secret).join('[redacted]');
    }
  }
  return sanitized.replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer [redacted]');
}

function normalizeBase64Image(value, mimeType) {
  const trimmed = value.trim();
  if (trimmed.startsWith('data:')) {
    return trimmed;
  }

  return `data:${mimeType};base64,${trimmed.replace(/\s/g, '')}`;
}

async function readLocalImageAsDataUrl(imagePath) {
  const resolvedPath = resolveLocalPath(imagePath);
  const info = await stat(resolvedPath);
  if (!info.isFile()) {
    throw new Error('Image path must be a file');
  }
  if (info.size > getMaxImageBytes()) {
    throw new Error(`Image exceeds MAX_IMAGE_BYTES (${getMaxImageBytes()})`);
  }

  const data = await readFile(resolvedPath);
  const mimeType = detectImageMimeType(data) || MIME_BY_EXTENSION.get(extname(resolvedPath).toLowerCase());

  if (!mimeType) {
    throw new Error('Unsupported image type. Use PNG, JPEG, GIF, WebP, or TIFF.');
  }

  return `data:${mimeType};base64,${data.toString('base64')}`;
}

async function detectImageMimeTypeFromFile(path) {
  const data = await readFile(path);
  return detectImageMimeType(data) || MIME_BY_EXTENSION.get(extname(path).toLowerCase());
}

function detectImageMimeType(data) {
  if (data.length >= 8 && data.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) {
    return 'image/png';
  }

  if (data.length >= 3 && data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) {
    return 'image/jpeg';
  }

  if (data.length >= 6) {
    const signature = data.subarray(0, 6).toString('ascii');
    if (signature === 'GIF87a' || signature === 'GIF89a') {
      return 'image/gif';
    }
  }

  if (
    data.length >= 12 &&
    data.subarray(0, 4).toString('ascii') === 'RIFF' &&
    data.subarray(8, 12).toString('ascii') === 'WEBP'
  ) {
    return 'image/webp';
  }

  if (data.length >= 4) {
    const header = data.subarray(0, 4).toString('hex');
    if (header === '49492a00' || header === '4d4d002a') {
      return 'image/tiff';
    }
  }

  return undefined;
}

async function readClipboardImageAsDataUrl() {
  const osPlatform = platform();

  if (osPlatform === 'darwin') {
    return readMacosClipboardImageAsDataUrl();
  }

  if (osPlatform === 'win32') {
    return readWindowsClipboardImageAsDataUrl();
  }

  return readLinuxClipboardImageAsDataUrl();
}

async function readMacosClipboardImageAsDataUrl() {
  const dir = await mkdtemp(join(tmpdir(), 'mcp-clipboard-image-'));
  const rawPath = join(dir, 'clipboard-image');
  const pngPath = join(dir, 'clipboard-image.png');

  try {
    const { stdout } = await execFile(
      'osascript',
      ['-l', 'JavaScript', '-e', MACOS_CLIPBOARD_IMAGE_SCRIPT],
      {
        env: {
          ...process.env,
          OUT: rawPath
        },
        timeout: 10000
      }
    );
    const pasteboardType = stdout.trim().split(/\s+/).at(-1);

    if (pasteboardType === 'public.png') {
      const data = await readFile(rawPath);
      return `data:image/png;base64,${data.toString('base64')}`;
    }

    if (pasteboardType === 'public.jpeg') {
      const data = await readFile(rawPath);
      return `data:image/jpeg;base64,${data.toString('base64')}`;
    }

    if (pasteboardType === 'com.compuserve.gif') {
      const data = await readFile(rawPath);
      return `data:image/gif;base64,${data.toString('base64')}`;
    }

    await execFile('sips', ['-s', 'format', 'png', rawPath, '--out', pngPath], {
      timeout: 10000
    });
    const data = await readFile(pngPath);
    return `data:image/png;base64,${data.toString('base64')}`;
  } finally {
    await rm(dir, {
      recursive: true,
      force: true
    });
  }
}

async function readWindowsClipboardImageAsDataUrl() {
  const dir = await mkdtemp(join(tmpdir(), 'mcp-clipboard-image-'));
  const pngPath = join(dir, 'clipboard-image.png');

  try {
    await execFile(
      'powershell.exe',
      ['-NoProfile', '-STA', '-Command', WINDOWS_CLIPBOARD_IMAGE_SCRIPT],
      {
        env: {
          ...process.env,
          OUT: pngPath
        },
        timeout: 10000
      }
    );
    const data = await readFile(pngPath);
    return `data:image/png;base64,${data.toString('base64')}`;
  } finally {
    await rm(dir, {
      recursive: true,
      force: true
    });
  }
}

async function readLinuxClipboardImageAsDataUrl() {
  const wayland = await tryReadLinuxClipboardCommand('wl-paste', ['--type', 'image/png']);
  if (wayland) {
    return wayland;
  }

  const x11 = await tryReadLinuxClipboardCommand('xclip', ['-selection', 'clipboard', '-t', 'image/png', '-o']);
  if (x11) {
    return x11;
  }

  throw new Error('No clipboard image found. On Linux, install wl-clipboard or xclip and copy a PNG-compatible image.');
}

async function tryReadLinuxClipboardCommand(command, args) {
  try {
    const { stdout } = await execFile(command, args, {
      encoding: 'buffer',
      maxBuffer: getMaxImageBytes(),
      timeout: 10000
    });

    if (!Buffer.isBuffer(stdout) || stdout.length === 0) {
      return undefined;
    }

    if (stdout.length > getMaxImageBytes()) {
      throw new Error(`Clipboard image exceeds MAX_IMAGE_BYTES (${getMaxImageBytes()})`);
    }

    return `data:image/png;base64,${stdout.toString('base64')}`;
  } catch {
    return undefined;
  }
}

function normalizeBaseUrl(value) {
  const url = new URL(value);
  if (!url.pathname.endsWith('/')) {
    url.pathname += '/';
  }
  return url.href;
}

function resolveLocalPath(value) {
  if (!value || typeof value !== 'string') {
    throw new Error('imagePath is required');
  }

  const expandedValue = expandEnvironmentVariables(value);

  if (expandedValue.startsWith('file://')) {
    return fileURLToPath(expandedValue);
  }

  if (expandedValue === '~') {
    return homedir();
  }

  if (expandedValue.startsWith('~/')) {
    return resolve(join(homedir(), expandedValue.slice(2)));
  }

  return resolve(expandedValue);
}

function parseClaudeUploadDirs() {
  const configured = process.env.CLAUDE_UPLOAD_DIRS;
  if (!configured) {
    return getDefaultClaudeUploadDirs();
  }

  const delimiter = process.env.CLAUDE_UPLOAD_DIRS_DELIMITER || (platform() === 'win32' ? ';' : ':');

  return configured
    .split(delimiter)
    .map((value) => value.trim())
    .filter(Boolean);
}

function expandEnvironmentVariables(value) {
  return value
    .replace(/%([^%]+)%/g, (match, name) => process.env[name] || match)
    .replace(/\$([A-Z_][A-Z0-9_]*)/gi, (match, name) => process.env[name] || match);
}

function assertEnabled(name, message) {
  if (process.env[name] !== 'true') {
    throw new Error(`${message}. Set ${name}=true to enable it.`);
  }
}

function validateImageUrl(value, { allowPrivateNetworkUrls = false } = {}) {
  const url = new URL(value);
  if (!['http:', 'https:', 'data:'].includes(url.protocol)) {
    throw new Error('image_url must be http, https, or data URL');
  }
  if (url.protocol !== 'data:' && !allowPrivateNetworkUrls && isPrivateHostname(url.hostname)) {
    throw new Error('Private network image URLs are disabled by default');
  }
}

function getMaxImageBytes() {
  if (!Number.isInteger(DEFAULT_MAX_IMAGE_BYTES) || DEFAULT_MAX_IMAGE_BYTES <= 0) {
    return 10 * 1024 * 1024;
  }
  return DEFAULT_MAX_IMAGE_BYTES;
}

function isPrivateHostname(hostname) {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (normalized === 'localhost' || normalized.endsWith('.localhost')) return true;

  const ipVersion = isIP(normalized);
  if (!ipVersion) return false;

  if (ipVersion === 6) {
    return normalized === '::1' || normalized.startsWith('fc') || normalized.startsWith('fd') || normalized.startsWith('fe80:');
  }

  const parts = normalized.split('.').map((part) => Number.parseInt(part, 10));
  const [a, b] = parts;
  return (
    a === 10 ||
    a === 127 ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) ||
    a === 0
  );
}
````

### src/web-reader.mjs

````javascript
import { execFile as execFileCallback } from 'node:child_process';
import { isIP } from 'node:net';
import { promisify } from 'node:util';

const execFile = promisify(execFileCallback);

const DEFAULT_USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';

const DEFAULT_MAX_CHARS_PER_URL = 24000;
const DEFAULT_MAX_URLS = 5;
const DEFAULT_TIMEOUT_MS = 20000;

const ENTITY_MAP = new Map([
  ['amp', '&'],
  ['lt', '<'],
  ['gt', '>'],
  ['quot', '"'],
  ['apos', "'"],
  ['nbsp', ' ']
]);

export function extractUrls(text) {
  if (!text || typeof text !== 'string') {
    return [];
  }

  const seen = new Set();
  const matches = text.match(/https?:\/\/[^\s<>"'`，。！？、；：]+/g) || [];
  const urls = [];

  for (const match of matches) {
    const url = trimUrl(match);
    if (!url || seen.has(url)) continue;
    seen.add(url);
    urls.push(url);
  }

  return urls;
}

export function htmlToReadableText(html, { maxChars = DEFAULT_MAX_CHARS_PER_URL } = {}) {
  if (!html || typeof html !== 'string') {
    return '';
  }

  const title = decodeHtmlEntities(extractTitle(html));
  const text = decodeHtmlEntities(
    html
      .replace(/<!--[\s\S]*?-->/g, ' ')
      .replace(/<script\b[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style\b[\s\S]*?<\/style>/gi, ' ')
      .replace(/<noscript\b[\s\S]*?<\/noscript>/gi, ' ')
      .replace(/<svg\b[\s\S]*?<\/svg>/gi, ' ')
      .replace(/<canvas\b[\s\S]*?<\/canvas>/gi, ' ')
      .replace(/<\/?(?:article|aside|blockquote|br|dd|div|dl|dt|figcaption|figure|footer|form|h[1-6]|header|hr|li|main|nav|ol|p|pre|section|table|tbody|td|tfoot|th|thead|tr|ul)\b[^>]*>/gi, '\n')
      .replace(/<[^>]+>/g, ' ')
  );
  const lines = text
    .split(/\n+/)
    .map((line) => line.replace(/[ \t\f\v]+/g, ' ').trim())
    .filter(Boolean);
  const body = truncate(lines.join('\n'), maxChars);

  return [title ? `Title: ${title}` : '', body].filter(Boolean).join('\n\n');
}

export async function fetchReadableUrl(
  url,
  {
    fetchImpl = fetch,
    maxChars = DEFAULT_MAX_CHARS_PER_URL,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    useJinaFallback = process.env.USE_JINA_READER === 'true',
    allowPrivateNetworkUrls = process.env.ALLOW_PRIVATE_NETWORK_URLS === 'true'
  } = {}
) {
  validateHttpUrl(url, {
    allowPrivateNetworkUrls
  });

  let primary;

  try {
    primary = await fetchReadableUrlOnce(url, {
      fetchImpl,
      maxChars,
      timeoutMs
    });
  } catch (error) {
    if (!useJinaFallback) {
      throw error;
    }

    const fallback = await fetchReadableUrlOnce(toJinaReaderUrl(url), {
      fetchImpl,
      maxChars,
      timeoutMs
    });

    return {
      ...fallback,
      url,
      fetchedUrl: fallback.url,
      reader: 'jina'
    };
  }

  const needsFallback = shouldUseJinaFallback(primary);
  if (!needsFallback || !useJinaFallback) {
    return primary;
  }

  try {
    const fallback = await fetchReadableUrlOnce(toJinaReaderUrl(url), {
      fetchImpl,
      maxChars,
      timeoutMs
    });

    if (fallback.ok && (needsFallback || fallback.text.length >= primary.text.length)) {
      return {
        ...fallback,
        url,
        fetchedUrl: fallback.url,
        reader: 'jina'
      };
    }
  } catch {
    // Keep the primary result when the optional reader is unavailable.
  }

  return primary;
}

export async function buildWebContext(
  input,
  {
    fetchImpl = fetch,
    maxUrls = DEFAULT_MAX_URLS,
    maxCharsPerUrl = DEFAULT_MAX_CHARS_PER_URL,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    useJinaFallback = process.env.USE_JINA_READER === 'true'
  } = {}
) {
  const urls = extractUrls(input).slice(0, maxUrls);
  const pages = [];

  for (const url of urls) {
    try {
      const page = await fetchReadableUrl(url, {
        fetchImpl,
        maxChars: maxCharsPerUrl,
        timeoutMs,
        useJinaFallback
      });
      pages.push(page);
    } catch (error) {
      pages.push({
        url,
        status: 0,
        ok: false,
        text: `读取失败：${error.message}`
      });
    }
  }

  return {
    urls,
    pages,
    text: pages
      .map((page, index) => {
        const status = page.status ? `Status: ${page.status}` : 'Status: failed';
        return [`Source ${index + 1}: ${page.url}`, status, page.text].join('\n');
      })
      .join('\n\n---\n\n')
  };
}

async function fetchReadableUrlOnce(url, { fetchImpl, maxChars, timeoutMs }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    let response;

    try {
      response = await fetchImpl(url, {
        redirect: 'follow',
        signal: controller.signal,
        headers: {
          'user-agent': DEFAULT_USER_AGENT,
          accept: 'text/html,application/xhtml+xml,application/xml,text/plain,application/json,*/*;q=0.8',
          'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
      });
    } catch (error) {
      if (fetchImpl !== fetch) {
        throw error;
      }

      return fetchReadableUrlWithCurl(url, {
        maxChars,
        timeoutMs
      });
    }

    const contentType = response.headers.get('content-type') || '';
    const body = await response.text();
    const text = normalizeResponseText(body, contentType, maxChars);

    return {
      url,
      fetchedUrl: response.url || url,
      status: response.status,
      ok: response.ok,
      contentType,
      text
    };
  } finally {
    clearTimeout(timer);
  }
}

async function fetchReadableUrlWithCurl(url, { maxChars, timeoutMs }) {
  const marker = '\n__MCP_WEB_READER_META__\n';
  const timeoutSeconds = Math.max(1, Math.ceil(timeoutMs / 1000));
  const { stdout } = await execFile(
    'curl',
    [
      '-sS',
      '-L',
      '--max-time',
      String(timeoutSeconds),
      '-A',
      DEFAULT_USER_AGENT,
      '-H',
      'Accept: text/html,application/xhtml+xml,application/xml,text/plain,application/json,*/*;q=0.8',
      '-H',
      'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8',
      '-w',
      `${marker}%{http_code}\n%{content_type}\n%{url_effective}`,
      url
    ],
    {
      encoding: 'utf8',
      maxBuffer: 16 * 1024 * 1024,
      timeout: timeoutMs + 5000
    }
  );
  const markerIndex = stdout.lastIndexOf(marker);

  if (markerIndex === -1) {
    throw new Error('curl did not return response metadata');
  }

  const body = stdout.slice(0, markerIndex);
  const [statusLine = '0', contentType = '', effectiveUrl = url] = stdout
    .slice(markerIndex + marker.length)
    .split('\n');
  const status = Number.parseInt(statusLine, 10) || 0;

  return {
    url,
    fetchedUrl: effectiveUrl,
    status,
    ok: status >= 200 && status < 300,
    contentType,
    text: normalizeResponseText(body, contentType, maxChars)
  };
}

function normalizeResponseText(body, contentType, maxChars) {
  if (contentType.includes('text/html') || /<\/?[a-z][\s\S]*>/i.test(body)) {
    return htmlToReadableText(body, {
      maxChars
    });
  }

  if (contentType.includes('application/json')) {
    try {
      return truncate(JSON.stringify(JSON.parse(body), null, 2), maxChars);
    } catch {
      return truncate(body, maxChars);
    }
  }

  return truncate(body.replace(/\r\n/g, '\n').replace(/[ \t\f\v]+/g, ' ').trim(), maxChars);
}

function shouldUseJinaFallback(page) {
  if (page.reader === 'jina') return false;
  if (!page.ok) return true;
  if (/application\/pdf/i.test(page.contentType)) return true;
  if (
    page.text.length < 1000 &&
    /<script|enable javascript|captcha|access denied|cloudflare|something went wrong|try again|privacy related extensions|don.t miss what.s happening/i.test(
      page.text
    )
  ) {
    return true;
  }
  return false;
}

function toJinaReaderUrl(url) {
  return `https://r.jina.ai/${url}`;
}

function extractTitle(html) {
  return html.match(/<title\b[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.replace(/<[^>]+>/g, ' ').trim() || '';
}

function decodeHtmlEntities(text) {
  return text.replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (entity, raw) => {
    const lower = raw.toLowerCase();
    if (lower.startsWith('#x')) {
      return String.fromCodePoint(Number.parseInt(lower.slice(2), 16));
    }
    if (lower.startsWith('#')) {
      return String.fromCodePoint(Number.parseInt(lower.slice(1), 10));
    }
    return ENTITY_MAP.get(lower) ?? entity;
  });
}

function truncate(text, maxChars) {
  if (text.length <= maxChars) {
    return text;
  }

  return `${text.slice(0, maxChars)}\n\n[Truncated]`;
}

function validateHttpUrl(url, { allowPrivateNetworkUrls }) {
  const parsed = new URL(url);
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('Only http and https URLs are supported');
  }

  if (!allowPrivateNetworkUrls && isPrivateHostname(parsed.hostname)) {
    throw new Error('Private network URLs are disabled by default');
  }
}

function isPrivateHostname(hostname) {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (normalized === 'localhost' || normalized.endsWith('.localhost')) return true;

  const ipVersion = isIP(normalized);
  if (!ipVersion) return false;

  if (ipVersion === 6) {
    return normalized === '::1' || normalized.startsWith('fc') || normalized.startsWith('fd') || normalized.startsWith('fe80:');
  }

  const parts = normalized.split('.').map((part) => Number.parseInt(part, 10));
  const [a, b] = parts;
  return (
    a === 10 ||
    a === 127 ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) ||
    a === 0
  );
}

function trimUrl(value) {
  return value.replace(/[，。！？、；：,.!?;:)\]}>]+$/g, '');
}
````

### scripts/check-secrets.mjs

````javascript
#!/usr/bin/env node
import { readdir, readFile, stat } from 'node:fs/promises';
import { join, relative } from 'node:path';

const ROOT = process.cwd();
const EXCLUDED_DIRS = new Set(['.git', '.claude', 'node_modules', 'coverage', 'dist']);
const EXCLUDED_FILES = new Set(['.env', 'package-lock.json', 'scripts/check-secrets.mjs']);
const SECRET_PATTERNS = [
  ['OpenAI-style API key', /sk-[A-Za-z0-9_-]{16,}/],
  ['Slack token', /xox[baprs]-/],
  ['GitHub token', /gh[pousr]_[A-Za-z0-9_]{20,}/],
  ['AWS access key', /AKIA[0-9A-Z]{16}/],
  ['Bearer token', /Bearer\s+[A-Za-z0-9._~+/=-]{16,}/],
  ['personal absolute path', /\/Users\/[^\s"'`]+/]
];

const findings = [];

await scanDir(ROOT);

if (findings.length) {
  for (const finding of findings) {
    console.error(`${finding.file}:${finding.line}: ${finding.kind}`);
  }
  process.exitCode = 1;
}

async function scanDir(dir) {
  const entries = await readdir(dir, {
    withFileTypes: true
  });

  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    const relPath = relative(ROOT, fullPath) || entry.name;

    if (entry.isDirectory()) {
      if (EXCLUDED_DIRS.has(entry.name)) continue;
      await scanDir(fullPath);
      continue;
    }

    if (!entry.isFile()) continue;
    if (EXCLUDED_FILES.has(relPath) || relPath.endsWith('.tgz')) continue;

    await scanFile(fullPath, relPath);
  }
}

async function scanFile(fullPath, relPath) {
  const info = await stat(fullPath);
  if (info.size > 2 * 1024 * 1024) return;

  let text;
  try {
    text = await readFile(fullPath, 'utf8');
  } catch {
    return;
  }

  const lines = text.split(/\r?\n/);
  for (const [index, line] of lines.entries()) {
    for (const [kind, pattern] of SECRET_PATTERNS) {
      if (pattern.test(line)) {
        findings.push({
          file: relPath,
          line: index + 1,
          kind
        });
      }
    }
  }
}
````

### test/model-client.test.mjs

````javascript
import assert from 'node:assert/strict';
import { mkdtemp, rm, utimes, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import {
  askModelWithImage,
  buildChatMessages,
  buildChatRequest,
  buildImageUrl,
  extractChatText,
  findLatestClaudeUpload,
  getDefaultClaudeUploadDirs,
  resolveImageInput
} from '../src/model-client.mjs';

test('builds OpenAI-compatible chat messages', () => {
  const messages = buildChatMessages({
    prompt: 'hello',
    system: 'system prompt'
  });
  const request = buildChatRequest({
    messages,
    model: 'vision-model',
    maxTokens: 4096
  });

  assert.deepEqual(messages, [
    { role: 'system', content: 'system prompt' },
    { role: 'user', content: 'hello' }
  ]);
  assert.equal(request.model, 'vision-model');
  assert.equal(request.max_tokens, 4096);
  assert.equal(request.stream, false);
});

test('extracts text from chat completion responses', () => {
  assert.equal(
    extractChatText({
      choices: [
        {
          message: {
            content: 'ok'
          }
        }
      ]
    }),
    'ok'
  );
});

test('has cross-platform default upload directories', () => {
  assert.deepEqual(getDefaultClaudeUploadDirs('darwin'), [
    '~/Library/Application Support/Claude-3p/pending-uploads',
    '~/Library/Application Support/Claude/pending-uploads'
  ]);
  assert.ok(getDefaultClaudeUploadDirs('win32').some((dir) => dir.includes('%APPDATA%')));
  assert.ok(getDefaultClaudeUploadDirs('linux').some((dir) => dir.includes('.config')));
});

test('disables explicit local image paths by default', async () => {
  await assert.rejects(
    () =>
      buildImageUrl({
        imagePath: '/tmp/example.png'
      }),
    /ALLOW_LOCAL_IMAGE_PATHS/
  );
});

test('builds data URLs from local image files when enabled', async () => {
  const previous = process.env.ALLOW_LOCAL_IMAGE_PATHS;
  process.env.ALLOW_LOCAL_IMAGE_PATHS = 'true';
  const dir = await mkdtemp(join(tmpdir(), 'mcp-vision-image-test-'));
  const imagePath = join(dir, 'pixel.png');

  try {
    await writeFile(
      imagePath,
      Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
        'base64'
      )
    );

    const imageUrl = await buildImageUrl({
      imagePath
    });

    assert.match(imageUrl, /^data:image\/png;base64,/);
  } finally {
    if (previous === undefined) {
      delete process.env.ALLOW_LOCAL_IMAGE_PATHS;
    } else {
      process.env.ALLOW_LOCAL_IMAGE_PATHS = previous;
    }
    await rm(dir, {
      recursive: true,
      force: true
    });
  }
});

test('finds the latest recent uploaded image', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'mcp-vision-upload-test-'));
  const olderPath = join(dir, 'older.jpg');
  const newerPath = join(dir, 'newer.jpg');
  const now = Date.now();

  try {
    await writeFile(olderPath, Buffer.from([0xff, 0xd8, 0xff, 0xdb, 0x00, 0x43]));
    await writeFile(newerPath, Buffer.from([0xff, 0xd8, 0xff, 0xdb, 0x00, 0x43]));
    await utimes(olderPath, new Date(now - 120000), new Date(now - 120000));
    await utimes(newerPath, new Date(now - 30000), new Date(now - 30000));

    const latest = await findLatestClaudeUpload({
      uploadDirs: [dir],
      maxAgeMinutes: 5,
      now
    });

    assert.equal(latest.path, newerPath);
    assert.equal(latest.mimeType, 'image/jpeg');
  } finally {
    await rm(dir, {
      recursive: true,
      force: true
    });
  }
});

test('sends image content to chat completions', async () => {
  let requestBody;
  const result = await askModelWithImage({
    prompt: 'describe',
    imageBase64: 'AAAA',
    apiKey: 'test-key',
    model: 'vision-model',
    fetchImpl: async (url, init) => {
      assert.equal(String(url), 'https://api.example.com/v1/chat/completions');
      requestBody = JSON.parse(init.body);

      return new Response(
        JSON.stringify({
          choices: [
            {
              message: {
                content: 'ok'
              }
            }
          ]
        }),
        {
          status: 200,
          headers: {
            'content-type': 'application/json'
          }
        }
      );
    }
  });

  assert.equal(result.text, 'ok');
  assert.deepEqual(result.source, {
    type: 'base64',
    mimeType: 'image/png'
  });
  assert.deepEqual(requestBody.messages[0].content, [
    {
      type: 'text',
      text: 'describe'
    },
    {
      type: 'image_url',
      image_url: {
        url: 'data:image/png;base64,AAAA'
      }
    }
  ]);
});

test('blocks private network image URLs by default', async () => {
  await assert.rejects(
    () =>
      resolveImageInput({
        imageUrl: 'http://127.0.0.1/image.png'
      }),
    /Private network image URLs/
  );
});

test('formats provider errors without leaking bearer tokens', async () => {
  await assert.rejects(
    () =>
      askModelWithImage({
        prompt: 'describe',
        imageBase64: 'AAAA',
        apiKey: 'test-key',
        fetchImpl: async () =>
          new Response(
            JSON.stringify({
              error: {
                message: 'bad request Bearer test-key'
              }
            }),
            {
              status: 400,
              headers: {
                'content-type': 'application/json'
              }
            }
          )
      }),
    /Bearer \[redacted\]/
  );
});
````

### test/web-reader.test.mjs

````javascript
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  buildWebContext,
  extractUrls,
  fetchReadableUrl,
  htmlToReadableText
} from '../src/web-reader.mjs';

test('extracts URLs from mixed text', () => {
  assert.deepEqual(extractUrls('Read https://example.com/a?b=1 and https://x.com/example/status/123。'), [
    'https://example.com/a?b=1',
    'https://x.com/example/status/123'
  ]);
});

test('converts HTML into readable text', () => {
  const readable = htmlToReadableText(`
    <html>
      <head>
        <title>Test title</title>
        <style>.hidden { display: none; }</style>
        <script>window.bad = true;</script>
      </head>
      <body>
        <main>
          <h1>Main title</h1>
          <p>First&nbsp;paragraph.</p>
          <p>Second paragraph.</p>
        </main>
      </body>
    </html>
  `);

  assert.match(readable, /Title: Test title/);
  assert.match(readable, /Main title/);
  assert.match(readable, /First paragraph/);
  assert.doesNotMatch(readable, /window\.bad/);
  assert.doesNotMatch(readable, /display: none/);
});

test('blocks private network URLs by default', async () => {
  await assert.rejects(() => fetchReadableUrl('http://127.0.0.1:3000/private'), /Private network URLs/);
  await assert.rejects(() => fetchReadableUrl('http://localhost/private'), /Private network URLs/);
  await assert.rejects(() => fetchReadableUrl('http://192.168.1.1/private'), /Private network URLs/);
});

test('fetches a readable web page', async () => {
  const readable = await fetchReadableUrl('https://example.com/post', {
    fetchImpl: async (url, init) => {
      assert.equal(String(url), 'https://example.com/post');
      assert.match(init.headers['user-agent'], /Mozilla/);

      return new Response('<html><head><title>Hello</title></head><body><article><p>Article body</p></article></body></html>', {
        status: 200,
        headers: {
          'content-type': 'text/html; charset=utf-8'
        }
      });
    }
  });

  assert.equal(readable.url, 'https://example.com/post');
  assert.equal(readable.status, 200);
  assert.match(readable.text, /Title: Hello/);
  assert.match(readable.text, /Article body/);
});

test('uses optional Jina Reader fallback only when enabled', async () => {
  const calls = [];
  const readable = await fetchReadableUrl('https://x.com/example/status/1', {
    useJinaFallback: true,
    fetchImpl: async (url) => {
      calls.push(String(url));
      if (calls.length === 1) {
        throw new TypeError('fetch failed');
      }

      return new Response('Title: Fallback\n\nTweet content', {
        status: 200,
        headers: {
          'content-type': 'text/plain'
        }
      });
    }
  });

  assert.deepEqual(calls, [
    'https://x.com/example/status/1',
    'https://r.jina.ai/https://x.com/example/status/1'
  ]);
  assert.equal(readable.reader, 'jina');
  assert.match(readable.text, /Tweet content/);
});

test('builds web context from links in a prompt', async () => {
  const context = await buildWebContext('Summarize https://example.com/a and https://example.com/b', {
    fetchImpl: async (url) =>
      new Response(`<html><body><p>Body ${url}</p></body></html>`, {
        status: 200,
        headers: {
          'content-type': 'text/html'
        }
      }),
    maxCharsPerUrl: 80
  });

  assert.deepEqual(context.urls, ['https://example.com/a', 'https://example.com/b']);
  assert.match(context.text, /Source 1: https:\/\/example\.com\/a/);
  assert.match(context.text, /Body https:\/\/example\.com\/b/);
});
````

### README.md

````javascript
# mcp-vision-web-bridge

Local MCP server that gives Claude Desktop, Claude Code, and other MCP clients two practical bridge tools:

- read an image from a recent Claude upload, clipboard, local path, URL, or base64 input, then send it to an OpenAI-compatible vision model;
- read web links locally, extract readable text, then send the result to an OpenAI-compatible model.

It does not include a model or any model credits. You bring your own OpenAI-compatible API endpoint and API key.

## Use Cases

- Your Claude client can accept images, but the third-party model behind it does not reliably receive image content.
- Your model provider supports vision, but your MCP client needs a local tool to collect image inputs.
- You want a safer local web reader with private-network blocking enabled by default.

## Capabilities

| Capability | macOS | Windows | Linux |
| --- | --- | --- | --- |
| MCP server | Supported | Supported | Supported |
| OpenAI-compatible chat completions | Supported | Supported | Supported |
| Web page reading | Supported | Supported | Supported |
| Recent Claude upload image | Supported | Best effort | Best effort |
| Clipboard image | Supported | Supported via PowerShell / Windows Forms | Supported via `wl-paste` or `xclip` |

Recent Claude upload paths are client implementation details, not a stable public API. If auto-detection does not work in your environment, set `CLAUDE_UPLOAD_DIRS` manually.

## Security Defaults

The default configuration is intentionally conservative:

- `.env` is ignored and should never be committed.
- API keys are only read from environment variables.
- Explicit local image paths are disabled unless `ALLOW_LOCAL_IMAGE_PATHS=true`.
- Clipboard image reading is disabled unless `ALLOW_CLIPBOARD_IMAGES=true`.
- Private-network web and image URLs are disabled unless `ALLOW_PRIVATE_NETWORK_URLS=true`.
- Jina Reader fallback is disabled unless `USE_JINA_READER=true`.
- The server does not log prompts, image data, API keys, or fetched page bodies.

## Requirements

- Node.js 20 or newer
- npm

This is a Node.js project. It does not require Python or a virtual environment.

## Install

```bash
npm install
cp .env.example .env
```

Edit `.env`:

```bash
MODEL_BASE_URL=https://api.example.com/v1
MODEL_API_KEY=replace-with-your-own-key
MODEL_NAME=replace-with-your-vision-model

ALLOW_LOCAL_IMAGE_PATHS=false
ALLOW_CLIPBOARD_IMAGES=false
ALLOW_PRIVATE_NETWORK_URLS=false
USE_JINA_READER=false
MAX_IMAGE_BYTES=10485760
```

`MODEL_BASE_URL` must be an OpenAI-compatible `/v1` endpoint.

### SiliconFlow Example

```bash
MODEL_BASE_URL=https://api.siliconflow.cn/v1
MODEL_API_KEY=replace-with-your-own-key
MODEL_NAME=Qwen/Qwen3-VL-8B-Instruct
```

Use a model that supports vision input.

## Claude Desktop Config

Use absolute paths for your local checkout:

```json
{
  "mcpServers": {
    "vision-web-bridge": {
      "command": "node",
      "args": [
        "--env-file-if-exists=/absolute/path/to/mcp-vision-web-bridge/.env",
        "/absolute/path/to/mcp-vision-web-bridge/src/server.mjs"
      ]
    }
  }
}
```

Restart Claude Desktop after changing the config.

## Claude Code Config

Add the same server to your Claude Code MCP config. After restart, check `/mcp` and confirm that `vision-web-bridge` is connected.

The server exposes two tools:

- `read_image_with_model`
- `read_links_with_model`

It also exposes two MCP prompts:

- `/mcp__vision-web-bridge__img`
- `/mcp__vision-web-bridge__clipboard-image`

## Usage

Read the latest image uploaded to the Claude client:

```text
Use read_image_with_model with use_latest_upload=true.
```

Read the current clipboard image:

```text
Use read_image_with_model with use_clipboard=true and use_latest_upload=false.
```

Read a local image path after enabling `ALLOW_LOCAL_IMAGE_PATHS=true`:

```text
Use read_image_with_model with image_path="/absolute/path/to/image.png".
```

Read web links:

```text
Use read_links_with_model to summarize https://example.com/article
```

## Tool Details

### `read_image_with_model`

Supported image sources:

- latest Claude upload;
- public image URL;
- base64 image;
- data URL;
- local image path, opt-in only;
- clipboard image, opt-in only.

The tool returns the model response and a non-sensitive source label such as `latest uploaded image`, `clipboard image`, or `local image path`.

### `read_links_with_model`

The tool extracts URLs from the user input, fetches readable page content locally, and asks the configured model to summarize or answer questions.

Private-network URLs are blocked by default. Optional Jina Reader fallback can be enabled with `USE_JINA_READER=true`, which sends the URL to Jina Reader.

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `MODEL_BASE_URL` | `https://api.example.com/v1` | OpenAI-compatible `/v1` endpoint |
| `OPENAI_BASE_URL` | unset | Fallback base URL if `MODEL_BASE_URL` is not set |
| `MODEL_API_KEY` | unset | API key for the model provider |
| `MODEL_NAME` | `replace-with-your-vision-model` | Chat or vision model name |
| `CLAUDE_UPLOAD_DIRS` | client-specific defaults | Override upload directories |
| `CLAUDE_UPLOAD_DIRS_DELIMITER` | platform default | Directory list delimiter |
| `ALLOW_LOCAL_IMAGE_PATHS` | `false` | Allow explicit local image paths |
| `ALLOW_CLIPBOARD_IMAGES` | `false` | Allow reading image data from clipboard |
| `ALLOW_PRIVATE_NETWORK_URLS` | `false` | Allow private-network web and image URLs |
| `USE_JINA_READER` | `false` | Allow Jina Reader fallback |
| `MAX_IMAGE_BYTES` | `10485760` | Maximum image size in bytes |

## Development

```bash
npm test
npm run check:secrets
```

Before publishing, run:

```bash
npm pack --dry-run
```

Check the file list carefully. `.env`, logs, images, local screenshots, and personal paths must not be included.

## Windows Notes

- Use full absolute paths in `claude_desktop_config.json`.
- Save JSON config as UTF-8 without BOM.
- Restart Claude from the system tray after editing config.
- Clipboard image reading uses PowerShell / Windows Forms.

## License

MIT
````

### CHANGELOG.md

````javascript
# Changelog

## 0.2.0

- Add MCP prompts for latest uploaded images and clipboard images.
- Return a non-sensitive image source label with image recognition results.
- Block private-network image URLs by default.
- Replace local endpoint defaults with a placeholder API endpoint.
- Improve provider error messages and redact bearer tokens.
- Add release-time secret scanning and `prepack` checks.

## 0.1.0

- Initial MCP server with image reading and web link reading tools.
````

### SECURITY_REVIEW.md

````javascript
# Security Review Checklist

Use this checklist before publishing or tagging a release.

## Required Checks

- `.env` is present only locally and is not tracked.
- No real API keys, cookies, tokens, credentials, account IDs, or session data are present.
- No local screenshots, image caches, logs, downloads, transcripts, or personal drafts are present.
- No personal filesystem paths are present.
- No machine-specific network addresses are present in docs, examples, package metadata, or release notes.
- Local image paths remain disabled by default.
- Clipboard image reading remains disabled by default.
- Private-network web and image URLs remain disabled by default.
- Third-party reader fallback remains disabled by default.
- Tool errors do not echo bearer tokens or configured API keys.

## Current Security Boundaries

- `read_image_with_model` requires exactly one image source.
- `image_path` requires `ALLOW_LOCAL_IMAGE_PATHS=true`.
- `use_clipboard` requires `ALLOW_CLIPBOARD_IMAGES=true`.
- `image_url` blocks private-network hosts unless explicitly enabled.
- `read_links_with_model` blocks private-network hosts unless explicitly enabled.
- Jina Reader fallback requires `USE_JINA_READER=true`.
- The tool returns a non-sensitive image source label, not local file paths.
- The server does not intentionally log prompts, image content, API keys, or fetched web content.

## Release Commands

```bash
npm test
npm run check:secrets
npm pack --dry-run
```

Manually inspect the `npm pack --dry-run` file list before publishing.
````

### LICENSE

````javascript
MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
````

### vision.mjs

````javascript
import { askModelWithImage } from "./src/model-client.mjs";

const imagePath = process.argv[2];
const prompt = process.argv[3] || "请描述这张图片。如果包含文字，请提取文字。";

if (!imagePath) {
  console.error("Usage: node vision.mjs <image-path> [prompt]");
  process.exit(1);
}

try {
  const result = await askModelWithImage({
    prompt,
    imagePath,
    model: process.env.MODEL_NAME || "qwen-vl-max",
    maxTokens: 8192,
  });
  console.log(result.text);
} catch (err) {
  console.error("Error:", err.message);
  process.exit(1);
}
````

### setup.ps1

````javascript
# mcp-vision-web-bridge 一键配置脚本
# 以管理员身份运行（推荐）

Write-Host "=== mcp-vision-web-bridge 配置脚本 ===" -ForegroundColor Cyan
Write-Host ""

# 获取脚本所在目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "[1/3] 安装 Node.js 依赖..." -ForegroundColor Yellow
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "npm install 失败！请检查 Node.js 是否已安装（需要 v20+）" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "✓ 依赖安装完成" -ForegroundColor Green
Write-Host ""

# 构建绝对路径
$ServerPath = Join-Path $ScriptDir "src\server.mjs"
$EnvFilePath = Join-Path $ScriptDir ".env"

Write-Host "[2/3] 配置 Claude Desktop..." -ForegroundColor Yellow

# Claude Desktop 配置文件路径
$ConfigDir = "$env:APPDATA\Claude"
$ConfigFile = "$ConfigDir\claude_desktop_config.json"

# 确保目录存在
if (-not (Test-Path $ConfigDir)) {
    New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
}

# 读取或创建配置
$Config = @{}
if (Test-Path $ConfigFile) {
    try {
        $Config = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Host "配置文件格式异常，将创建新配置" -ForegroundColor Yellow
    }
}

# 确保 mcpServers 字段存在
if (-not $Config.mcpServers) {
    $Config = $Config | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue @{} -Force -PassThru
}

# 添加 vision-web-bridge 配置
$VisionConfig = @{
    command = "node"
    args = @(
        "--env-file-if-exists=$EnvFilePath",
        $ServerPath
    )
}

$Config.mcpServers | Add-Member -NotePropertyName "vision-web-bridge" -NotePropertyValue $VisionConfig -Force

# 保存配置文件（UTF-8 无 BOM）
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
$JsonString = $Config | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($ConfigFile, $JsonString, $Utf8NoBom)

Write-Host "✓ Claude Desktop 配置已更新" -ForegroundColor Green
Write-Host "  配置文件位置: $ConfigFile"
Write-Host ""

Write-Host "[3/3] 重启 Claude Desktop..." -ForegroundColor Yellow

# 停止 Claude Desktop 进程
$ClaudeProcesses = Get-Process -Name "Claude" -ErrorAction SilentlyContinue
if ($ClaudeProcesses) {
    $ClaudeProcesses | Stop-Process -Force
    Write-Host "✓ 已关闭 Claude Desktop" -ForegroundColor Green
    Start-Sleep -Seconds 3
} else {
    Write-Host "Claude Desktop 未在运行" -ForegroundColor Gray
}

# 重新启动 Claude Desktop
$ClaudePath = "$env:LOCALAPPDATA\Claude-3p\Claude-3p.exe"
if (Test-Path $ClaudePath) {
    Start-Process $ClaudePath
    Write-Host "✓ Claude Desktop 已重新启动" -ForegroundColor Green
} else {
    $ClaudePath2 = "$env:LOCALAPPDATA\Claude\Claude.exe"
    if (Test-Path $ClaudePath2) {
        Start-Process $ClaudePath2
        Write-Host "✓ Claude Desktop 已重新启动" -ForegroundColor Green
    } else {
        Write-Host "⚠ 未找到 Claude Desktop 可执行文件，请手动启动" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== 配置完成 ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "📋 使用说明：" -ForegroundColor White
Write-Host "  1. 截图或复制一张图片到剪贴板 (Ctrl+C)" -ForegroundColor Gray
Write-Host "  2. 在 Claude 中按 Ctrl+V 粘贴图片" -ForegroundColor Gray
Write-Host "  3. 我会自动调用识图工具分析图片内容" -ForegroundColor Gray
Write-Host ""
pause
````

### setup.bat

````javascript
@echo off
chcp 65001 >nul
title mcp-vision-web-bridge 一键安装

echo ========================================
echo   mcp-vision-web-bridge 一键配置脚本
echo ========================================
echo.

:: 检查 Node.js
where node >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 Node.js！请先安装 Node.js ^(v20+^)
    echo        下载地址: https://nodejs.org
    pause
    exit /b 1
)
echo [✓] Node.js 已安装
node -v
echo.

:: 进入脚本所在目录
cd /d "%~dp0"

:: 安装依赖
echo [1/2] 安装 Node.js 依赖...
call npm install --no-audit --no-fund
if %ERRORLEVEL% neq 0 (
    echo [错误] npm install 失败！
    pause
    exit /b 1
)
echo [✓] 依赖安装完成
echo.

:: 获取完整路径
set "SERVER_PATH=%~dp0src\server.mjs"
set "ENV_PATH=%~dp0.env"

echo [2/2] 配置 Claude Desktop...
set "CONFIG_DIR=%APPDATA%\Claude"
set "CONFIG_FILE=%CONFIG_DIR%\claude_desktop_config.json"

if not exist "%CONFIG_DIR%" (
    mkdir "%CONFIG_DIR%"
)

:: 生成 JSON 配置（用 PowerShell 处理）
set "JSON_OUT=%TEMP%\claude_config.json"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$cfg = @{}; " ^
    "if (Test-Path '%CONFIG_FILE%') { " ^
    "    try { $cfg = Get-Content '%CONFIG_FILE%' -Raw -Encoding UTF8 | ConvertFrom-Json; } catch {} " ^
    "}; " ^
    "if (-not $cfg.mcpServers) { $cfg = $cfg | Add-Member -NotePropertyName 'mcpServers' -NotePropertyValue @{} -Force -PassThru; }; " ^
    "$cfg.mcpServers | Add-Member -NotePropertyName 'vision-web-bridge' -NotePropertyValue @{ " ^
    "    command = 'node'; " ^
    "    args = @('--env-file-if-exists=%ENV_PATH:\=\\%', '%SERVER_PATH:\=\\%') " ^
    "} -Force; " ^
    "$json = $cfg | ConvertTo-Json -Depth 10; " ^
    "$utf8 = New-Object System.Text.UTF8Encoding $false; " ^
    "[System.IO.File]::WriteAllText('%CONFIG_FILE%', $json, $utf8); " ^
    "Write-Host '[✓] Claude Desktop 配置已更新'"
echo.

:: 尝试重启 Claude
echo [*] 正在重启 Claude Desktop...
taskkill /f /im "Claude.exe" >nul 2>&1
taskkill /f /im "Claude-3p.exe" >nul 2>&1
timeout /t 3 /nobreak >nul

if exist "%LOCALAPPDATA%\Claude-3p\Claude-3p.exe" (
    start "" "%LOCALAPPDATA%\Claude-3p\Claude-3p.exe"
) else if exist "%LOCALAPPDATA%\Claude\Claude.exe" (
    start "" "%LOCALAPPDATA%\Claude\Claude.exe"
) else (
    echo [⚠] 未找到 Claude Desktop，请手动启动
)
echo [✓] 启动完成
echo.

echo ========================================
echo   配置完成！
echo ========================================
echo.
echo 使用方法：
echo   1. 截图或复制图片到剪贴板 ^(Ctrl+C^)
echo   2. 在 Claude 中 Ctrl+V 粘贴图片
echo   3. Claude 会自动调用识图工具分析
echo.
pause
````

### Windows环境说明.md

````javascript
# Windows 环境使用说明：mcp-vision-web-bridge

## 一、这个工具需要什么环境？

mcp-vision-web-bridge 是一个 **Node.js** 项目（不是 Python），安装环境非常简单：

- **Node.js** >= 20
- **npm**（安装 Node.js 时会自动带上）
- **不需要 Python、不需要虚拟环境（venv）**

## 二、Windows 安装步骤

```bash
# 1. 去 https://nodejs.org 下载安装 Node.js（LTS 版本即可）

# 2. 打开终端（CMD 或 PowerShell），验证安装
node -v    # 应显示 v20.x.x 或更高
npm -v     # 应显示 10.x.x 或更高

# 3. 进入项目目录，安装依赖
cd mcp-vision-web-bridge
npm install

# 4. 复制环境变量文件（Windows 用复制改名）
cp .env.example .env

# 5. 编辑 .env，填上你的模型地址和 API Key
```

## 三、Claude Desktop 配置

在 `claude_desktop_config.json` 中加入（路径改成你实际的绝对路径）：

```json
{
  "mcpServers": {
    "vision-web-bridge": {
      "command": "node",
      "args": [
        "--env-file-if-exists=D:\\你的路径\\mcp-vision-web-bridge\\.env",
        "D:\\你的路径\\mcp-vision-web-bridge\\src\\server.mjs"
      ]
    }
  }
}
```

⚠️ **注意**：Windows 上必须用**完整绝对路径**，不支持 `%USERPROFILE%` 这类环境变量。

## 四、关于 Windows 家庭版的特别说明

如果你是 **Windows 家庭版** 用户，可能会遇到两种情况：

### 情况 1：只配置 MCP 工具（没问题）

只把 mcp-vision-web-bridge 配到 Claude Desktop 里用——**Windows 家庭版完全支持**。只要 Node.js 装好就能跑，不需要任何虚拟机或沙箱。

### 情况 2：想用 Claude Cowork（有限制）

Claude Cowork 的沙箱环境依赖 **Hyper-V**（Windows 的虚拟化技术）。但 **Windows 家庭版没有 Hyper-V**，所以 Cowork 的沙箱 Linux 环境可能无法启动。

| 使用场景 | Windows 家庭版 | Windows 专业版/企业版 |
|---------|---------------|---------------------|
| Claude Desktop + MCP 工具 | ✅ 可用 | ✅ 可用 |
| Claude Cowork（沙箱模式） | ❌ 缺少 Hyper-V，可能无法运行 | ✅ 完整支持 |
| Claude Code（终端模式） | ✅ 通过 WSL2 可用 | ✅ 通过 WSL2 可用 |

### 解决方案

- **方案一**：先用 Claude Desktop 的普通模式配合 MCP 工具使用，不开启 Cowork
- **方案二**：升级到 **Windows 专业版**（有 Hyper-V）
- **方案三**：安装 **VirtualBox / VMware** 虚拟机，在虚拟机里装 Linux 跑 Cowork
- **方案四**：如果只是要用 Claude Code，通过 **WSL2** 即可

## 五、常见问题排查

**问：提示"需要虚拟环境（venv）"怎么办？**

答：这个工具是 Node.js 项目，不需要任何虚拟环境。如果看到这个提示，可能有两个原因：
1. 你电脑上其他 Python MCP 工具报的错，和本工具无关
2. 你尝试启动 Claude Cowork 时，Windows 提示缺少虚拟化支持（见上面第四点）

**问：Windows 上配置后 MCP 工具没出现？**

答：检查以下几点：
- `claude_desktop_config.json` 是否用了**无 BOM 的 UTF-8 编码**（PowerShell 保存时默认带 BOM，会导致 Claude 忽略文件）
- 路径是否用的**完整绝对路径**（不要用 `%USERPROFILE%`）
- 配置修改后，必须从**系统托盘完全退出 Claude** 再重新打开
- 查看日志：`%APPDATA%\Claude\logs\`
````

### claude_desktop_config_ready.json

````javascript
{
  "mcpServers": {
    "vision-web-bridge": {
      "command": "node",
      "args": [
        "--env-file-if-exists=D:\\path\\to\\mcp-vision-web-bridge\\.env",
        "D:\\path\\to\\mcp-vision-web-bridge\\src\\server.mjs"
      ]
    }
  }
}
````

## 四、完成后必须执行的验证命令

```bash
npm install
npm test
npm run check:secrets
```

- `npm test` 必须全部通过。
- `npm run check:secrets` 必须无输出且退出码为 0。
- 不要手动编写 `package-lock.json`，让 `npm install` 自动生成。

## 五、配置与使用

1. 复制 `.env.example` 为 `.env`，填写你自己的 `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME`。
2. Windows 下运行 `setup.ps1` 或 `setup.bat` 自动写 Claude Desktop 配置；也可以手动复制 `claude_desktop_config_ready.json` 内容。
3. 必须使用完整绝对路径，且配置 JSON 保存为无 BOM 的 UTF-8。
4. 修改配置后从系统托盘完全退出并重启 Claude 客户端。
5. 用 `/mcp`（Claude Code）或 MCP 面板确认 `vision-web-bridge` 已连接。
6. 工具使用示例：
   - `read_image_with_model` + `use_latest_upload=true`
   - `read_image_with_model` + `use_clipboard=true`（需 `ALLOW_CLIPBOARD_IMAGES=true`）
   - `read_links_with_model` 传入任意网页 URL

## 六、绝对禁止

- 不要在生成的文件中写入真实 API Key、token、Cookie、个人截图、个人绝对路径或机器专用地址。
- 不要提交 `.env`、`node_modules`、`work`、日志或打包产物。
- 不要改变默认安全开关（本地路径、剪贴板、私网 URL、Jina Reader 必须默认关闭）。
