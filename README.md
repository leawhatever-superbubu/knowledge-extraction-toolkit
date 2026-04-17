# Knowledge Extraction Toolkit

> 从多模态内容（视频/音频/图片/PDF）自动提取结构化知识点的 AI 工具集

## 项目说明

这是一套完整的知识库构建工具，能够将课程内容（视频、音频、图片、PDF）自动拆解成独立的、可检索的知识点。

**实际案例参考：** [《把 40 节课变成 700 个知识点：我是怎么用 AI 做知识库的》](你的文章链接)

## 工具列表

### 1. doc-to-knowledge
从音频/视频课程转录稿自动提取结构化知识点

- 支持：飞书文档、本地 .docx、Markdown 笔记
- 输出：本地 JSON、飞书多维表格、腾讯文档
- AI 模型：OpenAI / Gemini / Claude

**[查看详细说明 →](./doc-to-knowledge/README_PUBLIC.md)**

### 2. image-to-knowledge
从图片和 PDF 文件自动提取结构化知识点

- 支持：PPT 截图、架构图、操作步骤图、PDF 文件
- 输出：本地 Markdown / JSON、飞书多维表格
- AI 模型：Gemini Vision / GPT-4 Vision

**[查看详细说明 →](./image-to-knowledge/README_PUBLIC.md)**

## 快速开始

```bash
# 克隆项目
git clone https://github.com/leawhatever-superbubu/knowledge-extraction-toolkit.git
cd knowledge-extraction-toolkit

# 选择工具
cd doc-to-knowledge  # 或 cd image-to-knowledge

# 安装依赖
pip3 install -r requirements.txt

# 配置环境
cp .env.example .env
# 编辑 .env，填入 AI API Key

# 运行示例
# doc-to-knowledge:
python3 scripts/pipeline.py --local-docx demo.docx

# image-to-knowledge:
python3 scripts/pipeline.py --folder /path/to/images/
```

## 适用场景

- 📚 **在线教育**：视频课程 → 知识库
- 📖 **企业培训**：内训资料 → 可检索知识点
- 📊 **技术文档**：架构图/截图 → 结构化说明
- 🎓 **学习笔记**：课堂录音/PPT → 复习材料

## 为什么要用这个工具？

**传统方式：**
- 让用户翻 40 节课、几十小时的视频找答案 → 大概率放弃
- 让用户在几十张 PPT 截图里找操作步骤 → 效率低

**这个工具：**
- 把课程拆成 700+ 个独立知识点 → 用户搜索"插件配置"，3 秒定位答案
- 把图片内容结构化 → 快速检索、精准定位

## 成本参考（40 节课示例）

| 环节 | 成本 |
|------|------|
| 音频转文本（如需） | ~200 元 |
| AI 拆解知识点 | ~500 元 |
| 人工审核时间 | ~20 小时 |

**vs 纯人工拆解：** 100+ 小时，效率提升 5 倍

## 技术栈

- **AI 模型**：OpenAI GPT-4 / Gemini / Claude（可切换）
- **输出目标**：本地 JSON/Markdown、飞书多维表格、腾讯文档
- **编程语言**：Python 3.9+

## License

MIT — 自由使用、修改和分发

## 作者

OpenClaw Studio

如有问题或建议，欢迎提 Issue 或 PR！

---

**相关文章：** [《把 40 节课变成 700 个知识点：我是怎么用 AI 做知识库的》](你的文章链接)
