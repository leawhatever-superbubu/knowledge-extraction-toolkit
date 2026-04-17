# 飞书应用配置指南

本指南帮助你从零开始配置 doc-to-knowledge 所需的飞书自建应用和多维表格。

---

## 1. 创建飞书自建应用

1. 登录 [飞书开放平台](https://open.feishu.cn/app)
2. 点击「创建自建应用」
3. 填写应用名称（如 "知识提取机器人"）和描述
4. 创建成功后，进入应用详情页

### 获取凭证

在「凭证与基础信息」页面获取：
- **App ID**：格式如 `cli_xxxxx`
- **App Secret**：格式如 `xxxxx`

将它们填入 `.env` 文件：
```bash
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx
```

---

## 2. 配置应用权限

在「权限管理」页面，搜索并添加以下权限：

### 文档读取权限
- `docx:document:readonly` — 读取文档内容
- `drive:drive:readonly` — 读取云盘文件

### 多维表格权限
- `bitable:app` — 读写多维表格

### 可选权限
- `im:message:send_as_bot` — 机器人发送消息（用于群聊通知）

添加权限后，需要**管理员审批通过**才能生效。

---

## 3. 创建飞书多维表格

1. 在飞书中创建一个新的多维表格
2. 按以下结构添加字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 知识点ID | 文本 | 主键，格式 `{doc_title}_K{序号}` |
| 来源文档 | 文本 | 来源文档标题 |
| 来源章节 | 文本 | 来源章节标题 |
| 知识点标题 | 文本 | 15 字以内标题 |
| 知识点类型 | 单选 | 选项：概念解释 / 操作方法 / 避坑提醒 / 数据洞察 / 行业趋势 / 工具技巧 |
| 核心内容 | 文本 | 200-500 字描述 |
| 关键要点 | 文本 | bullet point 格式 |
| 适用场景 | 文本 | 场景描述 |
| 痛点标签 | 多选 | 选项：预算有限 / 缺乏经验 / 人手不足 / 获客困难 / 转化率低 / 不懂数据 / 素材匮乏 / 复购难 |
| 难度等级 | 单选 | 选项：入门 / 进阶 / 高级 |
| 原文摘录 | 文本 | 原始转录文段 |
| 处理状态 | 单选 | 选项：待审核 / 已通过 / 已弃用 |
| 社交文案状态 | 单选 | 选项：未生成 / 已生成 / 已发布 |
| 序号 | 文本 | 自动分配的序号 |

### 获取表格信息

多维表格 URL 格式：
```
https://your-domain.feishu.cn/base/APP_TOKEN?table=TABLE_ID&view=VIEW_ID
```

从 URL 中提取：
- **app_token**：`/base/` 后面的部分
- **table_id**：`?table=` 后面的部分
- **view_id**（可选）：`&view=` 后面的部分

填入 `config.json`：
```json
{
  "feishu": {
    "app_token": "YOUR_APP_TOKEN",
    "table_id": "YOUR_TABLE_ID",
    "view_id": "YOUR_VIEW_ID"
  }
}
```

---

## 4. 授权应用访问多维表格

**重要**：飞书自建应用默认无法访问你的多维表格，需要手动授权。

1. 打开多维表格
2. 点击右上角「...」→「更多」→「添加文档应用」
3. 搜索并添加你创建的自建应用
4. 授予「可编辑」权限

同理，如果需要读取飞书文档，也需要将文档授权给应用。

---

## 5. 配置 AI 模型

本工具支持两种 AI 后端：

### 方案 A：OpenAI 兼容接口（推荐）

在 `.env` 中配置：
```bash
OPENAI_API_KEY=sk-xxxxx
# 可选：使用第三方兼容接口
# OPENAI_BASE_URL=https://your-compatible-api.com/v1
```

在 `config.json` 中设置模型：
```json
{
  "ai": {
    "model": "gpt-4o",
    "temperature": 0.3,
    "max_tokens_per_request": 4096
  }
}
```

### 方案 B：Gemini 原生接口

如果你使用 Gemini API，系统会自动检测并切换到原生接口：
```bash
OPENAI_API_KEY=sk-xxxxx
OPENAI_BASE_URL=https://your-gemini-proxy.com
```

```json
{
  "ai": {
    "model": "gemini-2.5-flash",
    "base_url": "https://your-gemini-proxy.com"
  }
}
```

---

## 6. 快速验证

配置完成后，运行预览模式验证：

```bash
# 1. 安装依赖
pip3 install -r requirements.txt

# 2. 预览模式（不写入飞书，只提取知识点到本地 JSON）
python3 scripts/pipeline.py --doc-token YOUR_DOC_TOKEN --dry-run
```

如果看到类似以下输出，说明配置成功：
```
Step 1/4: 读取飞书文档 — YOUR_TOKEN
文档概况: 第一课 — 8 章节, 12000 字
Step 2/4: AI 提取知识点
提取完成: 共 15 个知识点
Step 3/4: [DRY RUN] 跳过写入飞书多维表格
Step 4/4: 导出本地 JSON 备份
```

---

## 常见问题

### Q: 提示 "获取 tenant_access_token 失败"
A: 检查 FEISHU_APP_ID 和 FEISHU_APP_SECRET 是否正确。

### Q: 提示 "获取文档块失败" / 权限不足
A: 确认文档已授权给应用（参考第 4 步）。

### Q: AI 提取结果为空
A: 检查 OPENAI_API_KEY 是否有效，以及模型是否正确。尝试用 `--model gpt-4o-mini` 测试。

### Q: 写入多维表格失败
A: 确认多维表格已授权给应用，且字段名与 field_map 完全一致。
