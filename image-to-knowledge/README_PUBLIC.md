# image-to-knowledge

> 从图片和 PDF 文件自动提取结构化知识点

## 这是什么？

这是一个基于 Vision AI 的知识库构建工具，能够：
- 分析图片（PPT 截图、数据报表、操作步骤截图、架构图等）
- 分析 PDF 文件（逐页渲染为图片后处理）
- 用 AI 自动提取结构化知识点
- 输出到本地 Markdown/JSON、腾讯文档或飞书多维表格

**适用场景：** 你有一堆 PPT 截图、技术架构图、操作步骤示意图，想快速转成可检索的知识点，而不是让用户在几十张图片里翻找。

## 实际案例参考

本工具的方法论和使用说明，可参考这篇文章：
[《把 40 节课变成 700 个知识点：我是怎么用 AI 做知识库的》](你的文章链接)

文章用"OpenClaw 学习知识库"作为演示案例（实际项目已脱敏），完整展示了从多模态素材到知识库的原子化拆解过程。

## 快速开始

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 2. 配置环境

```bash
# 创建 .env 文件，填入 AI API Key（必需）
OPENAI_API_KEY=sk-xxxxx

# 如果需要飞书功能，补充：
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx
```

### 3. 提取知识点

```bash
# 从本地文件夹批量处理（图片 + PDF 混合扫描）
python3 scripts/pipeline.py --folder /path/to/files/

# 处理 PDF 文件（每页渲染为图片后分析）
python3 scripts/pipeline.py --pdf report.pdf slides.pdf

# 处理指定图片
python3 scripts/pipeline.py --images img1.jpg img2.png img3.png

# 输出为 Markdown（默认，可直接粘贴到腾讯文档）
python3 scripts/pipeline.py --folder /path/ --output-format markdown

# 输出为 JSON
python3 scripts/pipeline.py --folder /path/ --output-format json

# 同时输出 Markdown 和 JSON
python3 scripts/pipeline.py --images demo.png --output-format both

# 预览模式（不输出文件）
python3 scripts/pipeline.py --folder /path/ --dry-run

# PDF 高分辨率渲染
python3 scripts/pipeline.py --pdf report.pdf --pdf-dpi 300
```

### 4. 查看结果

- **Markdown 输出**：`output/{批次名}_知识点.md`（可直接粘贴到腾讯文档）
- **JSON 输出**：`output/{批次名}_知识点.json`
- **飞书多维表格**：如果配置了凭证且指定 `--output-format feishu`

## 输出示例

### Markdown 格式
```markdown
# 知识点提取结果

## 概览
- 总知识点数：15
- 来源文件数：3
- 提取时间：2026-04-17 10:30

## 目录
1. K01 - OpenClaw 插件目录结构规范
2. K02 - Skill.md 编写要点
...

## 知识点详情

### K01 - OpenClaw 插件目录结构规范
**类型**：操作方法  
**难度**：入门  
**核心内容**：...  
**关键要点**：...  
**适用场景**：...
```

### JSON 格式
```json
[
  {
    "知识点ID": "IMG_批次名_K01",
    "标题": "OpenClaw 插件目录结构规范",
    "类型": "操作方法",
    "核心内容": "...",
    "关键要点": ["要点1", "要点2", "要点3"],
    "适用场景": "新手创建插件时",
    "难度等级": "入门",
    "原文摘录": "来自图片的关键文字",
    "来源": "demo.png"
  }
]
```

## 技术细节

### 支持的输入格式
- 图片：JPG、PNG、WebP、HEIC
- PDF：自动逐页渲染为图片后分析
- 来源：本地文件夹、手动指定路径、飞书云盘（可选）

### AI 模型
- 默认：Gemini Vision（多模态能力强）
- 可切换：GPT-4 Vision、Claude Vision（需兼容 OpenAI API）

### 输出目标
- 本地 Markdown（推荐，可直接粘贴到腾讯文档）
- 本地 JSON
- 飞书多维表格（可选）

## 为什么要用这个工具？

**传统方式：** 让用户在几十张 PPT 截图、架构图里翻找 → 效率低、容易漏掉关键信息

**这个工具：** 把图片内容结构化 → 用户搜索"插件配置流程"，直接定位到对应截图的知识点

## 常见问题

### Q: Vision AI 能识别什么？
A: 文字（OCR）、图表、流程图、代码截图、UI 界面、架构图等。复杂图片会先让 AI 描述，再提取知识点。

### Q: PDF 支持多页吗？
A: 支持！工具会自动把每页渲染成图片，逐页分析提取知识点。

### Q: 我想用腾讯文档，不想用飞书可以吗？
A: 可以！用 `--output-format markdown`，然后直接粘贴到腾讯文档即可。

### Q: 图片很多时会不会很慢？
A: 会有点慢（Vision AI 比纯文本慢），但可以批量并发处理。建议先用几张图测试，确认效果后再全量跑。

### Q: 能自定义提取的内容吗？
A: 可以，编辑 `scripts/knowledge_extractor.py` 里的 Prompt 即可。

## 成本估算

| 环节 | 成本（100 张图片） |
|------|-------------------|
| Vision AI 分析 | ~200 元（Gemini Vision） |
| 知识点提取 | ~300 元（GPT-4） |
| 人工审核时间 | ~10 小时 |

**vs 纯人工提取：** 50+ 小时，效率提升 5 倍

## 配套工具

- `doc-to-knowledge`：从音频/视频转录稿提取知识点
- 可以组合使用：视频课程（用 doc-to-knowledge） + PPT 截图（用 image-to-knowledge） = 完整知识库

## 进阶用法

### 自定义场景标签
通过 `--scene` 参数指定素材来源场景，让 AI 提取时更有针对性：

```bash
python3 scripts/pipeline.py --folder /path/ --scene "OpenClaw 插件开发教程"
```

### 调整提取策略
编辑 `scripts/knowledge_extractor.py` 里的 System Prompt，改变 AI 提取的风格和粒度。

### PDF 高清渲染
默认 DPI 是 150，如果 PDF 里文字很小，可以提高到 300：

```bash
python3 scripts/pipeline.py --pdf slides.pdf --pdf-dpi 300
```

## License

MIT — 自由使用、修改和分发

## 作者

OpenClaw Studio

如有问题或建议，欢迎提 Issue 或 PR！
