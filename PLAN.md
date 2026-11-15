# CourseMate 技术方案

## 1. 目标与功能边界

**目标：做一个基于课程 PDF 的学习助手，完成“上传资料 → 有依据地问答 → 生成练习 → 查看结果”的完整流程。**

已确认：Vue 前端、Python 后端；千问向量模型和 DeepSeek 均调用云端 API；本地单用户演示，无注册登录。以下限制是第一版工程范围，不是课程额外要求。

| 核心功能 | 第一版范围 | 完成表现 |
|---|---|---|
| 课程资料 | 上传、列出、查看和删除文字型 PDF | 上传成功后可以用于问答和出题 |
| 课程问答 | 在所选资料内检索、多轮追问、中英文输入、流式回答 | 答案附真实文件名、PDF 页码和原文片段；资料不足时说明无法确定 |
| 选择题练习 | 指定资料和主题，每次生成 3 道四选一单选题 | 提交后由程序判分，显示正确答案、解析和来源 |
| 历史记录 | 保存聊天和练习结果 | 刷新页面、重启服务后仍可查看 |

不纳入：OCR、图片/图表理解、语音、虚拟人、模型训练、多用户权限、联网搜索、复杂错题复习和云端部署。

文字提取不保证保留复杂表格及公式语义。无可提取文字的 PDF 拒绝导入；混合 PDF 跳过无文字页，并向用户提示。演示使用事先检查过的课程资料。

## 2. 技术栈与整体架构

| 部分 | 技术 | 用途 |
|---|---|---|
| 前端 | Vue 3、TypeScript、Vite | 页面及构建 |
| 前端配套 | Vue Router、Pinia、Element Plus | 路由、会话状态、基础组件 |
| 通信 | 原生 Fetch；聊天使用 SSE | 普通 JSON 请求、逐步显示答案 |
| 后端 | Python 3.11、FastAPI、Uvicorn | 单个后端进程提供全部接口 |
| 数据校验 | Pydantic、pydantic-settings | 请求/模型输出校验、配置读取 |
| 业务数据 | SQLite、SQLAlchemy 2 | 会话、消息、文档信息、练习记录 |
| 向量索引 | Chroma PersistentClient | 本地持久化、按文档过滤检索 |
| PDF | PyMuPDF | 按页提取文字 |
| 向量模型 | 百炼 `text-embedding-v4`，1024 维 | 文档和问题向量化 |
| 生成模型 | DeepSeek `deepseek-flash` | 课程回答、生成题目和解析 |
| API 客户端 | Python `openai` 客户端 | 分别连接百炼和 DeepSeek 的兼容接口 |
| 验证与协作 | pytest、人工评估集、Git | 核心逻辑测试、质量评估、版本管理 |

`text-embedding-v4` 属于 Qwen3 Embedding 系列；使用其云端 API，无需下载模型。[百炼接口文档](https://www.alibabacloud.com/help/en/model-studio/embedding-interfaces-compatible-with-openai)

DeepSeek 模型名采用当前官方接口名称，并通过环境变量配置；两个客户端分别使用自己的地址和密钥。[DeepSeek 接入文档](https://api-docs.deepseek.com/)

```text
浏览器中的 Vue
       │ HTTP / SSE
       ▼
FastAPI：路由 → 业务服务
       ├── SQLite：业务记录
       ├── 本地目录：原始 PDF
       ├── 千问 Embedding → Chroma：资料检索
       └── DeepSeek：根据检索资料回答、出题
```

仅运行一个前端开发服务和一个后端进程。直接编写 RAG 流程，不引入 Agent 框架、消息队列、Redis 或微服务。数据库以内嵌方式运行。

## 3. 前端代码架构

```text
frontend/
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── router.ts
│   ├── api/
│   │   ├── client.ts           # JSON 请求、错误处理、SSE 读取
│   │   ├── documents.ts
│   │   ├── chat.ts
│   │   └── quizzes.ts
│   ├── stores/chat.ts         # 当前会话、消息、生成状态
│   ├── views/
│   │   ├── DocumentsView.vue  # 上传、列表、导入结果
│   │   ├── ChatView.vue       # 资料选择、历史会话、聊天
│   │   └── QuizView.vue       # 出题、答题、历史结果
│   ├── components/
│   │   ├── MessageItem.vue
│   │   ├── SourceCard.vue     # 文件名、页码、原文、PDF 链接
│   │   └── QuizQuestion.vue
│   ├── types.ts              # 与后端字段对应的类型
│   └── style.css
├── package.json
├── package-lock.json
└── vite.config.ts
```

- 页面只负责交互，API 调用集中到 `api/`；业务事实以服务端为准。
- 新会话先选择资料，之后资料范围固定；更换资料时新建会话。
- 出题页面输入主题、选择资料和语言，数量固定为 3 道，减少配置。
- 上传、生成和提交期间显示进度状态并阻止重复点击；失败显示可操作的错误。
- SSE 按事件边界解析，不能假设一次网络读取就是完整事件；仅收到 `done` 才视为回答完成。
- 回答先以纯文本展示，保留换行；引用独立展示为来源卡片。

## 4. 后端代码架构

```text
backend/
├── app/
│   ├── main.py               # 应用入口、路由、异常处理
│   ├── config.py             # 环境变量与默认配置
│   ├── db.py                 # SQLite 引擎、Session、建表
│   ├── models.py             # SQLAlchemy 表定义
│   ├── schemas.py            # 请求、响应及出题结构
│   ├── routers/
│   │   ├── documents.py
│   │   ├── conversations.py
│   │   ├── chat.py
│   │   └── quizzes.py
│   ├── services/
│   │   ├── documents.py      # 文件校验、提取、分块、索引与删除
│   │   ├── rag.py            # 检索、上下文组装、回答和引用
│   │   └── quizzes.py        # 出题校验、判分、保存结果
│   ├── clients/
│   │   ├── embedding.py      # 千问 API
│   │   └── llm.py            # DeepSeek API
│   ├── vector_store.py       # Chroma 写入、过滤查询、删除
│   └── prompts.py            # 问答、出题提示词
├── tests/
├── requirements.txt
└── .env.example
```

调用方向：`router → service → 模型客户端 / 数据库`。路由负责输入输出，服务负责业务规则；SQLAlchemy 和 Chroma 的细节不进入前端。

### 4.1 资料导入

1. 单次上传一个 PDF，默认限制 20 MB、100 页；校验真实 PDF 格式和可提取文本。
2. 使用 UUID 保存文件；按页提取，保留从 1 开始的 **PDF 物理页码**。
3. 以段落为优先边界，初始设置每段最多 800 字符、重叠约 100 字符，不跨页切块。
4. 分批调用千问，每批最多 10 段；验证向量数量及维度后写入 Chroma。
5. 索引全部成功后写入 SQLite 文档记录并返回成功。失败时清理本次文件与向量，不留下可查询的半成品。

第一版采用请求内完成导入，前端等待结果，不增加后台任务队列。导入请求总时限设为 180 秒；达到时限则失败清理，提示拆分文件后重试。批量上限以所选地域的官方接口限制为准。

### 4.2 问答与引用

1. 校验会话及其资料仍存在；使用上一条用户问题和当前问题构造检索文本，支持简单指代追问。
2. 用千问生成问题向量，按当前会话的文档 ID 过滤，使用余弦距离取最相关的 5 段。
3. 将当前问题、最近 3 轮完整对话、相关片段交给 DeepSeek；片段编号为 `S1`、`S2` 等。
4. 要求基于片段回答，以 `[S1]` 标记依据；资料不足时说明无法确定。资料内容仅作为证据，不作为系统指令。
5. 流式发送正文。结束后检查引用编号属于本次检索结果；文件名、页码、原文由后端元数据生成。
6. 将完整问答及引用快照放在同一个 SQLite 事务保存，再发送 `done`。断流或引用编号无效时发送错误，不保存为成功回答。

检索永远会返回“相对接近”的内容，不能以有结果就认定能回答。第一版结合提示词和未覆盖问题评估处理资料不足，不把相似度展示成置信度。引用编号合法不代表内容正确，仍需人工检查证据是否支持结论。

Chroma 显式传入 `embeddings` / `query_embeddings`，不启用默认向量模型；文档与问题必须使用同一模型、维度。更换向量配置须新建索引并重新导入资料。[Chroma 查询文档](https://docs.trychroma.com/docs/querying-collections/query-and-get)

### 4.3 出题与判分

- 根据所选文档和主题检索资料，请 DeepSeek 返回 3 道题的 JSON。
- 模型返回 `stem、options(A–D)、correct_option、explanation、source_ids`；后端为每题分配 UUID，并保存对应来源快照。
- Pydantic 检查题目数量、四个非空选项、正确选项范围、引用编号合法性；校验失败只重试一次，仍失败则明确报错。
- 无有效资料或模型判断资料不足时返回 `422 INSUFFICIENT_CONTEXT`，提示更换主题，不强行生成题目。
- 创建及查看未提交练习的接口只返回题干、选项，不返回答案、解析或来源提示。
- 提交必须包含全部题目的合法选项。后端读取已保存的标准答案直接比较，不再调用模型判分。
- 每份练习只提交一次；重复提交返回已保存结果，避免重复记录。之后可查看正确答案、解析及引用。

## 5. 数据库与文件架构

### 5.1 SQLite：业务数据

所有主键使用 UUID 字符串，时间保存为 UTC。数组和嵌套结构使用 JSON 字段，第一版不拆出额外关联表。

| 表 | 核心字段 | 关系/约束 |
|---|---|---|
| `documents` | `id, filename, file_path, page_count, chunk_count, created_at` | 只记录已完成导入的文档 |
| `conversations` | `id, title, document_ids, created_at` | 创建时校验文档，范围固定 |
| `messages` | `id, conversation_id, role, content, citations, created_at` | `conversation_id` 外键；按会话、时间查询 |
| `quizzes` | `id, document_ids, topic, language, questions, created_at` | `questions` 含标准答案，仅后端可读取完整结构 |
| `quiz_attempts` | `id, quiz_id, answers, correct_count, total, created_at` | `quiz_id` 外键且唯一，每套题一个提交结果 |

`citations` 保存 `{source_id, document_id, filename, page, excerpt}` 快照；题目也保存自己的引用快照。开启 SQLite 外键约束，所有响应通过专门的 Pydantic 响应结构输出，避免泄漏答案字段。

### 5.2 Chroma：向量索引

- 一个持久化 collection，名称包含向量模型和维度标识。
- 每条记录：`id = document_id:page:chunk_index`、`document = 文本片段`、`embedding = 1024 维向量`。
- 元数据：`document_id、filename、page、chunk_index`；检索必须按 `document_id` 过滤。

### 5.3 本地存储与删除

```text
data/
├── app.db                    # SQLite
├── uploads/<document_id>.pdf # 原始文件
└── chroma/                   # 向量索引
```

删除资料按“清理向量 → 清理原文件 → 删除 SQLite 文档记录”执行，步骤允许重试；失败不返回成功。聊天及练习快照保留，原文件链接标记为不可用。引用了已删除资料的会话不可继续发送问题，提示重新选择资料创建会话；历史练习仍按已保存题目判分。

## 6. 核心接口

统一前缀 `/api`；除文件及 SSE 外使用 JSON。资源 ID 使用 UUID，来源编号使用 `S1` 等标识；请求不接受客户端传入本地路径。

| 方法与路径 | 请求 | 成功结果 |
|---|---|---|
| `GET /health` | 无 | `200 {status:"ok"}`，只检查应用存活 |
| `POST /documents` | multipart `file` | `201` 文档信息、片段数、无文字页提示 |
| `GET /documents` | 无 | `200` 文档列表 |
| `GET /documents/{id}/file` | 无 | `200` PDF；前端以 `#page=N` 打开来源页 |
| `DELETE /documents/{id}` | 无 | `204` |
| `POST /conversations` | `{document_ids:[...]}`，1–5 个 | `201 {id,title,document_ids}` |
| `GET /conversations` | 无 | `200` 历史会话列表 |
| `GET /conversations/{id}/messages` | 无 | `200` 按时间排序的消息及引用 |
| `POST /chat` | `{conversation_id,message}`，1–2000 字符 | `200 text/event-stream` |
| `POST /quizzes` | `{document_ids:[...],topic,language}`；1–5 份资料，主题 1–200 字符，语言 `zh/en` | `201 {id,questions:[{id,stem,options}]}` |
| `GET /quizzes` | 无 | `200` 练习摘要及是否已提交 |
| `GET /quizzes/{id}` | 无 | `200` 题目；已提交时附结果、解析和来源 |
| `POST /quizzes/{id}/submit` | `{answers:[{question_id,option}]}` | `200` 分数及逐题结果；重复提交返回原结果 |

流式事件约定，使用 Fetch POST 后读取响应流：

```text
event: delta
data: {"text":"A* 搜索……"}

event: done
data: {"message_id":"uuid","citations":[{"source_id":"S1","document_id":"uuid","filename":"lecture.pdf","page":5,"excerpt":"原文片段"}]}

event: error
data: {"code":"MODEL_TIMEOUT","message":"生成超时，请重试"}
```

`done` 与 `error` 为互斥的终止事件。网络断开且未收到 `done` 时标记未完成；可重新加载会话历史确认是否已保存。后端每个会话只允许一个正在生成的请求，其余返回 `409`。

普通错误统一为 `{error:{code,message}}`：无效参数 `422`、文件过大 `413`、资源不存在 `404`、状态冲突 `409`、模型调用失败 `502`、超时 `504`。已开始 SSE 后使用 `error` 事件，不能再修改 HTTP 状态。FastAPI 可通过流式响应实现此协议。[官方说明](https://fastapi.tiangolo.com/advanced/custom-response/)

## 7. 配置与运行

后端 `.env`：

```dotenv
DASHSCOPE_API_KEY=填写自己的密钥
DASHSCOPE_BASE_URL=填写百炼控制台中与账号地域匹配的兼容接口地址
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
DEEPSEEK_API_KEY=填写自己的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DATA_DIR=../data
```

- 路径相对后端目录解析。真实 `.env`、`data/`、缓存和依赖目录加入 `.gitignore`，仅提交 `.env.example`。
- 两种 API Key 只放后端；前端仅请求 `/api`。API 调用需要联网及可用额度。
- 开发：Vite 使用 `127.0.0.1:5173`，将 `/api` 代理到 `127.0.0.1:8000`；Uvicorn 单 worker 运行，无需额外 CORS 配置。
- 后端模型请求设置超时，问答/出题总时限 90 秒；错误直接反馈，避免无限重试。同步 PDF、SQLite、Chroma 操作放入线程池，避免阻塞流式接口。
- 演示：Vue 构建后由 FastAPI 提供静态文件及 SPA 回退，API 路由优先；浏览器只访问本机一个地址。
- Python 依赖在首轮运行验证后固定版本；前端提交锁文件。README 写清安装、配置和启动命令。

## 8. 开发任务与验收

依赖顺序：**Task 1 → Task 2 → Task 3 → Task 4 → Task 5**。每个任务交付可运行的前后端闭环，不只完成界面或孤立接口。

### Task 1：搭建最小可运行工程

**核心任务：**建立 Vue 三个页面和 FastAPI 目录；配置代理、SQLite 表、Chroma 持久化及两个模型客户端；确定响应类型。

**验收标准：**

- 按 README 在新环境启动前后端，三个页面可访问，前端成功请求 `/api/health`。
- 数据目录及五张表可自动初始化，重启不清空已有数据。
- 千问返回 1024 维向量，DeepSeek 返回一条测试回复；失败时可定位到缺失配置或 API 错误。
- 密钥不出现在前端代码、浏览器响应或版本库中。

### Task 2：完成 PDF 知识库

**核心任务：**上传界面、PDF 校验与分块、千问批量向量化、Chroma 写入/过滤查询、文件查看和删除。

**验收标准：**

- 导入至少 2 份课程 PDF，重启后仍可列出和检索；原文片段的页码与 PDF 一致。
- 指定文档检索不会返回另一份未选资料的片段。
- 超限、非 PDF、纯扫描 PDF 有明确错误；模拟 API 失败后无可用的半成品，重传可成功。
- 删除后原文件和对应向量不可访问，历史引用按第 5 节处理。

### Task 3：完成带引用的多轮问答

**核心任务：**创建会话、文档范围过滤、DeepSeek 流式输出、引用卡片、聊天持久化及错误处理。

**验收标准：**

- 可执行“提问 → 答案 → 点击来源 → 追问 → 刷新恢复历史”的完整流程。
- 准备 5 个有资料依据的问题、2 个简单追问、3 个资料未覆盖的问题；人工核对答案和资料不足提示，记录结果。
- 成功回答的引用编号均合法，文件/页码来自后端元数据；人工检查引用确实支持答案。
- 模拟断流、超时和无效引用，不把未完成回答保存成成功记录；生成结束后可以继续使用。

### Task 4：完成选择题练习

**核心任务：**按主题出题、JSON 校验、答题界面、确定性判分、结果和历史展示。

**验收标准：**

- 至少两个主题能各生成 3 道合法单选题，人工确认题意、答案和引用依据。
- 提交前 API 响应中不存在正确答案和解析；提交后显示分数、逐题结果及来源。
- 用固定题目验证全对、全错、部分正确；缺题、重复题号及非法选项被拒绝。
- 重复提交不重复记分，刷新及重启后可查看相同结果；非法模型 JSON 重试一次后仍失败会明确报错。

### Task 5：联调、评估与提交准备

**核心任务：**修复完整链路、运行关键测试、形成评估记录、整理 README 与展示材料。

**验收标准：**

- 使用至少 2 份 PDF 完成“导入 → 问答 → 追问 → 引用核对 → 练习 → 历史查询”，重启后数据仍一致。
- pytest 覆盖文档过滤/失败清理、引用编号校验、出题校验、答案隐藏、判分与重复提交；模型调用在自动测试中使用替身。
- 建立 20 条人工评估问题：12 条可回答、4 条追问、4 条未覆盖；记录预期依据、实际答案、引用支持情况及耗时。验收目标分别为至少 10 条回答正确且依据支持、3 条正确理解追问、3 条明确说明资料不足；未达标先修复再复测，不虚构结果。
- 前端构建通过；按 README 在另一台电脑或全新环境运行，并完成一次真实 API 演示。
- README 包含全部组员姓名/学号、扩展功能、启动方式和限制；准备源代码 ZIP、PPTX、7 分钟英文演示及问答材料。打包不包含真实密钥和依赖目录。

**交付完成的判断：核心流程稳定、引用可核对、练习可判分、说明可复现。新增功能不作为本轮完成条件。**
