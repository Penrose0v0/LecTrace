# LecTrace — 项目概要

## 一句话简介

LecTrace 是一个面向课堂 / 讲座场景的**听讲辅助网页**：实时把讲话内容转录成文字，当听讲者走神或跟不上时，点一下 **"Catchup"**，由 LLM 立即总结最近一段时间的讲课内容，帮助其快速回到进度。

## 背景与要解决的问题

在课堂、研讨会、线上会议等实时讲授场景中，听讲者经常会有短暂的走神、查资料、记笔记，等回过神来时已经错过了一段内容，很难在不打断讲者的情况下补上。

LecTrace 的核心思路是：**转录一直在后台进行，但摘要按需触发**。用户不需要通读全部转录文本，只要在"掉线"之后点一次 Catchup，就能拿到"你刚才错过的这几分钟讲了什么"的精炼总结。

## 核心功能

### 1. 实时转录（Live Transcription）
- 持续采集音频并转成文字，形成带时间戳的转录流。
- 前端实时展示滚动的转录文本。

### 2. Catchup（核心特性）
- 用户点击 Catchup 按钮，系统取出**最近 X 分钟**内的转录内容（时间窗口**用户可调**，在前端设置）。
- 调用 LLM 对该时间段内容做快速摘要，返回"要点 / 你错过了什么"。
- 目标是**低延迟**：从点击到出摘要要尽量快，因为它是在"实时追赶"的场景下使用的。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | Web 网页（音频采集 + 实时转录展示 + Catchup 交互） |
| 后端 | Python（`backend/`），STT 代理 + Catchup 摘要 API |
| 语音转录 | **Google Cloud Speech-to-Text**（Cloud Run 代理调用 streaming API） |
| LLM / 摘要 | **Gemini API** |
| 状态存储 | **Firestore**（转录段落 + 会话状态） |
| 部署 | **Google Cloud Run** |

> 注：本仓库正在**重构**中，`README.md` 描述的是旧版本，不代表当前设计方向。以本文件为准。

## 数据流与职责划分

转录经由**后端代理**完成：前端通过 WebSocket 把音频流发给 Cloud Run，后端再转发给 Google Cloud Speech-to-Text 的 streaming API，识别结果沿原路回传给前端。GCP 凭证只留在后端，客户端不接触任何长期密钥。

1. **采集与转录（前端 → Cloud Run WebSocket → STT）**：前端采集麦克风音频，经 WebSocket 上行到 Cloud Run；后端代理调用 Speech-to-Text streaming API，把带时间戳的转录结果实时推回前端滚动展示。
2. **持久化（后端 → Firestore）**：转录段落（文本 + 时间戳）写入 Firestore，按会话组织，作为 Catchup 的数据源。
3. **Catchup（前端 → 后端 → Gemini）**：用户点击 Catchup 并带上所选时间窗口 X，后端从 Firestore 取该会话最近 X 分钟的段落，调用 Gemini API 生成摘要并返回。

## 部署

- 目标平台：**Cloud Run**（容器化、按需伸缩）——需支持 WebSocket 长连接来承载音频流代理。
- Gemini API 密钥、GCP 项目等配置通过环境变量注入（见 `.env.example`）；STT 凭证仅存在于后端。
- 转录状态落在 Firestore，服务本身不保存会话数据。

## 架构草图

```
麦克风
  │ (音频流)
  ▼
前端网页 ──WebSocket(音频)──► 后端服务 (Cloud Run) ──streaming──► Speech-to-Text
  │  ▲                              │      ▲                          │
  │  └──── 转录结果(WS) ────────────┘      └──── 转录结果 ─────────────┘
  │                                 │
  │                                 │ 写入转录段落 (文本+时间戳)
  │                                 ▼
  │                              Firestore (会话 / 转录段落)
  │                                 ▲
  │  点击 Catchup(窗口 X)            │ 取最近 X 分钟段落
  │                                 ▼
  └──── 摘要结果 ◄──── 调 Gemini API 生成摘要
```

## 待定项 / 设计决策

- **时间窗口 X 的语义**：是纯粹"最近 X 分钟"，还是可结合"上次 Catchup 时间点"给出更贴合的区间。
- **写入路径**：转录段落是逐句实时写 Firestore，还是节流/批量后再写，以控制写入量与成本。
- **WebSocket 会话管理**：连接与 Firestore 会话如何对应、断线重连后如何续接转录流。

## 目录结构（重构目标）

```
LecTrace/
├── backend/      # Python 后端服务（转录 + Catchup 摘要 API）
├── frontend/     # 网页前端
├── docs/         # 项目文档（本文件所在处）
└── ...
```
