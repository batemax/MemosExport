# Import Workflow

[English](#english) | [简体中文](#简体中文)

## English

### Goal

Restore an export bundle into a target Memos instance while keeping memo IDs stable and rebuilding comments, attachments, and relations in a controlled order.

### Import Stages

The importer runs in four stages:

1. create top-level memo bodies
2. create parented memos through the comment API
3. reconcile selected memo fields after creation
4. upload attachments
5. apply relations

This order prevents relation failures caused by missing target memos, preserves parent-before-comment creation, compensates for deployments that ignore some create-time memo fields, and keeps attachment failures isolated from memo creation.

### Stage 0: Preflight

Before any writes happen, the importer:

1. validates the target token with `GET /api/v1/auth/me`
2. extracts the bundle
3. loads `manifest.json`
4. validates required files
5. creates or resumes an import state file
6. verifies that an existing state file belongs to the same bundle path and target instance

### Conflict Strategies

#### fail

If a memo with the same `memo_id` already exists in the target instance, stop immediately.

Use this when you want a strict migration with no ambiguity.

#### skip

If a memo with the same `memo_id` already exists, keep it and continue.

Use this when resuming interrupted work or importing into a partially populated target.

In `skip` mode the importer still:

- restores exported attachments that are not already present on that memo
- applies exported relations for that memo

### Stage 1: Create Memo Bodies and Comments

For each memo payload:

- read `memos/<id>.json`
- call `POST /api/v1/memos` for top-level memos
- call `POST /api/v1/memos/{memo}/comments` when the exported payload has a `parent`
- pass the original `memo_id`
- restore:
  - `state`
  - `content`
  - `visibility`
  - `createTime`
  - `updateTime`
  - `displayTime`
  - `pinned`
  - `location`

Parented memos are deferred until the parent memo already exists in the target instance.

Relations are intentionally skipped in this stage.

### Stage 1.5: Reconcile Create-Time Memo Fields

Some deployments accept `state` and `pinned` on `CreateMemo`, but do not persist them reliably during the create call.

For newly created memos only, the importer can immediately call `PATCH /api/v1/memos/{memo}` with `updateMask=state,pinned` to reconcile those fields.

This step is intentionally not applied to `skip`-mode memos, because `skip` means keep the existing memo body as-is.

### Stage 2: Upload Attachments

If the bundle was exported with `attachment_mode = embedded_files`, the importer:

- reads each attachment entry
- resolves `exportedPath`
- base64-encodes the file content
- calls `POST /api/v1/attachments`
- binds the attachment to `memos/{memo_id}`

For memos that already exist in the target instance, the importer first indexes existing attachment IDs and skips exported attachments that are already present.

If the bundle only contains metadata:

- attachment restoration is skipped unless the attachment is represented as an external link

Attachment failures are recorded but do not roll back already created memos.

### Stage 3: Apply Relations

After all memo bodies exist, the importer:

- reads relation definitions from each memo payload
- normalizes them down to:
  - `memo.name`
  - `relatedMemo.name`
  - `type`
- calls `PATCH /api/v1/memos/{memo}/relations`

Because the importer preserved memo IDs in stage 1, relation targets can be reused directly.

### Resume Behavior

The importer writes `<bundle>.import-state.json` as it progresses.

The state file tracks:

- created memos
- skipped memos
- uploaded attachments
- applied relations
- failures

Re-running the importer on the same bundle will reuse this state file unless you provide a different path.

The importer refuses to reuse a state file if it belongs to:

- a different bundle path
- a different target instance

### Final Report

At the end of an import, the tool writes:

- `<bundle>.import-state.json.report.json`

The report includes:

- start time
- finish time
- target instance
- created memo count
- skipped memo count
- uploaded attachment count
- applied relation count
- failure list

### Known Limitations

- imported memos belong to the authenticated target user
- creator identity is not remapped across users
- reactions are not restored
- share links are not restored
- instance settings are not restored
- overwrite/update-in-place behavior is not implemented
- comment trees are only restored if the bundle already contains comment payloads
- some deployments accept `externalLink` on `CreateAttachment` but persist it as an empty string, which makes external-link attachments non-lossless there

## 简体中文

### 目标

将导出包恢复到目标 Memos 实例，同时保持 memo ID 稳定，并按可控顺序重建 comments、attachments 和 relations。

### 导入阶段

导入器分四个阶段执行：

1. 创建顶级 memo 本体
2. 通过 comment API 创建带父级关系的 memo
3. 对部分创建字段做补丁修正
4. 上传附件
5. 回填 relations

这样的顺序可以避免因为目标 memo 不存在导致 relation 失败，也能保证先有父级再创建 comment，同时补偿某些部署在创建阶段没有保留的 memo 字段，并把附件失败与 memo 创建失败隔离开。

### 第 0 阶段：预检

在任何写操作开始前，导入器会：

1. 使用 `GET /api/v1/auth/me` 校验目标 token
2. 解压 bundle
3. 加载 `manifest.json`
4. 校验必要文件
5. 创建或恢复 import state file
6. 校验现有 state file 是否属于同一个 bundle 路径和目标实例

### 冲突策略

#### fail

如果目标实例中已经存在相同 `memo_id` 的 memo，立即停止。

适用于要求严格、不能接受歧义的迁移场景。

#### skip

如果目标实例中已经存在相同 `memo_id` 的 memo，则保留现有对象并继续执行。

适用于恢复中断任务，或者向已经部分有数据的目标实例补导。

在 `skip` 模式下，导入器仍然会：

- 恢复该 memo 中目标实例尚不存在的导出附件
- 为该 memo 回填导出的 relations

### 第 1 阶段：创建 Memo 本体和 Comments

针对每条 memo payload，导入器会：

- 读取 `memos/<id>.json`
- 对顶级 memo 调用 `POST /api/v1/memos`
- 如果导出 payload 中存在 `parent`，则调用 `POST /api/v1/memos/{memo}/comments`
- 传入原始 `memo_id`
- 恢复：
  - `state`
  - `content`
  - `visibility`
  - `createTime`
  - `updateTime`
  - `displayTime`
  - `pinned`
  - `location`

带 `parent` 的 memo 会被延后，直到其父 memo 已经存在于目标实例中。

relations 在这一阶段不会处理。

### 第 1.5 阶段：修正创建阶段未保留的 Memo 字段

有些部署虽然在 `CreateMemo` 的请求结构里接受 `state` 和 `pinned`，但在创建时并不会稳定持久化它们。

对“本次新建”的 memo，导入器会立即调用 `PATCH /api/v1/memos/{memo}`，并带上 `updateMask=state,pinned` 去修正这两个字段。

这个步骤不会作用于 `skip` 模式下的 memo，因为 `skip` 的语义是保留目标实例里现有 memo 的主体状态。

### 第 2 阶段：上传附件

如果 bundle 的导出模式是 `attachment_mode = embedded_files`，导入器会：

- 读取每个附件条目
- 解析 `exportedPath`
- 对文件内容做 base64 编码
- 调用 `POST /api/v1/attachments`
- 将附件绑定到 `memos/{memo_id}`

对于目标实例中已经存在的 memo，导入器会先索引现有附件 ID，已存在的附件不会重复上传。

如果 bundle 只有元数据：

- 除非附件是 `externalLink`，否则不会恢复附件内容

附件失败会被记录，但不会回滚已创建的 memo。

### 第 3 阶段：回填 Relations

当所有 memo 本体都存在后，导入器会：

- 读取每条 memo payload 中的 relation 定义
- 规范化为：
  - `memo.name`
  - `relatedMemo.name`
  - `type`
- 调用 `PATCH /api/v1/memos/{memo}/relations`

因为第一阶段已经保留了原始 memo ID，所以 relation 目标可以直接复用。

### 续跑行为

导入器在执行过程中会持续写入 `<bundle>.import-state.json`。

state file 会记录：

- 已创建的 memos
- 已跳过的 memos
- 已上传的 attachments
- 已应用的 relations
- failures

如果再次对同一个 bundle 运行导入器，默认会复用这个 state file，除非你显式指定其他路径。

如果这个 state file 属于以下任一情况，导入器会拒绝复用：

- 不同的 bundle 路径
- 不同的目标实例

### 最终报告

导入结束后，工具会写出：

- `<bundle>.import-state.json.report.json`

报告中包含：

- 开始时间
- 结束时间
- 目标实例
- 已创建 memo 数量
- 已跳过 memo 数量
- 已上传附件数量
- 已应用 relation 数量
- failure 列表

### 已知限制

- 导入后的 memo 属于目标实例当前认证用户
- 不支持跨用户 creator 身份映射
- 不恢复 reactions
- 不恢复 share links
- 不恢复实例级设置
- 尚未实现覆盖式更新 / 原地更新
- 只有当 bundle 本身已经包含 comment payload 时，comment 树才能被恢复
- 某些部署虽然接受 `CreateAttachment.externalLink`，但最终会把它持久化为空字符串；在这类实例上，external-link 附件当前不是无损能力
