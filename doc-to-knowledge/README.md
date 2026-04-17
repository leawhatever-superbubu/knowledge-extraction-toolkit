# doc-to-knowledge

> 从音频/视频课程转录稿自动提取结构化知识点

## 这是什么？

这是一个 AI 驱动的知识库构建工具，能够：
- 读取视频课程的转录文本（支持飞书文档、本地 .docx、Markdown 笔记）
- 用 AI 自动拆解成独立的、可检索的知识点
- 输出到飞书多维表格、本地 JSON 或腾讯文档

**适用场景：** 你有一套完整的视频课程（比如 40 节 OpenClaw 教程），想快速转成知识库，让用户能快速找到"如何配置企业微信插件"这样的具体问题答案。

## 实际案例参考

本工具的方法论和使用说明，可参考这篇文章：
[《把 40 节课变成 700 个知识点：我是怎么用 AI 做知识库的》](https://mp.weixin.qq.com/s/oGPJj5wCX8TeLXN-Bro81g)

文章用"OpenClaw 学习知识库"作为演示案例（实际项目已脱敏），完整展示了从课程到知识库的原子化拆解过程。

## 快速开始

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 2. 配置环境

```bash
# 复制配置模板
cp .env.example .env
cp config.example.json config.json

# 编辑 .env，填入 AI API Key（必需）
OPENAI_API_KEY=sk-xxxxx

# 如果需要飞书功能，补充：
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx
```

### 3. 提取知识点

```bash
# 从本地 .docx 文件提取（最简单）
python3 scripts/pipeline.py --local-docx "第一课-转录稿.docx"

# 从飞书文档提取
python3 scripts/pipeline.py --doc-token YOUR_DOC_TOKEN

# 批量处理多个文档
python3 scripts/pipeline.py --doc-token TOKEN1 TOKEN2 TOKEN3

# 只导出 JSON 不写飞书
python3 scripts/pipeline.py --local-docx demo.docx --json-only

# 预览模式（不输出文件）
python3 scripts/pipeline.py --local-docx demo.docx --dry-run
```

### 4. 查看结果

- **本地 JSON**：`output/` 目录下
- **飞书多维表格**：如果配置了凭证，会自动写入

## 输出示例

每个知识点包含：
- **知识点ID**：如 `第一课_K03`
- **标题**：10 字以内的简洁描述
- **类型**：概念解释 / 操作方法 / 避坑提醒 / 数据洞察 / 行业趋势 / 工具技巧
- **核心内容**：200-500 字的独立说明
- **关键要点**：3-5 个要点列表
- **适用场景**：什么情况下用这个知识点
- **难度等级**：入门 / 进阶 / 高级
- **关联知识点**：前置 / 后续推荐

## 技术细节

### 支持的输入格式
- 飞书在线文档（docx）
- 本地 .docx 文件
- Obsidian Markdown 笔记

### AI 模型
- 默认：OpenAI GPT-4 / GPT-3.5
- 可切换：Gemini、Claude、国产大模型（需兼容 OpenAI API）

### 输出目标
- 本地 JSON 文件
- 飞书多维表格（Bitable）
- 腾讯文档（通过 JSON 导入）

## 为什么要用这个工具？

**传统方式：** 让用户翻 40 节课、几十小时的视频找答案 → 大概率放弃

**这个工具：** 把课程拆成 700+ 个独立知识点 → 用户搜索"插件配置"，3 秒定位答案

## 常见问题

### Q: 我没有视频转录稿怎么办？
A: 可以用 Whisper API（讯飞、阿里云、OpenAI）把音频/视频转文本，成本很低（40 节课约 200 元）。

### Q: 知识点会不会拆得太碎？
A: 有最低字数限制（200 字），太短的会被合并。也可以在 `config.json` 里调整。

### Q: 我想用腾讯文档，不想用飞书可以吗？
A: 可以！用 `--json-only` 导出 JSON，然后手动导入腾讯文档。

### Q: 标签体系可以自定义吗？
A: 可以，编辑 `scripts/knowledge_extractor.py` 里的 Prompt 和标签列表即可。

## 成本估算（40 节课示例）

| 环节 | 成本 |
|------|------|
| 音频转文本（如需） | ~200 元（Whisper API） |
| AI 拆解知识点 | ~500 元（GPT-4） |
| 人工审核时间 | ~20 小时 |

**vs 纯人工拆解：** 100+ 小时，效率提升 5 倍

## 进阶用法

### 配合其他工具
- `image-to-knowledge`：从截图/PPT 提取知识点（配套工具）
- 自定义标签体系：适配你的业务场景
- 多语言支持：修改 Prompt 即可

### 调整提取策略
编辑 `scripts/knowledge_extractor.py` 里的 System Prompt，改变 AI 提取的风格和粒度。

## License

MIT — 自由使用、修改和分发

## 作者

OpenClaw Studio

如有问题或建议，欢迎提 Issue 或 PR！
