# 📖 文档提炼神器 (doc-to-knowledge) —— 小白使用教程

这个工具可以帮你**一键把文档（比如会议纪要、视频转录稿）、本地 Word、Markdown 笔记，直接提取成一条条结构化的“知识点”**！
提取出来的知识点会自动整理成漂亮的 Markdown 格式（你可以直接复制粘贴进腾讯文档、Notion 或本地），也可以自动录入飞书多维表格（如果你需要做知识库）。

---

## 🛠️ 第一步：快速准备

1. **下载解压**
   - 把 `doc-to-knowledge.zip` 下载并解压到你电脑里的任意一个文件夹。
2. **填写 API Key（必需）**
   - 找到解压文件夹里的 `.env` 文件。
   - 用记事本（或任意文本编辑器）打开它。
   - 填入你的 AI 大模型 Key，像下面这样（如果你用的是别家模型，也填对应的 URL 和 Key）：
     ```ini
     OPENAI_API_KEY=sk-xxxxxxxxx你的Key
     OPENAI_BASE_URL=https://api.openai.com/v1  # 根据实际模型接口填写
     ```
   - *（可选）如果**不需要**写入飞书多维表格，飞书相关的凭证可以留空！不用管！*
3. **安装依赖环境**
   - 打开终端（Terminal，在 Mac/Linux 上）或者 命令提示符（cmd，在 Windows 上）。
   - 切换到这个文件夹里（比如 `cd ~/Downloads/doc-to-knowledge`）。
   - 运行：`pip install -r requirements.txt`

---

## 🚀 第二步：开始提取知识点！

下面是最常用的几种傻瓜操作。**注意**：在终端里运行命令时，确保你已经在 `doc-to-knowledge` 目录下。

### 场景一：提取本地 Word 文档（最简单，不用配飞书！）
你有一个本地的 `.docx` 文件，想直接提取成知识点存到本地：
```bash
python scripts/pipeline.py --local-docx "/路径/到/你的/文件.docx"
```
✅ **结果**：程序跑完后，会在 `output/` 文件夹里生成一个排版精美的 `.md` 文件。你可以直接打开它，全选复制，粘贴到腾讯文档里，排版会自动保留！

### 场景二：提取本地 Markdown 笔记（支持批量提取！）
你整理了一堆 Obsidian / Typora 的 `.md` 笔记，想全部批量提取：
```bash
# 提取单个 Markdown 笔记
python scripts/pipeline.py --local-md "/路径/到/你的/笔记.md"

# 批量提取整个文件夹里的所有 Markdown 笔记！
python scripts/pipeline.py --local-md "/路径/到/你的/笔记文件夹/"
```
✅ **结果**：同样会在 `output/` 下按文件名生成提炼好的知识点，非常适合建立自己的超级知识库。

### 场景三：直接提炼飞书云文档（只需给个链接！）
如果你想直接分析网上的飞书文档：
```bash
# 直接贴飞书文档的链接
python scripts/pipeline.py --doc-url "https://your-domain.feishu.cn/docx/xxxxxxxxx"
```
> **⚠️ 提示**：分析云端飞书文档，**必须**在 `.env` 中配置 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 哦！

---

## 🎛️ 高级玩法：输出到飞书多维表格

默认情况下，工具只会把知识点保存在本地的 `output/` 文件夹里。
如果你想直接自动填写到**飞书多维表格**里：

1. 确保 `.env` 里配置了飞书相关的五个参数（`APP_ID`, `APP_SECRET`, `APP_TOKEN`, `TABLE_ID` 等）。
2. 在运行命令时，加上 `--output-format feishu`：

```bash
# 例子：提取本地 Word，直接写入飞书多维表格！
python scripts/pipeline.py --local-docx "/路径/到/你的/文件.docx" --output-format feishu
```

**支持的输出格式大全**：
- `--output-format markdown` ：(默认) 只输出好看的 Markdown 文件。
- `--output-format feishu` ：只写入飞书多维表格。
- `--output-format json` ：只输出给程序员用的纯数据文件。
- `--output-format all` ：小孩子才做选择，我全都要！（本地 MD + JSON + 写入飞书）

---

## 常见问题 Q&A

**Q: 运行报错“缺少飞书应用凭证”？**
A: 因为你在处理飞书云文档链接（或者选择了写入飞书表格），但没在 `.env` 里填飞书凭证。如果只是想处理本地文件，请用 `--local-docx` 参数，这样就不用管飞书了。

**Q: 提取出来的 Markdown 文件怎么用？**
A: 最好的用法是：用 Typora 等软件打开，`Ctrl+A` (全选)，`Ctrl+C` (复制)，然后打开一个空的腾讯文档或飞书文档，`Ctrl+V` (粘贴)！你会发现加粗、列表、层级、引用的排版全部完美继承！

**Q: 我可以自己修改提取规则吗？**
A: 完全可以！在 `config.json` 里，找到 `ai.prompt.system` 和 `ai.prompt.user`，你可以随意用大白话修改提取要求，让它变成你的专属提炼器！