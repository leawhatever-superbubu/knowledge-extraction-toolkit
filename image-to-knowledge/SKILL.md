---
name: image-to-knowledge
description: Analyzes case study images (marketing posters, data reports, chat screenshots, PPT slides) via Vision AI, extracts structured knowledge points targeting SMB merchants, and writes them into Feishu Bitable. Pipeline Stage 2 parallel branch.
---

## Overview

使用 Vision AI 分析**图片和 PDF 文件**（营销海报、数据报表截图、聊天记录、PPT 截图等），以 **中小客 (SMB)** 视角从中提取结构化知识点。

支持输出到**本地 Markdown/JSON**（可直接粘贴到腾讯文档），也保留飞书多维表格写入能力。

```
输入来源                    处理流程                      输出目标
───────────               ──────────                   ──────────
本地图片文件夹  ─┐
手动指定图片    ─┤         Vision AI 分析               本地 Markdown ←默认
PDF 文件       ─┤ ──→  → 知识点提取 ──→ 去重编号 ──→  本地 JSON
飞书云盘图片    ─┘         → 后处理质检                  飞书多维表格(可选)
```

## When To Use

- 有案例图片（营销海报、数据报表截图、聊天记录、PPT 截图等）需要提取知识点
- 有 **PDF 文件**（演讲稿、案例集、数据报告等）需要逐页分析提取知识点
- 需要从本地文件夹批量处理案例图片/PDF
- 手动提供单张图片或 PDF 路径给 AI 分析
- 需要将提取结果输出为 Markdown（方便粘贴到腾讯文档）或 JSON

## Prerequisites

1. 图片/PDF 素材已就绪（本地文件夹 / 手动指定路径 / 飞书云盘）
2. AI 代理网关可访问（`http://43.162.95.137:5050`），支持 Gemini Vision
3. 已安装依赖：`pip3 install -r requirements.txt`
4. （可选）飞书自建应用凭证 — 仅在选择飞书输出或从飞书下载图片时需要

## Quick Workflow

### 0. 启动前参数确认（Agent 必须执行）

在执行任何脚本之前，Agent **必须**向用户确认以下参数：

1. **输入来源**：本地文件夹路径 / 手动指定图片 / PDF 文件 / 飞书云盘链接
2. **案例来源场景（`--scene`）**：本批次素材来自什么场景？
   - 默认值：`微信小店商家使用小店广告（腾讯广告-小店版）`
   - 常用选项：`朋友圈广告商家` / `搜一搜广告` / `视频号直播投流` / `腾讯广告投放端（通用）`
   - 用户也可自定义输入任意场景描述
   - 如果用户说"不需要"或"通用"，则不传 `--scene`
3. **输出格式（`--output-format`）**：
   - `markdown`（默认）— 生成结构化 Markdown 文档，可直接粘贴到腾讯文档
   - `json` — 生成 JSON 文件
   - `both` — 同时生成 Markdown 和 JSON
   - `feishu` — 写入飞书多维表格（需配置凭证）
4. **运行模式**：
   - 正式输出（默认）
   - `--dry-run` 预览模式（只提取不输出）

> Agent 必须在收到全部确认后才组装命令执行。

### 1. 配置环境变量

```bash
# .env 文件（最小配置，只需 AI Key）
OPENAI_API_KEY=sk-xxxxx

# 如果需要飞书功能，补充以下：
# FEISHU_APP_ID=cli_xxxxx
# FEISHU_APP_SECRET=xxxxx
```

### 2. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 3. 运行示例

```bash
# 从本地文件夹批量处理（图片 + PDF 混合扫描）
python3 scripts/pipeline.py --folder /path/to/files/

# 处理 PDF 文件（每页渲染为图片后分析）
python3 scripts/pipeline.py --pdf report.pdf slides.pdf

# 处理指定图片
python3 scripts/pipeline.py --images img1.jpg img2.png

# 指定场景 + JSON 输出
python3 scripts/pipeline.py --folder /path/ --scene "微信小店商家使用小店广告" --output-format json

# 同时输出 Markdown 和 JSON
python3 scripts/pipeline.py --images demo.png --output-format both

# 预览模式
python3 scripts/pipeline.py --folder /path/ --dry-run

# PDF 高分辨率渲染
python3 scripts/pipeline.py --pdf report.pdf --pdf-dpi 300

# 写入飞书多维表格（需配置凭证）
python3 scripts/pipeline.py --folder /path/ --output-format feishu
```

### 4. 输出说明

**Markdown 输出**（默认）:
- 文件名：`{批次名}_知识点.md`
- 包含：概览统计表 + 目录 + 逐条知识点详情
- 可直接粘贴到腾讯文档或 Obsidian

**JSON 输出**:
- 文件名：`{批次名}_知识点.json`
- 结构化数据，含中文字段名

## Resources

### `scripts/pipeline.py`
主入口脚本。串联：扫描输入 → 预处理 → Vision AI 分析 → 知识点提取 → 全局去重编号 → 输出。

### `scripts/pdf_loader.py`
PDF 文件加载器。使用 PyMuPDF 将 PDF 每页渲染为 PNG 图片，接入处理流程。

### `scripts/image_loader.py`
图片加载器。支持：本地文件夹扫描、手动指定路径、飞书云盘下载。

### `scripts/image_preprocessor.py`
图片预处理：大图压缩、EXIF 方向修正、格式统一、base64 编码。

### `scripts/vision_analyzer.py`
Vision AI 分析核心。使用 Gemini Vision 多模态能力将图片转为结构化文本描述。

### `scripts/knowledge_extractor.py`
AI 知识点提取核心。含图片案例专用 Prompt、JSON 解析容错、自动修复。

### `scripts/local_writer.py`
本地输出模块。支持 Markdown 和 JSON 两种格式导出。

### `scripts/gemini_client.py`
Gemini API 客户端，支持纯文本和 Vision 多模态调用。

### `scripts/bitable_writer.py`（可选）
飞书多维表格写入模块，仅在选择 `--output-format feishu` 时使用。

### `scripts/feishu_client.py`（可选）
飞书 API 客户端，仅在飞书相关功能时需要。

### `config.json`
运行时配置：AI 模型、Vision 参数、知识点提取参数、PDF 参数等。

## Output Expectations

- **Markdown**：结构清晰的知识点文档，含概览、目录、逐条详情，适合直接阅读或粘贴到腾讯文档
- **JSON**：结构化数据文件，每个知识点含 10 个字段（知识点ID、标题、类型、核心内容、关键要点、适用场景、痛点标签、难度等级、原文摘录、来源）
- **飞书**（可选）：写入多维表格，与 doc-to-knowledge 完全兼容
- 知识点 ID 格式：`IMG_{batch_name}_K{序号}`
- 输出格式与 doc-to-knowledge 完全兼容，下游 `knowledge-to-social-copy` 可直接读取
