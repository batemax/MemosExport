# Memos Export/Import Plan

[English](#english) | [简体中文](#简体中文)

## English

### Goal

Provide a practical migration path for Memos instances without relying on the removed built-in export UI.

The workflow is:

- export memos into a structured `zip` bundle
- move the bundle elsewhere
- import the bundle into a target Memos instance

This is a replayable content migration workflow, not a full disaster-recovery backup of the entire instance.

### Design Principles

#### Preserve memo IDs

The importer keeps original memo IDs by using the `memoId` create parameter. This is the critical requirement for restoring relations and internal references reliably.

#### Import in phases

The importer rebuilds data in four passes:

1. top-level memo bodies
2. parented memos through the comment API
3. attachments
4. relations

This keeps failures localized and makes resume behavior simpler.

#### Make bundles self-describing

Every export bundle includes a `manifest.json` that records:

- format version
- source instance
- source user
- bundle mode
- exported items
- export warnings

#### Support interruption and replay

The importer writes a state file and a final report file so long-running imports can be resumed or audited. State files are bound to one bundle path and one target instance so an old run cannot be replayed against the wrong destination.

### API Usage

Export primarily uses:

- `GET /api/v1/auth/me`
- `GET /api/v1/memos`
- `GET /api/v1/memos/{memo}`
- `GET /api/v1/memos/{memo}/attachments`

Import primarily uses:

- `POST /api/v1/memos`
- `POST /api/v1/memos/{memo}/comments`
- `POST /api/v1/attachments`
- `PATCH /api/v1/memos/{memo}/relations`

Attachment file bytes are downloaded through:

- `/file/attachments/{attachmentId}/{filename}`

This route matters because some Memos deployments return attachment metadata through the public API while leaving `content` empty.

### Supported Data

Version 1 exports and imports:

- memo content
- memo timestamps
- memo visibility
- pinned state
- location
- archived vs normal state
- attachment metadata
- attachment files
- memo relations

Version 1 imports comment memos represented by the exported `parent` field.

### Not Supported Yet

Version 1 does not attempt to preserve or restore:

- cross-user creator identity
- reactions
- share links
- instance settings
- full user/account migration

### Risks

#### Creator identity cannot be preserved automatically

Memos creates imported content under the authenticated target user. Imported memos therefore belong to the token owner in the target instance.

#### Attachment behavior varies by deployment

Some deployments expose attachment bytes only through the file route, not through JSON metadata APIs. The exporter therefore treats attachment downloads as an explicit data path, not an optional nicety.

Some deployments also accept `CreateAttachment.externalLink` in the schema but persist it as an empty string. On those deployments, external-link attachments are not lossless.

#### Comment export depends on list behavior

The current exporter walks `ListMemos`. If a deployment does not include comment memos in that list response, the exporter cannot reconstruct a full comment tree yet.

#### Relations depend on stable memo IDs

If the importer fails to preserve original memo IDs, relations break. This is why memo creation is always phase one and why `memoId` is treated as required for replayability.

### Success Criteria

The tool is considered successful when:

- the export bundle is portable and self-contained
- memo content imports correctly into a new instance
- attachments can be restored when exported
- relations still resolve after import
- interrupted imports can be resumed safely
- an old state file cannot be silently reused for a different bundle or target

## 简体中文

### 目标

在不依赖已移除的内建导出 UI 的前提下，为 Memos 实例提供一条实际可用的迁移路径。

整体流程是：

- 将 memo 导出为结构化 `zip` 包
- 把导出包移动到其他环境
- 再导入到目标 Memos 实例

这是一套可回放的内容迁移方案，不是完整的实例级灾备备份。

### 设计原则

#### 保留 memo ID

导入器通过 `memoId` 创建参数保留原始 memo ID。这是恢复 relations 和内部引用的关键前提。

#### 分阶段导入

导入器分四个阶段恢复数据：

1. 顶级 memo 本体
2. 通过 comment API 创建带 `parent` 的 memo
3. 附件
4. relations

这样可以把失败范围局部化，也更容易实现断点续传。

#### 让导出包自描述

每个导出包都包含一个 `manifest.json`，用于记录：

- 格式版本
- 来源实例
- 来源用户
- bundle 模式
- 导出条目
- 导出警告

#### 支持中断和重放

导入器会写入 state file 和最终 report file，方便长任务中断后继续执行或事后审计。state file 会绑定到单一 bundle 路径和单一目标实例，避免旧状态被错误复用。

### API 使用范围

导出主要使用：

- `GET /api/v1/auth/me`
- `GET /api/v1/memos`
- `GET /api/v1/memos/{memo}`
- `GET /api/v1/memos/{memo}/attachments`

导入主要使用：

- `POST /api/v1/memos`
- `POST /api/v1/memos/{memo}/comments`
- `POST /api/v1/attachments`
- `PATCH /api/v1/memos/{memo}/relations`

附件文件字节通过以下路径下载：

- `/file/attachments/{attachmentId}/{filename}`

这条路径之所以重要，是因为某些 Memos 部署虽然会通过公开 API 返回附件元数据，但 `content` 字段是空的。

### 当前支持的数据

第一版支持导出和导入：

- memo 内容
- 由导出 `parent` 字段表示的 comment memo
- memo 时间戳
- memo 可见性
- pinned 状态
- location
- archived / normal 状态
- 附件元数据
- 附件文件
- memo relations

### 暂不支持

第一版暂不尝试保留或恢复：

- 跨用户 creator 身份
- reactions
- share links
- 实例级设置
- 完整用户/账号迁移

### 风险点

#### 无法自动保留 creator 身份

Memos 会把导入内容归属到目标实例中当前认证用户，因此导入后的 memo 属于 token 持有者，而不是来源实例中的原始用户。

#### 不同部署的附件行为不一致

有些部署只通过文件路由暴露附件字节，不通过 JSON 元数据 API 返回。因此导出器把附件下载视为一条明确的数据路径，而不是可有可无的补充能力。

#### relations 依赖稳定的 memo ID

如果导入器无法保留原始 memo ID，relations 就会失效。这也是为什么 memo 创建总是放在第一阶段，并且 `memoId` 被视为可回放迁移的必要条件。

### 成功标准

如果满足以下条件，就可以认为工具达到了预期：

- 导出包是可移植且自包含的
- memo 内容可以正确导入到新实例
- 已导出的附件可以被恢复
- 导入后 relations 仍然有效
- 中断后的导入可以安全继续
- 旧的 state file 不会被静默复用到别的 bundle 或别的目标实例
