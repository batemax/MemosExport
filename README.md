# Memos Export/Import Tools

[English](#english) | [简体中文](#简体中文)

## English

Portable export and import scripts for [Memos](https://www.usememos.com/), built on top of the public `v1` API.

The project is intended for practical content migration:

- export memos into a structured `zip` bundle
- optionally include attachment files
- import that bundle into another Memos instance
- preserve memo IDs so relations remain valid

### Features

- Export `NORMAL` and `ARCHIVED` memos
- Export one JSON payload per memo
- Export a bundle manifest for validation and replay
- Optional attachment file export
- Import in four stages: memos, comments, attachments, relations
- Resume interrupted imports with a state file bound to one bundle and one target instance
- Conflict strategies: `fail` and `skip`
- Standard-library only, no third-party Python dependencies

### Files

- [`export_memos.py`](/Users/booth/Personal/Workspace/memosExport/export_memos.py): create export bundles
- [`import_memos.py`](/Users/booth/Personal/Workspace/memosExport/import_memos.py): restore bundles into a target instance
- [`memos_api.py`](/Users/booth/Personal/Workspace/memosExport/memos_api.py): shared API client
- [`docs/memos-export-import-plan.md`](/Users/booth/Personal/Workspace/memosExport/docs/memos-export-import-plan.md): high-level design
- [`docs/export-bundle-spec.md`](/Users/booth/Personal/Workspace/memosExport/docs/export-bundle-spec.md): bundle format
- [`docs/import-workflow.md`](/Users/booth/Personal/Workspace/memosExport/docs/import-workflow.md): importer execution model

### Requirements

- Python 3.9+
- A Memos instance
- A Memos Personal Access Token

### Quick Start

Export metadata only:

```bash
python3 export_memos.py \
  --base-url "https://memos.example.com" \
  --token "YOUR_TOKEN"
```

Export with attachment files:

```bash
python3 export_memos.py \
  --base-url "https://memos.example.com" \
  --token "YOUR_TOKEN" \
  --attachment-mode embedded_files
```

Import a bundle:

```bash
python3 import_memos.py \
  --base-url "https://target-memos.example.com" \
  --token "YOUR_TOKEN" \
  --bundle "./dist/memos-export-2026-04-07T12-00-00Z.zip"
```

### Environment Variables

Both scripts accept CLI flags and environment variables:

- `MEMOS_BASE_URL`
- `MEMOS_TOKEN`

Example:

```bash
export MEMOS_BASE_URL="https://memos.example.com"
export MEMOS_TOKEN="YOUR_TOKEN"
python3 export_memos.py --attachment-mode embedded_files
```

### Attachment Export Notes

Attachment metadata APIs do not always expose file bytes directly.

This project uses two paths:

- documented API endpoints for memo and attachment metadata
- the file download route `/file/attachments/{attachmentId}/{filename}` for real attachment bytes when `--attachment-mode embedded_files` is enabled

If an attachment cannot be downloaded, the exporter writes a warning into `manifest.json` instead of failing the whole export.

### Export Output

The exporter produces a bundle like:

```text
memos-export-2026-04-07T12-00-00Z.zip
  manifest.json
  memos/
    memos_abc123.json
  attachments/
    abc123/
      image.png
```

See [`docs/export-bundle-spec.md`](/Users/booth/Personal/Workspace/memosExport/docs/export-bundle-spec.md) for the exact schema.

### Import Output

The importer writes:

- `<bundle>.import-state.json`
- `<bundle>.import-state.json.report.json`

These files make interrupted runs resumable and provide an audit trail for failures.

The importer refuses to reuse a state file that belongs to a different bundle or target instance.

Newly created memos are also patched once after creation to reconcile `state` and `pinned` on deployments that ignore those fields during `CreateMemo`.

### Current Scope

Version 1 supports:

- memo content
- `createTime`, `updateTime`, `displayTime`
- `visibility`
- `pinned`
- `location`
- `state`
- attachments
- relations

Version 1 imports comment memos represented by the exported `parent` field.

Version 1 does not restore:

- original creator identity across users
- reactions
- share links
- instance settings
- full multi-user migration

### Conflict Strategy Notes

- `fail`: stop when a memo with the same `memo_id` already exists in the target instance
- `skip`: keep the existing memo body, then continue reconciling attachment IDs and exported relations for that memo

### Compatibility Notes

Tested against `https://memos.moex.top` on `2026-04-07`:

- `CreateMemo` accepted `state` and `pinned` in the request schema, but the instance did not persist them reliably on create
- the importer now compensates by calling `UpdateMemo` after creation for newly created memos
- `CreateAttachment` accepted `externalLink` in the request schema, but the instance returned and persisted it as an empty string
- because of that deployment behavior, `externalLink` attachments should currently be treated as non-lossless on that instance
- comment trees imported correctly through `parent` + comment APIs
- the current exporter only exported top-level memos on that instance; comment memos were not included in the export bundle

### Known Limitations

- comment trees are currently importable, but not fully exportable on instances where `ListMemos` does not return comment memos
- `externalLink` attachments are not lossless on deployments that persist them as empty strings during `CreateAttachment`

### Publishing Notes

Before pushing this repository to GitHub, you should:

1. remove local test bundles from `dist-test/`
2. remove local import state files you do not want to publish
3. replace any real URLs or tokens used in local testing
4. add a license file if you want public reuse

## 简体中文

基于 Memos 公开 `v1` API 的导出与导入脚本，适合做实际可用的内容迁移。

这个项目的目标是：

- 将 memo 导出为结构化 `zip` 包
- 可选地把附件文件一并导出
- 将导出包导入到另一个 Memos 实例
- 保留原始 memo ID，确保 relations 仍然有效

### 功能特性

- 支持导出 `NORMAL` 和 `ARCHIVED` 状态的 memo
- 每条 memo 生成一份独立 JSON
- 生成可校验、可回放的 bundle manifest
- 可选导出附件文件
- 导入分四阶段执行：memos、comments、attachments、relations
- 支持断点续传，且 state file 绑定到单一 bundle 和单一目标实例
- 支持两种冲突策略：`fail` 和 `skip`
- 仅使用 Python 标准库，无第三方依赖

### 文件说明

- [`export_memos.py`](/Users/booth/Personal/Workspace/memosExport/export_memos.py)：导出 bundle
- [`import_memos.py`](/Users/booth/Personal/Workspace/memosExport/import_memos.py)：将 bundle 恢复到目标实例
- [`memos_api.py`](/Users/booth/Personal/Workspace/memosExport/memos_api.py)：共享 API 客户端
- [`docs/memos-export-import-plan.md`](/Users/booth/Personal/Workspace/memosExport/docs/memos-export-import-plan.md)：总体设计
- [`docs/export-bundle-spec.md`](/Users/booth/Personal/Workspace/memosExport/docs/export-bundle-spec.md)：导出包格式
- [`docs/import-workflow.md`](/Users/booth/Personal/Workspace/memosExport/docs/import-workflow.md)：导入执行流程

### 环境要求

- Python 3.9+
- 一个可访问的 Memos 实例
- 一个 Memos Personal Access Token

### 快速开始

仅导出元数据：

```bash
python3 export_memos.py \
  --base-url "https://memos.example.com" \
  --token "YOUR_TOKEN"
```

导出并包含附件文件：

```bash
python3 export_memos.py \
  --base-url "https://memos.example.com" \
  --token "YOUR_TOKEN" \
  --attachment-mode embedded_files
```

导入导出包：

```bash
python3 import_memos.py \
  --base-url "https://target-memos.example.com" \
  --token "YOUR_TOKEN" \
  --bundle "./dist/memos-export-2026-04-07T12-00-00Z.zip"
```

### 环境变量

两个脚本都支持命令行参数和环境变量：

- `MEMOS_BASE_URL`
- `MEMOS_TOKEN`

示例：

```bash
export MEMOS_BASE_URL="https://memos.example.com"
export MEMOS_TOKEN="YOUR_TOKEN"
python3 export_memos.py --attachment-mode embedded_files
```

### 附件导出说明

附件元数据 API 并不总是直接返回文件字节。

当前实现同时使用两类路径：

- 官方文档中的 memo / attachment 元数据 API
- 在 `--attachment-mode embedded_files` 模式下使用 `/file/attachments/{attachmentId}/{filename}` 下载真实附件字节

如果某个附件无法下载，导出器不会终止整个导出，而是把警告写入 `manifest.json`。

### 导出产物

导出器生成的 bundle 结构大致如下：

```text
memos-export-2026-04-07T12-00-00Z.zip
  manifest.json
  memos/
    memos_abc123.json
  attachments/
    abc123/
      image.png
```

完整字段请查看 [`docs/export-bundle-spec.md`](/Users/booth/Personal/Workspace/memosExport/docs/export-bundle-spec.md)。

### 导入产物

导入器会写出：

- `<bundle>.import-state.json`
- `<bundle>.import-state.json.report.json`

这两个文件用于断点续传和最终审计。

如果现有 state file 属于别的 bundle 或别的目标实例，导入器会拒绝复用。

对于新创建的 memo，导入器还会在创建后补做一次更新，用于修正某些部署在 `CreateMemo` 阶段没有保留下来的 `state` 和 `pinned`。

### 当前支持范围

第一版支持恢复：

- memo 内容
- `createTime`、`updateTime`、`displayTime`
- `visibility`
- `pinned`
- `location`
- `state`
- attachments
- relations

第一版支持导入由 `parent` 字段表示的 comment memo。

第一版暂不恢复：

- 跨用户的原始 creator 身份
- reactions
- share links
- 实例级设置
- 完整多用户迁移

### 冲突策略说明

- `fail`：目标实例中只要已存在相同 `memo_id`，立即停止
- `skip`：保留目标中已存在的 memo 本体，但继续补齐该 memo 的附件 ID 对齐和 relations 回填

### 兼容性说明

基于 `2026-04-07` 对 `https://memos.moex.top` 的实测：

- `CreateMemo` 的请求结构虽然声明支持 `state` 和 `pinned`，但该实例在创建时并不会稳定持久化这两个字段
- 导入器现在会在创建后追加一次 `UpdateMemo`，用于修正新建 memo 的这两个字段
- `CreateAttachment` 的请求结构虽然声明支持 `externalLink`，但该实例返回和持久化的值都是空字符串
- 因此在该实例上，`externalLink` 附件当前应视为“非无损能力”
- comment 树可以通过 `parent` 和 comment API 正确导入
- 当前 exporter 在该实例上只能导出顶级 memo，comment memo 不会进入导出包

### 已知限制

- comment 树当前可以导入，但在 `ListMemos` 不返回 comment memo 的实例上，无法完整导出
- 对于会把 `CreateAttachment.externalLink` 持久化为空字符串的部署，externalLink 附件当前不是无损能力
