# paper-buddy 第三步计划：LLM 证据化问答

## 1. 阶段目标

第三步要把当前的系统从“返回相关原文 chunks”升级为“基于检索证据生成自然语言回答”。

完整流程将变成：

```text
用户问题
  -> figure_anchor 或 hybrid retrieval
  -> 选择、去重并整理证据 chunks
  -> 把问题和证据交给 LLM
  -> 生成带页码引用的回答
  -> 保留原始检索结果供用户核查
```

本阶段仍然是单篇论文、文本证据版 RAG。暂时不直接分析图片像素，也不开始跨论文关联。

## 2. 用户最终能看到什么

用户上传论文并输入问题后：

1. 系统照常检索论文 chunks。
2. 用户点击“生成回答”。
3. 页面显示一段由 LLM 组织的回答。
4. 回答中的主要判断带有论文证据引用，例如：

```text
作者提出 depletion radius，是为了定义一个与暗物质晕物质耗尽和环境相互作用有关的自然边界。[page 2, body]
```

5. 回答下方继续显示原始 chunks、score 和 metadata，用户可以核对模型是否忠于原文。
6. 如果证据不足，回答必须明确写出：

```text
当前论文片段中没有足够依据。
```

## 3. 本阶段范围

### 3.1 必须完成

- 新增 `paper-guide/src/qa_engine.py`。
- 接入 DeepSeek 文本模型 API。
- 从环境变量读取 `DEEPSEEK_API_KEY`。
- 将检索结果格式化为带 metadata 的 context。
- 在 Streamlit 中增加“生成回答”按钮。
- 回答必须包含直接回答和证据引用。
- 没有 API key 时不调用模型，检索功能仍可正常使用。
- API 调用失败时显示清楚的错误信息，不影响用户查看检索结果。
- 完成固定论文上的验收测试。

### 3.2 暂不完成

- 直接读取 figure 图片像素。
- 多模态模型接入。
- 自动裁剪 PDF 中的 figure。
- 跨论文问答和参考文献网络。
- 对话历史和长期记忆。
- 完整的 LLM agent。
- 复杂的自动检索规划。

这些能力分别留给 Figure-based Explanation、多模态增强和论文关联阶段。

## 4. 技术方案

### 4.1 LLM Provider

第三步首先使用用户已有的 DeepSeek API。

建议配置：

```text
Provider: DeepSeek
API key: DEEPSEEK_API_KEY
Base URL: https://api.deepseek.com
```

代码中应把模型名称做成可配置项，而不是散落在业务逻辑里。例如：

```text
DEEPSEEK_MODEL
```

这样以后更换 DeepSeek 模型或增加 OpenAI 等 provider 时，不需要重写 RAG 主流程。

### 4.2 API 客户端

DeepSeek API 与 OpenAI API 的常见调用方式兼容，可以使用 OpenAI Python SDK，并设置 DeepSeek 的 `base_url`。

依赖将加入：

```text
openai
python-dotenv
```

`python-dotenv` 用于在本地开发时读取 `.env`，但 API key 不能提交到 Git。

项目应提供：

```text
.env.example
```

示例只写变量名，不写真实 key：

```text
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=
```

同时确认 `.env` 已加入 `.gitignore`。

### 4.3 QA Engine

新增文件：

```text
paper-guide/src/qa_engine.py
```

建议包含以下职责：

```python
is_llm_available()
select_context(results)
build_context(results)
generate_answer(question, results)
```

- `is_llm_available()`：检查 API key 是否存在。
- `select_context()`：从检索候选中选择真正发送给模型的证据。
- `build_context()`：将证据及其 metadata 格式化为模型可读文本。
- `generate_answer()`：构建 prompt、调用模型并返回回答。

检索逻辑继续留在 retriever 中，LLM 调用继续留在 QA engine 中，避免两个职责混在一起。

## 5. Context 设计

### 5.1 为什么不直接发送所有 chunks

发送更多文本不一定产生更好回答。无关片段会：

- 分散模型注意力。
- 让相互矛盾或重复的内容变多。
- 增加 token 消耗和 API 成本。
- 让引用更容易错配。
- 使真正关键的证据被埋没。

因此应追求“较高召回率的候选集合 + 干净而互补的最终上下文”，而不是无限增加文本。

### 5.2 第一版选择策略

第一版可以从当前排序结果中选择大约 8–12 个 chunks，并设置总字符数或 token 上限。

选择时考虑：

- 排名和检索 score。
- `quality_score`。
- 是否为直接回答问题的正文。
- 是否与已有证据高度重复。
- 是否需要 Introduction / Conclusion 提供全局背景。
- figure 问题中是否包含 caption、figure_discussion 和 figure_context。

普通问题和 figure 问题使用不同的证据结构。

普通问题优先：

```text
直接相关正文
  -> 定义或方法
  -> 结果或讨论
  -> Introduction / Conclusion 背景
```

Figure 问题优先：

```text
caption
  -> figure_discussion
  -> figure_context
  -> 相关正文
  -> Introduction / Conclusion 背景
```

### 5.3 Context 格式

每条证据必须带稳定编号和 metadata，例如：

```text
[Evidence 1]
page: 8
chunk_type: body
section: results
figure_id:
text: ...
```

模型应引用 metadata，而不是自行猜测页码。

为了支持阶段 4.5 的“回答引用与 PDF 原文联动”，第三步应从一开始保留稳定的证据映射：

```python
Evidence {
    evidence_id
    chunk_id
    page
    chunk_type
    figure_id
    bbox
}
```

第三步中 `bbox` 可以为空，但 `evidence_id`、`chunk_id` 和 `page` 应当可追溯。模型优先引用 `Evidence 1` 这类受控编号，程序再把它显示为 `[page 8, body]`。

这样后续可以在不改变问答协议的情况下加入：

- 点击引用跳转到 PDF 页面。
- 鼠标悬停引用时高亮原文。
- 点击后固定证据高亮。
- Figure caption、正文讲解与图片区域联动。

## 6. Prompt 约束

系统提示需要明确：

1. 只能根据提供的论文证据回答。
2. 先直接回答用户问题。
3. 每个主要结论都应附引用。
4. 引用格式统一为 `[page X, chunk_type]`。
5. 不得虚构论文中没有出现的定义、数字或结论。
6. 必须区分：
   - 论文直接表达的内容；
   - 基于多段证据进行的谨慎归纳；
   - 当前证据无法确认的内容。
7. 如果证据不足，明确写“当前论文片段中没有足够依据”。
8. 使用用户提问所用的主要语言回答。

第一版暂不强制模型输出复杂 JSON。先使用稳定的 Markdown 文本格式，便于观察回答质量。

## 7. Streamlit 前端改动

在现有检索结果区域增加：

- LLM 可用状态。
- “生成回答”按钮。
- 回答生成中的 spinner。
- 回答显示区域。
- API 错误提示。
- 本次送入模型的证据数量。

建议页面顺序：

```text
问题输入
-> 检索方式和候选数量
-> 生成回答按钮
-> LLM 回答
-> 使用的证据摘要
-> 全部检索结果和诊断信息
```

没有 `DEEPSEEK_API_KEY` 时：

- 按钮禁用或隐藏。
- 页面提示如何在本地配置 key。
- 原有检索功能不受影响。

## 8. 实施步骤

### 第 1 小步：配置与依赖

- 在 `requirements.txt` 中增加 API 客户端依赖。
- 新建 `.env.example`。
- 检查 `.gitignore` 是否忽略 `.env`。
- 在 README 中增加 DeepSeek 配置说明。

完成标志：应用可以识别“已配置 / 未配置 API key”，且不会泄露 key。

### 第 2 小步：实现 QA Engine

- 创建 `qa_engine.py`。
- 定义 context 选择和格式化函数。
- 定义 DeepSeek 调用函数。
- 增加超时和异常处理。

完成标志：可以在 Python 层传入问题和检索结果并获得回答。

### 第 3 小步：接入 Streamlit

- 增加“生成回答”按钮。
- 显示回答、引用和错误。
- 保留原始检索结果。
- 防止每次 Streamlit rerun 都重复调用 API。

完成标志：一次点击只触发一次请求，刷新控件不会意外重复计费。

### 第 4 小步：Prompt 调整

- 检查引用是否来自真实 metadata。
- 测试证据不足回答。
- 检查模型是否把背景推断写成论文结论。
- 调整 context 数量和长度。

完成标志：回答可读、引用可核查、没有明显无依据扩写。

### 第 5 小步：验收测试

使用固定测试论文：

```text
Fong & Han (2021)
A natural boundary of dark matter haloes revealed around the minimum bias and maximum infall locations
```

测试问题：

```text
作者为什么提出 depletion radius？
两种 depletion radius 有什么区别？
What does Figure 1 show?
图5说明了什么？
Figure 5 和 Figure 1 有什么关系？
```

再加入至少一个论文无法回答的问题，例如询问论文未讨论的实验或数据，以测试证据不足处理。

## 9. 验收标准

第三步完成需要同时满足：

- 有 API key 时能够生成回答。
- 无 API key 时应用正常运行并继续显示检索结果。
- 回答直接回应问题，而不是简单拼接 chunks。
- 主要论断带 `[page X, chunk_type]` 引用。
- 引用页码和 chunk_type 能在下方证据中找到。
- 回答能区分直接证据与合理归纳。
- 证据不足时明确承认。
- 不因 Streamlit rerun 自动重复调用 API。
- API key 不出现在代码、日志、Git 提交或页面中。
- 固定验收问题的回答质量达到可人工核查的程度。

## 10. 第三步的第二小阶段：LLM 检索规划

基础问答闭环稳定后，再让 LLM 在检索前参与理解问题。

流程升级为：

```text
用户问题
  -> LLM 判断问题类型
  -> 生成多个通用检索子问题
  -> hybrid / figure_anchor 多路召回
  -> 合并、去重和重排
  -> LLM 基于最终证据回答
```

例如：

```text
两种 depletion radius 有什么区别？
```

模型可以判断这是概念比较问题，并分别寻找：

- 两个概念各自的定义。
- 两者的物理含义。
- 论文中直接比较两者的段落。
- Introduction / Conclusion 中的整体定位。

这一能力称为：

- query rewriting：把原问题改写成更适合检索的表达。
- query expansion：生成多个相关检索表达。
- query planning：根据问题类型设计检索步骤。
- agentic retrieval：由模型动态决定后续检索动作。

它应建立在基础 RAG 闭环之上，而不是和第一次 API 接入同时完成。这样可以分别判断问题究竟来自检索、context 选择、prompt，还是模型生成。

## 10.1 多轮追问与上下文改写

### 当前状态

基础版问答仍然是单轮问答。

每次生成回答时，系统只发送：

```text
当前问题
+ 当前问题检索到的论文证据
```

当前不会自动发送或理解：

- 上一轮用户问题。
- 上一轮模型回答。
- 上一轮引用的证据。
- “它”“那一种”“为什么”等指代所依赖的历史语境。

因此当前版本不能稳定处理真正的追问。

### 实施时机

多轮追问和 Query Planner 一起放在阶段 3 的第二小阶段实现。

原因是追问不能只靠把历史回答附在 prompt 后面。系统还需要先把依赖上下文的追问改写成可以独立检索的问题，再重新查找论文证据。

目标流程：

```text
当前问题 + 相关对话历史
  -> 判断是否为追问
  -> 解析指代和省略信息
  -> 改写成独立问题
  -> Query Planner 制订检索计划
  -> 重新执行 hybrid / figure_anchor 检索
  -> 合并上一轮仍然相关的证据
  -> 生成带引用的回答
```

### 例子

第一轮：

```text
两种 depletion radius 有什么区别？
```

第二轮：

```text
那作者更推荐哪一种？
```

追问改写模块应生成类似：

```text
在 inner depletion radius 和 characteristic depletion radius 中，
作者更推荐哪一种作为暗物质晕边界？论文给出的理由是什么？
```

随后使用改写后的问题重新检索，而不是只沿用第一轮已经找到的 chunks。

### 数据结构

建议为每轮对话保存：

```python
ConversationTurn {
    turn_id
    user_question
    standalone_question
    answer
    cited_evidence_ids
    evidence
    paper_id
}
```

其中：

- `user_question`：用户实际输入的追问。
- `standalone_question`：结合历史改写后的独立问题。
- `answer`：最终回答。
- `evidence`：该轮真正用于回答的论文证据。
- `paper_id`：避免切换论文后错误沿用旧对话。

### 历史上下文控制

不能无限发送全部聊天记录。

第一版策略：

- 只使用当前论文下最近若干轮对话。
- 优先保留上一轮问题、回答摘要和引用证据。
- 当话题明显变化时，不沿用旧证据。
- 切换 PDF 或 `paper_id` 后，默认开始新的论文会话。
- 检索仍以改写后的当前问题为主，聊天历史只能帮助消除指代，不能替代论文证据。

### 前端改动

- 将单个问题输入框升级为论文会话区域。
- 按时间顺序显示用户问题和小助手回答。
- 显示“原始追问”和“系统改写后的检索问题”。
- 提供“新建会话”或“清除当前论文对话”。
- 每轮回答单独保留引用和证据列表。

### 验收标准

- “那作者更推荐哪一种？”能正确继承上一轮的两个概念。
- “为什么？”能识别它在追问上一轮结论的原因。
- “图2呢？”能结合上一轮 Figure 问题理解比较对象。
- 改写后的问题可以在页面中查看，方便调试。
- 每轮追问都会重新检索论文，而不是仅依赖模型聊天记忆。
- 回答仍然必须引用当前论文证据。
- 对话历史中没有足够信息时，系统应要求补充对象或明确说明无法解析指代。
- 切换论文后不会错误引用上一篇论文的对话和证据。

## 11. 阶段完成后的下一步

第三步通过验收后，进入阶段 4：Figure-based Explanation。

阶段 4 会复用本阶段的：

- LLM provider。
- context 格式。
- 引用规则。
- 证据不足处理。
- Streamlit 回答组件。

并在此基础上增加：

- 点击 figure。
- 按 figure_id 组织专用证据。
- 生成结构化图像锚点讲解。
- 后续可选的 figure 裁剪和多模态视觉分析。

阶段 4 的中后段还将进入“阶段 4.5：证据与 PDF 联动阅读”。详细设计记录在根目录的 `DEVELOPMENT_PLAN.md` 中。
