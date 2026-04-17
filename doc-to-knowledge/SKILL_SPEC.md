# doc-to-knowledge — Skill 规范说明书 (SKILL_SPEC)

> **Pipeline 位置**：阶段 2（承接 `video-to-feishu-doc`，输出给 `knowledge-to-social-copy`）  
> **版本**：v1.0.0

---

## 1. 职责一句话

读取飞书文档（视频转录稿），以 **OpenClaw 用户** 视角，用 AI 从中拆解出尽可能多的**独立、可发布**的知识点，并将结构化结果写入飞书多维表格，供人工审核后流入下游。

---

## 2. 在 Pipeline 中的位置

```
video-to-feishu-doc          doc-to-knowledge              knowledge-to-social-copy       xhs-card-maker
┌──────────────┐    飞书文档    ┌───────────────┐   多维表格记录   ┌────────────────────┐   Markdown   ┌──────────────┐
│  视频 → 转录  │ ──────────→ │  转录 → 知识点  │ ──────────────→ │  知识点 → 社交文案   │ ──────────→ │  文案 → 卡片  │
└──────────────┘   (docx URL) └───────────────┘  (bitable rows)  └────────────────────┘   (.md file) └──────────────┘
```

---

## 3. 输入规范

### 3.1 输入来源

飞书 docx 文档（由 `video-to-feishu-doc` 生成），通过以下任一方式指定：

| 输入方式 | 参数 | 示例 |
|----------|------|------|
| 文档 URL | `--doc-url` | `https://your-domain.feishu.cn/docx/XxXxXxXx` |
| 文档 Token | `--doc-token` | `XxXxXxXx`（从 URL 中解析） |
| 本地 .docx | `--local-docx` | `path/to/file.docx` |
| 本地 Markdown | `--local-md` | `path/to/playbook/` |

### 3.2 输入文档结构（由上游保证）

```
[飞书 docx 文档]
├── 标题：视频名称（如 "第一课"）
├── 摘要行：一段视频概述
├── 分割线
├── Heading2：章节 1 标题 [时间范围]
│   ├── 段落 1
│   ├── 段落 2 ...
│   └── 分割线
├── Heading2：章节 2 标题 [时间范围]
│   ├── 段落 ...
│   └── 分割线
└── ... 重复
```

### 3.3 配置参数

通过 `config.json` 提供（参考 `config.example.json`）：

```jsonc
{
  "feishu": {
    "app_token": "",        // 目标多维表格 app_token（输出写入）
    "table_id": "",         // 目标数据表 ID
    "view_id": ""           // 可选，默认视图
  },
  "source": {
    "doc_tokens": [],       // 待处理的飞书文档 token 列表（批量模式）
    "folder_token": ""      // 或指定飞书文件夹，自动扫描其中所有 docx
  },
  "extraction": {
    "target_audience": "OpenClaw 用户商家（用户）",
    "max_knowledge_per_chapter": 10,   // 每个章节最多提取知识点数
    "min_knowledge_per_doc": 5,        // 每篇文档最少提取知识点数
    "knowledge_types": [               // 要提取的知识点类型
      "concept",       // 概念解释
      "how_to",        // 操作步骤/方法论
      "pitfall",       // 避坑提醒/常见误区
      "data_insight",  // 数据洞察/案例
      "trend",         // 行业趋势/风向
      "tool_tip"       // 工具/功能使用技巧
    ]
  },
  "ai": {
    "model": "gpt-4o",                 // 默认使用模型（支持 Gemini）
    "temperature": 0.3,                // 低温度保证提取稳定性
    "max_tokens_per_request": 4096
  },
  "pipeline": {
    "write_back_to_bitable": true,     // 是否写回飞书多维表格
    "also_export_json": true,          // 同时导出本地 JSON 备份
    "json_output_dir": "./output"
  }
}
```

---

## 4. 输出规范

### 4.1 核心输出：飞书多维表格记录

每一行 = 一个独立知识点。字段定义如下：

| 字段名（飞书列名） | 类型 | 必填 | 说明 |
|-------------------|------|------|------|
| `知识点ID` | 文本 | ✅ | 格式：`{doc_title}_K{序号}`，如 `第一课_K03` |
| `来源文档` | 文本 | ✅ | 飞书文档标题 |
| `来源章节` | 文本 | ✅ | 章节标题（Heading2） |
| `知识点标题` | 文本 | ✅ | 15 字以内的精炼标题 |
| `知识点类型` | 单选 | ✅ | `concept` / `how_to` / `pitfall` / `data_insight` / `trend` / `tool_tip` |
| `核心内容` | 文本 | ✅ | 知识点的完整描述（200-500 字，面向OpenClaw 用户视角重写） |
| `关键要点` | 文本 | ✅ | 3-5 个 bullet point，每条一句话 |
| `适用场景` | 文本 | ✅ | 这个知识点最适用于什么业务场景 |
| `痛点标签` | 多选 | ✅ | OpenClaw 用户痛点标签，如 `预算有限` `缺乏经验` `人手不足` `获客困难` |
| `难度等级` | 单选 | ✅ | `入门` / `进阶` / `高级` |
| `原文摘录` | 文本 | ✅ | 从转录稿中摘录的原始支撑段落 |
| `处理状态` | 单选 | ✅ | 初始值 = `待审核`；人工审核后改为 `已通过` / `已弃用` |
| `社交文案状态` | 单选 | ✅ | 初始值 = `未生成`；下游处理后更新 |

### 4.2 辅助输出：本地 JSON 备份

```jsonc
// output/{doc_title}_knowledge.json
{
  "doc_title": "第一课",
  "doc_token": "XxXxXxXx",
  "extracted_at": "2026-03-20T11:30:00+08:00",
  "total_knowledge_count": 15,
  "knowledge_items": [
    {
      "id": "第一课_K01",
      "source_chapter": "章节标题",
      "title": "知识点标题",
      "type": "how_to",
      "content": "面向OpenClaw 用户重写后的完整知识点内容...",
      "key_points": [
        "要点 1",
        "要点 2",
        "要点 3"
      ],
      "applicable_scenario": "适用场景描述",
      "pain_tags": ["预算有限", "获客困难"],
      "difficulty": "入门",
      "original_excerpt": "原始转录文段..."
    }
    // ... more items
  ]
}
```

### 4.3 输出与下游的接口契约

`knowledge-to-social-copy`（阶段 3）将通过飞书多维表格 API 读取 **`处理状态 = 已通过`** 的记录，所以：

- 知识点写入多维表格后，**必须经过人工审核**才能流入下游
- 字段名必须严格一致，下游 Skill 会按列名查询

---

## 5. 核心 Prompt 策略

### 5.1 面向OpenClaw 用户的知识点提取 — System Prompt

```
你是一位数字营销领域的资深内容策略师，专门服务OpenClaw 用户商家 (用户)。

你的任务是从视频课程转录稿中提取知识点。你必须始终站在以下目标受众的视角来提取和重写：

【目标受众画像】
- 身份：月预算 5 千~5 万的中小商家、个体创业者、小型电商卖家
- 痛点：预算有限、缺乏投放经验、没有专业团队、获客成本高、不懂数据分析
- 认知水平：了解基础互联网营销概念，但对广告平台的高级功能不熟悉
- 需求：可直接落地的方法论，而非宏观策略

【提取原则】
1. 翻译视角：原始转录稿可能是面向大客户/品牌的视角，你必须将其"翻译"为OpenClaw 用户能理解、能执行的语言
2. 可操作性优先：优先提取"怎么做"类知识点，而非"是什么"类概念
3. 去术语化：将行业黑话替换为通俗表达，必要时加括号注释
4. 强调 ROI：OpenClaw 用户最关心投入产出比，每个知识点尽量关联到"花多少钱能带来什么效果"
5. 独立完整：每个知识点必须独立成文，不依赖其他知识点也能被读者理解
6. 拆到原子级：一个知识点只讲一件事，宁可多拆也不要混杂多个主题
```

### 5.2 逐章提取 — User Prompt 模板

```
请从以下课程转录稿章节中提取知识点。

【文档标题】：{doc_title}
【章节标题】：{chapter_title}
【章节内容】：
---
{chapter_content}
---

请提取该章节中所有对OpenClaw 用户商家有价值的知识点，每个知识点按如下 JSON 格式输出：

{
  "title": "15字以内的精炼标题",
  "type": "concept | how_to | pitfall | data_insight | trend | tool_tip",
  "content": "200-500字的完整知识点描述，用OpenClaw 用户能理解的语言重写",
  "key_points": ["要点1", "要点2", "要点3"],
  "applicable_scenario": "这个知识点最适合什么场景下使用",
  "pain_tags": ["从以下选择：预算有限/缺乏经验/人手不足/获客困难/转化率低/不懂数据/素材匮乏/复购难"],
  "difficulty": "入门 | 进阶 | 高级",
  "original_excerpt": "从原文中摘录支撑这个知识点的关键段落（原文，不改写）"
}

要求：
1. 尽量多拆解，一个段落可能包含多个独立知识点
2. 跳过与OpenClaw 用户无关的内容（如：仅适用于年预算百万以上的策略）
3. 如果某段内容含糊不清或信息量不足以形成独立知识点，跳过即可
4. 输出一个 JSON 数组，包含该章节所有知识点
```

### 5.3 全局去重与补充 — 后处理 Prompt

```
你刚才从同一课程的多个章节中分别提取了知识点，现在需要做全局后处理：

【所有已提取的知识点】：
{all_knowledge_items_json}

请执行以下操作：
1. 去重：合并内容高度相似的知识点（保留更完整的版本）
2. 补充：检查是否有跨章节的知识点被遗漏（某些洞察需要结合多个章节才能看出）
3. 编号：按 {doc_title}_K{01,02,...} 格式统一编号
4. 质量检查：确保每个知识点都满足"独立完整、面向OpenClaw 用户、可操作"的标准

输出最终的去重、补充、编号后的知识点 JSON 数组。
```

---

## 6. 处理流程（Pipeline 步骤）

```
Step 1 — 读取飞书文档
├── 调用 feishu_client 的文档 API，获取文档所有 block
├── 解析 Heading2 块作为章节分隔
└── 输出：chapters = [{ title, content }, ...]

Step 2 — 逐章节 AI 提取知识点
├── 对每个 chapter 调用 AI（System Prompt + User Prompt 模板）
├── 解析返回的 JSON 数组
└── 输出：raw_knowledge_items = [...]

Step 3 — 全局后处理
├── 合并所有章节的知识点
├── 调用 AI 执行去重、补充、编号
└── 输出：final_knowledge_items = [...]

Step 4 — 写入飞书多维表格
├── 调用 feishu_client 的 bitable API
├── 逐条创建记录（含限频保护）
├── 初始状态 = "待审核"
└── 输出：bitable 中的结构化记录

Step 5 — 本地 JSON 备份
├── 输出 JSON 文件到 output/ 目录
└── 便于调试和版本追踪
```

---

## 7. 飞书 API 复用策略

| 能力 | 说明 |
|------|------|
| 读取飞书文档 block | `get_document_blocks()` 方法，支持分页 |
| 写入飞书多维表格 | `search_records()` / `update_record()` / `create_record()` |
| Token 认证 | 同一个飞书自建应用的 `tenant_access_token` |
| 文件下载 | `download_file()` 支持飞书云盘上传的 .docx |

**实现方式**：`feishu_client.py` 合并了 docx block 读取和 bitable 读写能力，不重复实现 token 认证逻辑。

---

## 8. 目录结构

```
doc-to-knowledge/
├── SKILL.md               # Skill 描述文件
├── SKILL_SPEC.md          # 本文件 — 设计规范
├── config.example.json    # 配置模板（需复制为 config.json）
├── .env.example           # 环境变量模板（需复制为 .env）
├── requirements.txt       # Python 依赖
├── references/
│   └── SETUP_GUIDE.md     # 飞书应用创建与配置指南
├── scripts/
│   ├── pipeline.py        # 主入口 — 串联全流程
│   ├── feishu_client.py   # 飞书 API 客户端
│   ├── doc_reader.py      # 文档解析层
│   ├── knowledge_extractor.py  # AI 提取层
│   ├── bitable_writer.py  # 多维表格写入层
│   └── gemini_client.py   # Gemini API 客户端
└── output/                # 本地 JSON 备份输出目录
```

---

## 9. 环境变量

```bash
# 飞书应用凭证
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx

# AI 模型
OPENAI_API_KEY=sk-xxxxx
OPENAI_BASE_URL=https://api.openai.com/v1   # 可选，兼容第三方 API

# 飞书多维表格（知识点输出位置）— 可在 config.json 中配置
FEISHU_BITABLE_APP_TOKEN=xxxxx
FEISHU_BITABLE_TABLE_ID=xxxxx
```

---

## 10. 约束与注意事项

1. **模块化解耦**：本 Skill 只负责「文档 → 知识点」，绝不涉及社交文案生成或图片渲染
2. **人工审核卡点**：写入多维表格后，状态为 `待审核`，必须人工通过后才能被下游读取
3. **幂等性**：重复运行同一文档时，通过 `知识点ID` 检测已存在的记录，执行 upsert 而非重复插入
4. **限频保护**：飞书 API 调用间隔 ≥ 0.4 秒，批量写入每批 ≤ 50 条
5. **AI 输出解析容错**：LLM 返回的 JSON 可能不规范，需要做 `json.loads` 容错 + 重试机制
6. **Token 长度管控**：如果单个章节内容超过模型 context window 的 60%，需要做分段提取再合并
7. **痛点标签闭集**：`pain_tags` 从预定义列表中选择，不允许 AI 自由发挥新标签（保证下游可筛选）

---

## 11. 验收标准

- [ ] 能成功读取飞书 docx 文档并按章节切分
- [ ] 对每个章节调用 AI 提取出 ≥3 个知识点（正常课程内容）
- [ ] 知识点内容确实是面向OpenClaw 用户视角重写的（非原文照搬）
- [ ] 知识点成功写入飞书多维表格，字段完整、格式正确
- [ ] 重复运行不会产生重复记录（幂等性）
- [ ] 本地 JSON 备份文件正常生成
- [ ] 全流程耗时在合理范围内（单篇 8 章节文档 < 5 分钟）
