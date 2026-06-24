# paper-buddy 技术决策记录

这个文档记录 `paper-buddy` 已经实现的关键技术选择。

它和 `DEVELOPMENT_PLAN.md` 的区别：

- `DEVELOPMENT_PLAN.md` 记录未来路线、阶段目标和验收标准。
- `TECHNICAL_DECISIONS.md` 记录已经落地的技术方案、为什么这么选、怎么调用、替代方案和后续风险。

## 0. 第一步：Figure Anchor 检索逻辑

实现时间：阶段 1，规则版 MVP 与 Figure Anchor 基础。

### 0.1 结论

`figure_anchor` 是 `paper-buddy` 的核心亮点之一。

普通 RAG 通常按用户问题去找语义相似文本；`figure_anchor` 则在用户明确问某张图时，围绕该 figure 收集证据链。

它的目标不是直接“看懂图片像素”，而是基于论文文本证据解释 figure：

- figure caption
- 正文中正式讲解该 figure 的段落
- figure 附近上下文
- figure 所在页相关正文
- introduction / conclusion 全局背景

### 0.2 触发条件

当用户问题中包含明确图号时，进入 `figure_anchor` 模式。

支持的输入包括：

```text
图1说了什么？
fig.1讲了什么？
fig .1讲了什么？
figure.1 说了什么？
What does Figure 1 show?
```

代码位置：

```text
paper-guide/src/retriever.py
```

关键函数：

```python
requested_figure_numbers(query)
retrieve_figure_context(...)
```

### 0.3 为什么需要专门的 figure_anchor

如果只用普通关键词检索或向量检索，问“图1说了什么”时容易出现几类问题：

- 只匹配数字 `1`，返回页码、章节号、参考文献等噪声。
- 其他 figure caption 中提到 Figure 1，也会被误认为相关。
- 正文中真正讲 Figure 1 的段落可能被切在很后面。
- Introduction / Conclusion 对 figure 的全文定位不会被补充。

因此，图像问题需要特殊逻辑，而不是完全依赖普通 RAG。

### 0.4 chunk 类型设计

第一步为 figure anchor 增加了多种 chunk 类型：

- `caption`：figure caption。
- `figure_discussion`：正文中正式介绍某张 figure 的段落，例如 `In Figure 1 we show...`。
- `figure_context`：正文中提到某张 figure 的附近上下文。
- `body`：普通正文。
- `introduction`：引言片段。
- `conclusion`：结论片段。

代码位置：

```text
paper-guide/src/chunker.py
```

### 0.5 检索优先级

当问题明确问某张 figure 时，当前优先级是：

```text
caption > figure_discussion > figure_context > body > conclusion/introduction fallback
```

大致含义：

1. `caption` 是作者对图的直接说明。
2. `figure_discussion` 是正文中正式讲这张图的段落。
3. `figure_context` 是其他提到这张图的局部上下文。
4. `body` 是图所在页附近的普通正文补充。
5. `conclusion` 和 `introduction` 在证据不足时补位，提供全文视野。

### 0.6 Introduction / Conclusion fallback

当 figure anchor 找到的相关片段不足 `top_k=5` 时，系统会补充：

1. 一条 `conclusion`
2. 一条 `introduction`
3. 如果仍不足，再继续补剩余 conclusion / introduction

这样做的原因：

- 引言通常说明研究问题和动机。
- 结论通常说明论文最终主张。
- 它们能帮助理解这张图在全文中的作用。

但它们只是全局背景，不应被当作该 figure 的直接证据。

### 0.7 输入归一化决策

为了让用户自然提问，figure anchor 支持多种图号写法。

已处理的输入变体：

- `图1`
- `fig.1`
- `fig .1`
- `fig 1`
- `figure.1`
- `Figure 1`

这个决策来自实际测试：用户多输入一个空格或中英文混写时，原来的正则会漏识别，导致系统退回普通检索，结果不稳定。

### 0.8 当前 score 的含义

在 `figure_anchor` 中，score 主要是规则优先级，不是模型置信度。

大致分数：

```text
caption:             100 + 关键词重合分
figure_discussion:    75 + 关键词重合分
figure_context:       50 或 35 + 关键词重合分
body:                 几分以内
conclusion:            1.5
introduction:          1.0
```

所以 `figure_anchor` 的 score 更像“证据类型优先级”，而不是语义相似度。

### 0.9 当前局限

`figure_anchor` 仍然是规则系统，不是真正视觉理解。

局限包括：

- 它不能直接看图片像素。
- 它依赖 caption 和正文是否写得清楚。
- PDF 解析错误会影响 caption 和正文定位。
- 有些 figure 的正式讲解不一定以 `In Figure X...` 开头。
- Introduction / Conclusion fallback 可能提供背景，但不一定直接解释该图。

后续改进方向：

- 用向量检索帮助找到与 figure caption 语义相关的正文。
- 用 LLM 生成结构化 figure explanation。
- 未来接入 vision 模型后，再加入真正图像观察。

## 1. 第二步：本地向量检索方案

实现时间：阶段 2，向量检索升级。

### 1.1 结论

当前使用：

- Embedding 框架：`sentence-transformers`
- Embedding 模型：`sentence-transformers/all-MiniLM-L6-v2`
- 向量数据库：`ChromaDB`
- 向量距离：cosine distance
- 本地索引目录：`paper-guide/.chroma/`

### 1.2 为什么选择 sentence-transformers

`sentence-transformers` 是一个常用的句向量/文本向量库，可以直接把一句话或一个段落转成 embedding。

选择原因：

- 本地可运行，不需要 API key。
- 和 Hugging Face 模型生态兼容。
- 接入简单，适合 MVP。
- 后续可以比较容易替换模型。

当前代码位置：

```text
paper-guide/src/embeddings.py
```

核心调用：

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
vectors = model.encode(texts, normalize_embeddings=True)
```

项目中封装为：

```python
embed_texts(texts)
embed_query(text)
```

### 1.3 为什么选择 all-MiniLM-L6-v2

当前模型：

```text
sentence-transformers/all-MiniLM-L6-v2
```

选择原因：

- 小，加载和推理速度较快。
- 常用，资料多，适合 MVP。
- 输出 384 维向量，存储成本低。
- 可以本地运行。
- 对英文论文的普通语义检索够用。

局限：

- 不是专门为物理/天文论文训练的模型。
- 对专业公式、符号、非常细粒度的科学推理能力有限。
- 对中文问题到英文论文的跨语言检索能力不一定最强。

后续可考虑替代：

- `all-mpnet-base-v2`：质量通常更好，但更慢更大。
- `BAAI/bge-small-en-v1.5` 或 `BAAI/bge-base-en-v1.5`：检索常用模型。
- `BAAI/bge-m3`：多语言能力更强，适合中文问题检索英文论文，但更重。
- OpenAI embedding：效果强但需要 API key 和费用。
- 科学论文专用模型，如 SPECTER/SciBERT 系列：可能更适合论文语义，但接入和效果需要单独评估。

### 1.4 如何避免每次联网

第一次使用 `all-MiniLM-L6-v2` 时需要从 Hugging Face 下载模型。

下载完成后，当前代码优先使用本地缓存：

```python
SentenceTransformer(model_name, local_files_only=True)
```

如果本地缓存不存在，再尝试联网下载：

```python
SentenceTransformer(model_name)
```

这样可以避免每次启动应用都卡在 Hugging Face 网络检查上。

### 1.5 为什么选择 ChromaDB

ChromaDB 用来保存和查询向量。

选择原因：

- 本地可运行。
- Python 接入简单。
- 支持保存 document、embedding 和 metadata。
- 适合 MVP 阶段做本地 RAG。
- 后续可以持久化到项目目录。

当前代码位置：

```text
paper-guide/src/vector_store.py
```

当前 collection：

```text
paper_chunks
```

当前持久化目录：

```text
paper-guide/.chroma/
```

`.chroma/` 已加入 `.gitignore`，不会提交到 GitHub。

### 1.6 ChromaDB 中保存什么

每个 chunk 写入 ChromaDB 时保存：

- `document`：chunk 原文
- `embedding`：chunk 向量
- `metadata.paper_id`
- `metadata.index_version`
- `metadata.chunk_index`
- `metadata.page`
- `metadata.chunk_type`
- `metadata.figure_id`
- `metadata.section`
- `metadata.section_title`
- `metadata.paragraph_id`
- `metadata.source_block`
- `metadata.quality_score`
- `metadata.paper_title`

这样查询时可以只在当前论文中搜索：

```python
where={"paper_id": paper_id}
```

### 1.7 paper_id 决策

当前用文件名 + 文件 hash 生成 `paper_id`：

```text
paper_id = safe_filename(filename) + "::" + sha256(pdf_bytes)[:16]
```

代码位置：

```text
paper-guide/src/paper_id.py
```

这样做的原因：

- 同一 PDF 重复上传时可以识别出来。
- 不会重复索引同一篇论文。
- 同名不同内容的 PDF 仍能区分。
- 后续做多论文库和论文关联时可以复用。

### 1.8 当前检索分流逻辑

当前 `app.py` 中的检索策略：

1. 如果问题中明确包含图号，例如 `图1`、`fig.1`、`figure 1`：
   - 使用 `figure_anchor`
   - 走第一步构建的规则检索逻辑
2. 否则：
   - 使用 hybrid retrieval
   - 同时召回 vector 候选和 keyword 候选
   - 合并、去重、重排后返回
3. 如果 hybrid 检索失败或没有结果：
   - fallback 到关键词检索

也就是说：

```text
figure question -> figure_anchor
ordinary question -> hybrid(vector + keyword)
hybrid failed -> keyword_fallback
```

代码位置：

```text
paper-guide/src/hybrid_retriever.py
```

Hybrid retrieval 初版逻辑：

1. 从 ChromaDB 取 `vector top N`。
2. 从本地关键词检索取 `keyword top N`。
3. 按 page、chunk_type、figure_id、text 合并同一 chunk。
4. 去掉高度重叠文本。
5. 根据以下因素重排：
   - vector score
   - keyword score
   - 是否同时被 vector 和 keyword 找到
   - `quality_score`
   - chunk_type 是否是直接正文证据
6. 前端显示诊断信息：
   - `source`
   - `vector_score`
   - `keyword_score`
   - `matched_terms`
   - `why_selected`

### 1.9 当前 score 的含义

向量检索中，ChromaDB 返回的是 distance。

当前为了前端显示，把 distance 转成简单 score：

```python
score = 1 / (1 + distance)
```

因此：

- score 越高，表示向量距离越近。
- 它不是模型置信度。
- 它只用于排序和调试。

Hybrid retrieval 中显示的最终 score 是重排分数，不是单纯向量相似度。

它混合了：

- vector score
- keyword score
- quality score
- hybrid bonus
- 少量 chunk_type bonus

因此 hybrid score 只能用于同一次检索内部排序，不应被理解成绝对置信度。

### 1.10 当前阶段边界

第二步完成后，系统可以更聪明地找到语义相关原文 chunks。

但它仍然不能生成流畅回答。

当前输出仍然是：

- 原文 chunk
- page
- chunk_type
- figure_id
- score
- source

自然语言总结、引用整合和证据不足判断要到阶段 3 的 LLM 回答模块实现。

### 1.11 Chunk 切分质量改进

阶段 2 中对 chunker 做了轻量改进：

- 从字符级 overlap 改为句子级 overlap，减少半句话开头或结尾。
- 增加 `quality_score`，用于标记 chunk 的可读性和完整度。
- 过滤常见页眉页脚，例如页码、期刊页脚。
- 对明显跨页续接的正文 block 做保守合并，再切成完整句子。

跨页合并规则保持谨慎：

```text
前一个正文 block 没有完整句末标点
+ 下一个正文 block 明显以续接词开头
=> 合并后再切句
```

这能缓解 PDF 换页导致的半句开头问题，但不是完整的版面重建。双栏论文、公式、脚注和复杂排版仍可能让 PyMuPDF 的 block 顺序不完美。后续如果需要更高质量的版面恢复，可以进一步引入坐标级 block 排序、段落重建和 `bbox` metadata。

## 2. 当前暂不引入 LangChain

实现时间：阶段 2，向量检索和 metadata 打磨期间。

### 2.1 结论

当前项目暂不使用 LangChain。

目前 `paper-buddy` 采用自己实现的轻量 RAG pipeline：

```text
PyMuPDF 解析 PDF
-> figure_extractor 提取 Figure caption
-> chunker 切分 chunk 并生成 metadata
-> sentence-transformers 生成 embedding
-> ChromaDB 保存和查询向量
-> retriever / vector_store 执行 figure_anchor、vector、keyword fallback 检索
-> Streamlit 展示结果
```

### 2.2 为什么现在不使用 LangChain

LangChain 是一个功能很强的 LLM 应用框架，但当前阶段不引入它，原因是：

- 项目还在打基础，需要清楚看见每一步如何工作。
- 当前重点是论文结构、figure anchor、chunk metadata 和检索策略，不是通用聊天链路。
- 过早引入框架会增加 `Document`、`TextSplitter`、`Retriever`、`Chain`、`Runnable` 等抽象，学习成本和调试成本都会上升。
- 我们需要保留对 `figure_anchor` 的强控制权，因为这是项目特色，不是标准 RAG 模板能直接覆盖的部分。
- 当前依赖已经能完成 MVP：PyMuPDF、sentence-transformers、ChromaDB 和 Streamlit 足够支撑第二步。

### 2.3 这个决策的好处

暂不使用 LangChain 的好处是：

- 系统结构透明，方便学习和调试。
- 每个模块职责清楚，适合逐步理解 RAG。
- 自定义检索逻辑更自由，例如 figure anchor、Introduction / Conclusion fallback、chunk quality score。
- 减少框架升级、版本兼容和抽象泄漏带来的额外复杂度。

### 2.4 代价和风险

不使用 LangChain 也有代价：

- 需要自己维护 prompt、retriever、context builder 等模块。
- 后续接入多个 LLM provider 时，需要自己设计统一接口。
- 如果工作流变复杂，例如多轮 agent、工具调用、文献搜索链路，手写代码可能会变得分散。

### 2.5 后续什么时候重新评估

后续可以在这些场景下重新评估是否引入 LangChain，或只借鉴它的设计：

- 需要同时支持 OpenAI、DeepSeek、Claude、本地模型等多个 LLM provider。
- 需要复杂 prompt 模板管理。
- 需要多轮对话记忆。
- 需要把检索、重排、回答、工具调用串成更复杂的 workflow。
- 需要接入外部文献搜索、参考文献网络、数据库、网页搜索等工具。

即使未来引入 LangChain，也不应替代项目自己的核心逻辑：

```text
figure_anchor 检索
论文结构 metadata
图像锚点讲解流程
论文与论文/用户项目之间的关联建模
```

这些仍然应该作为 `paper-buddy` 的自定义能力保留下来。

## 3. 第三步：DeepSeek 证据化问答

实现时间：阶段 3，基础 LLM 回答模块。

### 3.1 Provider 与配置

当前首先接入 DeepSeek：

```text
API key: DEEPSEEK_API_KEY
Model: DEEPSEEK_MODEL
Base URL: DEEPSEEK_BASE_URL
```

默认配置：

```text
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

使用 OpenAI Python SDK 调用 DeepSeek 的 OpenAI 兼容接口。Provider 配置放在环境变量中，避免把模型名称和 API key 写死在业务逻辑里。

### 3.2 为什么使用受控 Evidence ID

不让模型直接猜测页码。系统先把上下文证据编号为：

```text
E1
E2
E3
```

模型只能在回答中引用 `[E1]`。回答返回后，程序根据 metadata 将其转换为：

```text
[E1 · Page 8 · body]
```

这个设计有三个目的：

- 页码和 chunk 类型来自程序，不来自模型记忆或猜测。
- 用户可以在下方核查对应原文。
- 后续能用 `evidence_id + chunk_id + page + bbox` 实现 PDF 跳转和原文高亮。

### 3.3 Context 选择

第一版不会把所有候选 chunks 全部发给模型。

当前策略：

- 默认最多选择 10 条证据。
- 默认上下文正文不超过约 14,000 个字符。
- 综合检索排名、retrieval score、`quality_score` 和 `chunk_type`。
- 去掉相同 `chunk_id` 的重复证据。
- 最终按用户在检索结果中看到的顺序编号，便于核查。

更多 context 不一定更可靠。大量低相关片段会增加成本、干扰模型判断，并提高错误引用的概率。

证据类型加分会根据问题类型调整：

- 明确 Figure 问题：优先 `caption / figure_discussion / figure_context`。
- 整篇论文总结问题：优先 `conclusion / introduction / body`。
- 普通概念、原因、比较问题：优先直接相关的 `body`，Introduction / Conclusion 作为补充。

类型加分只用于候选之间的轻量重排，不能取代检索相关性。

### 3.4 模块边界

代码位置：

```text
paper-guide/src/qa_engine.py
```

职责包括：

- 检查 DeepSeek 配置。
- 选择上下文证据。
- 构建带 metadata 的 context。
- 调用 LLM。
- 提取和渲染引用。

检索逻辑仍由 `retriever.py`、`hybrid_retriever.py` 和 `vector_store.py` 负责。QA engine 不重新实现检索。

### 3.5 Streamlit 调用时机

只有用户点击“生成回答”按钮时才调用 API。

回答保存到 `st.session_state`，避免普通 Streamlit rerun 因展开结果、调整控件等操作重复调用并产生费用。

没有 `DEEPSEEK_API_KEY` 时：

- 生成按钮不可用。
- 应用继续显示检索结果。
- PDF 解析、向量检索和 figure anchor 不受影响。
