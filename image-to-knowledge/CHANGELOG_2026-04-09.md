# image-to-knowledge Skill 检查与改造记录

**日期**: 2026-04-09 10:47
**操作人**: superBU（超级布布）

---

## 一、原有问题诊断

| # | 问题 | 严重程度 |
|---|------|----------|
| 1 | 飞书强绑定：输出只能写入飞书多维表格，不支持本地输出 | 高 |
| 2 | 缺少 PDF 支持：description 提到 PDF 但实际只支持 jpg/png/webp/gif | 高 |
| 3 | 输出选项不灵活：只有飞书写入 + JSON 导出两种模式 | 中 |
| 4 | 启动时必须配置飞书凭证，否则报警告 | 中 |
| 5 | `--json-only` 命名不清晰 | 低 |

## 二、改造方案

### 新增模块
1. **`scripts/pdf_loader.py`** — PDF 文件加载器
   - 使用 PyMuPDF (fitz) 将 PDF 每页渲染为 PNG 图片
   - 支持 DPI 配置、页码范围、最大页数限制
   - 批量加载多个 PDF
   
2. **`scripts/local_writer.py`** — 本地输出模块
   - Markdown 输出：含概览统计表 + 目录 + 逐条知识点详情
   - JSON 输出：结构化数据，带中文字段名
   - 适合直接粘贴到腾讯文档

### 修改模块
3. **`scripts/pipeline.py`** — 主入口重构
   - 新增 `--pdf` 参数：直接指定 PDF 文件
   - 新增 `--output-format` 参数：`markdown`(默认) / `json` / `both` / `feishu`
   - 新增 `--pdf-dpi` / `--pdf-max-pages` 参数
   - `--folder` 现在自动扫描 PDF 文件（除图片外）
   - 移除 `--json-only`（被 `--output-format json` 替代）
   - 飞书模块改为延迟导入（仅选择 feishu 输出时才加载）
   - 飞书凭证不再是必须配置项

### 配置变更
4. **`config.json`** — 更新默认配置
   - `pipeline.default_output_format` 改为 `"markdown"`
   - 移除 `pipeline.write_back_to_bitable`
   - 新增 `pdf` 配置段

5. **`requirements.txt`** — 添加 PyMuPDF 依赖

6. **`SKILL.md`** — 完全重写
   - 反映 PDF 支持
   - 反映本地输出为默认
   - 更新命令示例
   - 更新架构图

## 三、改动文件清单

| 文件 | 操作 |
|------|------|
| `scripts/pdf_loader.py` | 新建 |
| `scripts/local_writer.py` | 新建 |
| `scripts/pipeline.py` | 重构 |
| `config.json` | 更新 |
| `requirements.txt` | 更新 |
| `SKILL.md` | 重写 |

## 四、保留的兼容性

- `bitable_writer.py` 和 `feishu_client.py` 保留不动
- `--output-format feishu` 仍可写入飞书多维表格
- `--feishu-files` 仍可从飞书云盘下载图片
- `--output-meta` IPC 契约仍然有效（pipeline-ceo 兼容）
- 知识点 ID 格式和数据结构完全不变

## 五、使用示例

```bash
# 最简用法：文件夹 → Markdown
python3 scripts/pipeline.py --folder ~/案例图片/

# PDF → Markdown + JSON
python3 scripts/pipeline.py --pdf ~/报告.pdf --output-format both

# 图片 → JSON（程序处理）
python3 scripts/pipeline.py --images a.jpg b.png --output-format json

# 仍可写入飞书
python3 scripts/pipeline.py --folder ~/案例/ --output-format feishu
```
