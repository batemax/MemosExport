# Export Bundle Specification

[English](#english) | [简体中文](#简体中文)

## English

### Purpose

This document defines the version 1 export bundle format produced by `export_memos.py`.

The bundle is intended to be:

- portable
- inspectable
- replayable
- forward-compatible

### Archive Layout

```text
memos-export-2026-04-07T12-00-00Z.zip
  manifest.json
  memos/
    memos_abc123.json
    memos_def456.json
  attachments/
    abc123/
      image.png
      note.pdf
```

### manifest.json

`manifest.json` is the importer entry point. A typical manifest looks like:

```json
{
  "format_version": 1,
  "bundle_type": "memos-export",
  "exported_at": "2026-04-07T12:00:00Z",
  "source_instance": "https://memos.example.com",
  "source_user": {
    "name": "users/booth",
    "username": "booth",
    "displayName": "Booth"
  },
  "memo_count": 128,
  "attachment_mode": "embedded_files",
  "states": ["NORMAL", "ARCHIVED"],
  "order_by": "display_time desc",
  "filter": "",
  "items": [
    {
      "memo_name": "memos/abc123",
      "memo_id": "abc123",
      "memo_json_path": "memos/memos_abc123.json",
      "attachment_dir": "attachments/abc123",
      "attachment_count": 2
    }
  ],
  "warnings": []
}
```

### Manifest Fields

- `format_version`: export format version, currently `1`
- `bundle_type`: currently `memos-export`
- `exported_at`: UTC ISO8601 timestamp
- `source_instance`: origin Memos base URL
- `source_user`: authenticated export user, sanitized to avoid secrets
- `memo_count`: number of memo payload files in the bundle
- `attachment_mode`: `metadata_only` or `embedded_files`
- `states`: exported memo states
- `order_by`: API order setting used during export
- `filter`: API filter used during export
- `items`: per-memo index entries
- `warnings`: non-fatal export warnings

### Memo Payload Files

Each memo is written as one JSON file under `memos/`.

Example:

```json
{
  "name": "memos/abc123",
  "memo_id": "abc123",
  "state": "NORMAL",
  "creator": "users/booth",
  "createTime": "2026-04-01T08:00:00Z",
  "updateTime": "2026-04-01T09:00:00Z",
  "displayTime": "2026-04-01T08:00:00Z",
  "content": "# title\n\nhello",
  "visibility": "PRIVATE",
  "pinned": false,
  "tags": ["work"],
  "parent": null,
  "snippet": "title hello",
  "location": null,
  "attachments": [],
  "relations": []
}
```

### Attachment Export Rules

#### metadata_only

In `metadata_only` mode:

- attachment metadata is preserved in memo JSON
- no attachment files are written under `attachments/`

#### embedded_files

In `embedded_files` mode:

- the exporter first checks JSON metadata for inline content
- if that is empty, it attempts to download bytes from `/file/attachments/{attachmentId}/{filename}`
- successfully downloaded files are written under `attachments/{memo_id}/`
- the memo JSON receives an `exportedPath` field for each materialized attachment

If an attachment cannot be downloaded, the exporter records a warning in `manifest.json` and continues.

### Validation Rules

The importer expects:

- `manifest.json` to exist
- `format_version == 1`
- `bundle_type == "memos-export"`
- every `memo_json_path` listed in `items` to exist

For `embedded_files` bundles, attachment files referenced by `exportedPath` should also exist.

### Forward Compatibility

Future versions can add fields for:

- reactions
- user mapping
- share links

The current format is intended to evolve through additive changes rather than breaking field renames.

## 简体中文

### 用途

本文定义了 `export_memos.py` 生成的第一版导出包格式。

这个 bundle 的设计目标是：

- 可移植
- 可检查
- 可回放
- 向前兼容

### 压缩包结构

```text
memos-export-2026-04-07T12-00-00Z.zip
  manifest.json
  memos/
    memos_abc123.json
    memos_def456.json
  attachments/
    abc123/
      image.png
      note.pdf
```

### manifest.json

`manifest.json` 是导入器的入口文件。一个典型示例如下：

```json
{
  "format_version": 1,
  "bundle_type": "memos-export",
  "exported_at": "2026-04-07T12:00:00Z",
  "source_instance": "https://memos.example.com",
  "source_user": {
    "name": "users/booth",
    "username": "booth",
    "displayName": "Booth"
  },
  "memo_count": 128,
  "attachment_mode": "embedded_files",
  "states": ["NORMAL", "ARCHIVED"],
  "order_by": "display_time desc",
  "filter": "",
  "items": [
    {
      "memo_name": "memos/abc123",
      "memo_id": "abc123",
      "memo_json_path": "memos/memos_abc123.json",
      "attachment_dir": "attachments/abc123",
      "attachment_count": 2
    }
  ],
  "warnings": []
}
```

### Manifest 字段

- `format_version`：导出格式版本，当前为 `1`
- `bundle_type`：当前固定为 `memos-export`
- `exported_at`：UTC ISO8601 时间戳
- `source_instance`：来源 Memos 实例地址
- `source_user`：经过脱敏的导出用户信息
- `memo_count`：bundle 内 memo payload 文件数量
- `attachment_mode`：`metadata_only` 或 `embedded_files`
- `states`：导出的 memo 状态集合
- `order_by`：导出时使用的 API 排序参数
- `filter`：导出时使用的 API 过滤条件
- `items`：逐 memo 的索引条目
- `warnings`：非致命导出警告

### Memo Payload 文件

每条 memo 都会写成 `memos/` 目录下的一份独立 JSON。

示例：

```json
{
  "name": "memos/abc123",
  "memo_id": "abc123",
  "state": "NORMAL",
  "creator": "users/booth",
  "createTime": "2026-04-01T08:00:00Z",
  "updateTime": "2026-04-01T09:00:00Z",
  "displayTime": "2026-04-01T08:00:00Z",
  "content": "# title\n\nhello",
  "visibility": "PRIVATE",
  "pinned": false,
  "tags": ["work"],
  "parent": null,
  "snippet": "title hello",
  "location": null,
  "attachments": [],
  "relations": []
}
```

### 附件导出规则

#### metadata_only

在 `metadata_only` 模式下：

- 只保留附件元数据到 memo JSON
- 不会在 `attachments/` 目录下写出附件文件

#### embedded_files

在 `embedded_files` 模式下：

- 导出器会先检查 JSON 元数据里是否有内嵌 `content`
- 如果没有，就尝试从 `/file/attachments/{attachmentId}/{filename}` 下载字节
- 下载成功的文件会写到 `attachments/{memo_id}/`
- 对应的 memo JSON 会为该附件增加 `exportedPath` 字段

如果某个附件无法下载，导出器会把警告写入 `manifest.json`，但不会中断整个导出。

### 校验规则

导入器要求：

- 必须存在 `manifest.json`
- `format_version == 1`
- `bundle_type == "memos-export"`
- `items` 中列出的每个 `memo_json_path` 都必须存在

对于 `embedded_files` 模式，`exportedPath` 指向的附件文件也应存在。

### 向前兼容

后续版本可以继续增加字段，例如：

- reactions
- user mapping
- share links

当前格式尽量通过“只增不改”的方式演进，避免破坏性字段改名。
