<p align="center">
  <img src="docs/console.png" alt="本机控制台：提交公开链接并查看整理结果" width="900" />
</p>

<p align="center">
  <img src="docs/feishu-doc.png" alt="飞书文档中的分享式提纯稿" width="900" />
</p>

# 小 D · LangGraph

飞书入口的音视频转录整理 Agent。用 LangChain / LangGraph 编排，用 Vue + FastAPI 做本机控制台，用 LangSmith 按节点打点。

发给控制台或飞书机器人一条公开链接：小宇宙 / YouTube / B 站 / 本地音频 → 分享式提纯稿 → 飞书文档，并把权限授给发信人。

整理稿不是摘要。字幕优先，没有字幕再用本机 `faster-whisper`。

## 准备

在仓库根目录操作：

1. 复制 `.env.example` 为 `.env`，填 LangSmith、DeepSeek、飞书应用。
2. `uv sync --extra dev` 会装上 **yt-dlp** 和 **faster-whisper**。
3. 本机安装 [ffmpeg](https://ffmpeg.org/)，或把可执行文件路径写到 `.env` 的 `FFMPEG_BIN`。
4. `uv run xiaod doctor` 确认 yt-dlp、ffmpeg、faster-whisper 都在。
5. 飞书企业自建应用：开通事件订阅 WebSocket，订阅 `im.message.receive_v1`，开通云文档、协作者、发消息权限，并发布。

```bash
uv sync --extra dev
uv run xiaod doctor
```

Windows 复制环境文件：`copy .env.example .env`。macOS / Linux：`cp .env.example .env`。

## 命令

在仓库根目录执行：

```bash
uv run xiaod doctor         # 检查 yt-dlp / ffmpeg / faster-whisper
uv run xiaod hello          # 写一条 LangSmith hello trace
uv run xiaod eval           # 本地规则评估（分类 + 文稿门禁）
uv run xiaod run "请转录 https://www.xiaoyuzhoufm.com/episode/..."
uv run xiaod web            # FastAPI 控制台，默认 http://127.0.0.1:8765
uv run xiaod bot            # 飞书长连接，本机无需公网
```

前端开发页：

```bash
cd web
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。开发时 Vite 会把 `/api` 转到 FastAPI。先要另开一个终端跑 `uv run xiaod web`。

打包给 FastAPI 直接托管：

```bash
cd web
npm run build
```

回到仓库根目录后再执行 `uv run xiaod web`。

## 验收

能收链接、能拿到音频或字幕、能转写、是提纯稿不是要点、能建飞书文档、能授权给本人、链接可打开。

小红书 / 抖音 / 公众号 / 视频号 / 飞书妙记本期不处理。

## 监测

`LANGSMITH_TRACING=true` 且填了 `LANGSMITH_API_KEY` 后，整图自动进项目 `xiaod`。yt-dlp / whisper / 飞书调用带 `@traceable`。密钥会脱敏。

## 项目结构

### 一句话概述

飞书入口的音视频转录整理 Agent：发给它一条公开链接（小宇宙 / YouTube / B 站 / 本地音频），它自动取字幕或做语音识别，整理成「分享式提纯稿」，再创建飞书文档并授权给发信人。编排用 LangChain / LangGraph，控制台用 Vue + FastAPI，观测用 LangSmith。

### 技术栈

- 语言：Python ≥3.12（后端）+ JavaScript / Vue 3（前端）
- 编排：LangGraph + LangChain + langchain-openai（LLM 走 DeepSeek）
- 后端：FastAPI + Uvicorn，SQLite 存图检查点（langgraph-checkpoint-sqlite）
- 音视频：yt-dlp（下载）+ ffmpeg（转码）+ faster-whisper（本机 ASR）
- 飞书：lark-oapi（WebSocket 长连接机器人 + 云文档）
- 构建 / 依赖：uv（`pyproject.toml` + `uv.lock`）、Vite（前端）
- 测试：pytest

### 一级目录

| 条目 | 类型 | 作用 |
| --- | --- | --- |
| `src/` | 目录 | 核心源码，Python 包 `xiaod` |
| `web/` | 目录 | Vue 3 + Vite 本机控制台（`App.vue` / `main.js` / `vite.config.js`；`dist/` 为打包产物） |
| `tests/` | 目录 | pytest：分类、清洗、媒体、机器人、Web、评估等 |
| `docs/` | 目录 | 岗位卡、工作流、流程图、Profile、测试记录、使用说明书和截图 |
| `data/` | 目录 | 运行时数据（不入库）：SQLite 检查点、任务 JSON、下载的音视频与分段 |
| `README.md` | 文件 | 项目总述、准备与命令 |
| `pyproject.toml` / `uv.lock` | 文件 | Python 包元数据、依赖与入口 `xiaod = xiaod.cli:main` |
| `.env.example` | 文件 | 环境配置模板（本地复制为 `.env` 后填密钥） |
| `.python-version` | 文件 | 固定 Python 版本 |

`.venv/`、`web/node_modules/`、`.pytest_cache/` 等是本机依赖或缓存，不进仓库。

### 核心目录

`src/xiaod/` 是唯一承载实现的包：Agent 图、节点、工具、机器人、Web 服务和 CLI 都在这里。`web/` 是展示层，`tests/` 是验证层。

### `src/xiaod/` 二级目录

| 条目 | 作用 |
| --- | --- |
| `graph.py` | 父图路由：classify → ack → xiaod 子图 / human / status；管理 SQLite 检查点与线程状态读取 |
| `graphs/xiaod.py` | 小 D 子图：fetch_source → transcribe → purify → deliver；条件边处理失败，有字幕则跳过转写 |
| `nodes/` | 节点实现：`classify.py`（来源 / 意图）、`xiaod_nodes.py`（取源 / 转写 / 提纯 / 交付）、`clean.py`（清洗与 QA）、`reply.py`（应答、状态、人工兜底） |
| `tools/` | 底层能力：`media.py`（yt-dlp / ffmpeg / whisper）、`lark.py`（飞书文档与授权）、`llm.py`（DeepSeek 提纯）、`catalog.py`（工具注册） |
| `bot/` | 飞书机器人：`feishu_ws.py`（WebSocket、进度回报节流）、`jobs.py`（会话任务记忆） |
| `evals/` | 本地规则评估：`dataset.py`（样例）、`evaluators.py`（分类 + 文稿门禁） |
| `prompts/purify.md` | 提纯稿提示词 |
| `webapp.py` | FastAPI 控制台：任务 CRUD、进度回调、托管打包后的前端 |
| `cli.py` | 命令行入口：`doctor` / `hello` / `eval` / `run` / `web` / `bot` |
| `state.py` | `JobState` 与空状态构造 |
| `settings.py` | 读取 `.env`、密钥脱敏、工具栈开关 |
| `messages.py` / `progress.py` / `tracing.py` | 文案常量、进度上报、LangSmith 打点与脱敏 |
