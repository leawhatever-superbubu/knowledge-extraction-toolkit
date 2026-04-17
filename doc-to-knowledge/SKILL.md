---
name: doc-to-knowledge
description: Reads Feishu docx transcripts (from video courses), extracts structured knowledge points via AI (Gemini/OpenAI) targeting SMB merchants, and writes them into Feishu Bitable for human review. Pipeline Stage 2.
version: 1.0.0
author: OpenClaw Studio
---

## Overview

Pipeline 第 2 阶段：读取飞书 docx 文档（视频课程转录稿），以**中小客 (SMB)** 视角，用 AI 从中拆解出独立、可发布的知识点，将结构化结果写入飞书多维表格，供人工审核后流入下游。

```
video-to-feishu-doc  →  [本 Skill]  →  knowledge-to-social-copy  →  xhs-card-maker
   (视频→转录稿)      (转录→知识点)        (知识点→文案)              (文案→卡片PNG)
```

## When To Use

- 有新的视频课程转录稿（飞书 docx 文档）需要提取知识点
- 需要批量从多篇转录稿中提取结构化知识点到飞书多维表格
- 从 Obsidian Markdown 笔记（Playbook 卡片）中提取操作级知识点
- 需要补充知识点表与需求地图表的关联

## Prerequisites

1. 飞书 docx 文档已就绪（由 `video-to-feishu-doc` 生成，或手动上传）
2. 飞书自建应用凭证已配置（参考 `references/SETUP_GUIDE.md`）
3. AI 模型 API 可访问（支持 OpenAI 兼容接口或 Gemini 原生接口）
4. 目标飞书多维表格已创建，字段结构与 `SKILL_SPEC.md §4.1` 一致

## Quick Workflow

### 1. 配置环境

```bash
# 复制配置模板
cp .env.example .env
cp config.example.json config.json

# 编辑 .env，填入你的飞书应用凭证和 AI API Key
# 编辑 config.json，填入你的多维表格 app_token 和 table_id
```

### 2. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 3. 提取知识点

```bash
# 从单篇飞书文档提取知识点
python3 scripts/pipeline.py --doc-token YOUR_DOC_TOKEN

# 从飞书文档 URL 提取
python3 scripts/pipeline.py --doc-url "https://your-domain.feishu.cn/docx/YOUR_TOKEN"

# 批量处理多个文档
python3 scripts/pipeline.py --doc-token TOKEN1 TOKEN2 TOKEN3

# 预览模式（只提取不写入飞书）
python3 scripts/pipeline.py --doc-token YOUR_TOKEN --dry-run

# 只导出 JSON 不写飞书
python3 scripts/pipeline.py --doc-token YOUR_TOKEN --json-only

# 从本地 .docx 文件提取
python3 scripts/pipeline.py --local-docx path/to/file.docx

# 从 Obsidian Markdown 笔记提取（Playbook 模式）
python3 scripts/pipeline.py --local-md path/to/playbook/
```

## Resources

### `scripts/pipeline.py`

主入口脚本。串联：读取飞书文档 → 按章节切分 → 逐章 AI 提取知识点 → 全局去重编号 → 写入飞书多维表格 → 本地 JSON 备份。

### `scripts/feishu_client.py`

统一的飞书 API 客户端，合并三项核心能力：
- **读取 docx 文档 block**（`get_document_blocks()`）
- **读写多维表格 Bitable**（`search_records()`, `create_record()`, `update_record()`）
- **下载飞书云盘文件**（`download_file()`）

### `scripts/knowledge_extractor.py`

AI 知识点提取核心。包含：
- `KnowledgeItem` dataclass（知识点数据结构）
- System Prompt（中小客视角内容策略师人设）
- 逐章提取 + 全局后处理的两阶段 Prompt 策略
- Playbook 模式（SMB 操作级卡片提取）
- JSON 解析容错和自动修复逻辑

### `scripts/bitable_writer.py`

飞书多维表格写入模块。支持幂等 upsert（按知识点ID判重），自动分配序号。

### `scripts/doc_reader.py`

文档解析层。支持三种文档来源：
- 飞书在线文档（blocks API）
- 飞书云盘下载的 .docx（python-docx 本地解析）
- Obsidian Markdown 文件

### `scripts/gemini_client.py`

Gemini 原生 API 客户端，模拟 OpenAI SDK 接口，支持代理网关模式。

### `config.example.json`

配置模板：飞书表格 ID、提取参数、AI 模型配置等。**使用前需复制为 `config.json` 并填入实际值。**

### `SKILL_SPEC.md`

详细设计规范文档（字段定义、Prompt 策略、流程说明、约束条件、验收标准）。

## Output Expectations

- 每条知识点写入飞书多维表格的一行（13 个字段，初始状态「待审核」）
- 本地 JSON 备份到 `output/` 目录
- 知识点格式：`{doc_title}_K{序号}`，如 `第一课_K03`
- 知识点类型：概念解释 / 操作方法 / 避坑提醒 / 数据洞察 / 行业趋势 / 工具技巧
- 痛点标签从 8 个闭集选项中选择
- 人工审核通过后，下游 `knowledge-to-social-copy` 可读取

## License

MIT — 自由使用、修改和分发。
