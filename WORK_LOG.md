# paper-buddy 工作日记

这个文档记录开发过程中实际遇到的问题、判断、解决方案和暂未解决事项。

它和其他文档的分工：

- `DEVELOPMENT_PLAN.md`：路线图，记录接下来要做什么。
- `TECHNICAL_DECISIONS.md`：技术决策，记录已经采用的方案和取舍。
- `LEARNING_NOTES.md`：学习笔记，解释开发中遇到的新概念。
- `WORK_LOG.md`：工作日记，记录每阶段实际踩到的问题、如何处理、还剩什么风险。

## 阶段 1：规则版 MVP 与 Figure Anchor

### 已完成

- 建立 Streamlit 前端。
- 支持上传 PDF。
- 使用 PyMuPDF 解析 PDF 文本和 blocks。
- 提取 Figure caption，支持 `Figure 1.`、`Fig. 1.`、`FIG. 1`。
- 构建基础 chunk 类型：
  - `body`
  - `caption`
  - `figure_context`
  - `figure_discussion`
  - `introduction`
  - `conclusion`
- 实现本地关键词检索。
- 实现 `figure_anchor` 检索逻辑。

### 遇到的问题

用户问“图1说了什么？”时，普通关键词检索容易返回其他图的 caption 或不够相关的正文。

### 处理方式

新增 `figure_anchor` 检索：

- 明确识别 `图1`、`fig.1`、`fig .1`、`figure.1` 等图号写法。
- 优先返回目标 figure 的 caption。
- 再返回正文中正式讲解该 figure 的 `figure_discussion`。
- 再返回附近上下文 `figure_context`。
- 证据不足时补充 Introduction / Conclusion 作为全局背景。

### 暂未解决

- 规则检索仍不能真正理解图像像素。
- 有些正文对 figure 的讲解不一定以固定模式出现。
- Introduction / Conclusion 只是背景，不能当作该 figure 的直接证据。

## 阶段 2：向量检索与 chunk 质量

### 已完成

- 加入 ChromaDB。
- 加入 sentence-transformers。
- 默认 embedding 模型为 `sentence-transformers/all-MiniLM-L6-v2`。
- 使用文件名 + 文件 hash 生成 `paper_id`，避免重复索引同一 PDF。
- 保留关键词检索 fallback。
- 增加检索结果数量控制，可以显示更多候选。
- 增加 chunk metadata：
  - `section`
  - `section_title`
  - `paragraph_id`
  - `source_block`
  - `quality_score`
  - `paper_title`
- 增加 `index_version`，metadata 或 chunker 变化时自动重建旧索引。

### 遇到的问题：chunk 从半句话开始

例子：

```text
radius is also shown...
und radius...
to massive neighbours would not be identified as distinct haloes any more.
```

### 原因分析

问题来源不止一个：

- 早期 chunker 使用字符级 overlap，下一段可能从上一段中间开始。
- PyMuPDF 提取出的 block 本身可能就是跨页句子的后半截。
- 双栏论文中，block 顺序不一定完全等同于人类阅读顺序。
- 页眉、页脚、页码可能混进正文。

### 已处理

1. 把 chunk 切分从字符级 overlap 改成句子级 overlap。
2. 增加 chunk 边界清洗，去掉明显的开头残句。
3. 过滤常见页眉、页脚和页码。
4. 对明显跨页续接的正文 blocks 做保守合并，再切成完整句子。
5. 用 `quality_score` 标记 chunk 可读性。
6. 过滤 References 段落，避免参考文献列表进入普通语义检索结果。
7. 收紧章节标题识别，避免把脚注行误判成 `section_title`。

### 当前效果

坏 chunk 明显减少。

测试论文中，`to massive neighbours...` 这类半句开头不再直接作为独立检索结果开头出现。

用户问题“作者为什么提出 depletion radius”下，References 段落曾进入结果 10/11/14。原因是 References 被当成普通正文写入向量库。已通过识别 `references` section 并在 chunk 构建时过滤解决。

### 暂未解决

跨页和双栏版面仍有复杂情况。

例如 PyMuPDF 的 block 顺序可能把双栏文本、caption、页眉、正文混在一起。当前的保守合并能缓解，但不能保证恢复到完全符合人类阅读的段落顺序。

更强方案是引入 bbox 坐标级版面重建。

### 第二步今晚收尾计划

目标：把阶段 2 打磨到“足够进入阶段 3 接入 LLM”的状态。

不追求：

- 完整 PDF 版面重建。
- 所有双栏/跨页问题都完美修复。
- 检索结果直接像人工回答一样完整。

需要完成：

1. **Hybrid retrieval 初版**
   - 普通问题不再只用 vector。
   - 同时取 `vector top N` 和 `keyword top N`。
   - 合并候选，减少单一路径漏召回。

2. **基础去重**
   - 去掉文本高度重叠的候选。
   - 避免同一个 chunk 通过 vector 和 keyword 重复出现。

3. **基础重排**
   - 提高同时被 vector 和 keyword 命中的 chunk。
   - 提高 `quality_score` 高的 chunk。
   - 对 Introduction / Conclusion 保持可见，但不让它们随意挤掉直接证据。
   - 过滤 References。

4. **检索诊断信息**
   - 显示 `source`，例如 `vector`、`keyword`、`hybrid`、`figure_anchor`。
   - 显示 `matched_terms`。
   - 显示 `why_selected`，说明为什么该 chunk 被选中。

5. **验收测试**
   - 用固定测试论文提问：
     - `作者为什么提出 depletion radius`
     - `What does Figure 1 show?`
     - `图5说明了什么？`
   - top 10 中不应出现 References。
   - top 10 中应能看到定义/动机/物理解释/结论类证据的组合。
   - 如果结果仍有不完美 chunk，但不影响 LLM 获取主要证据，则允许进入阶段 3。

判断：如果以上完成，阶段 2 就可以先冻结为“可用版本”，后续 PDF 版面问题放到阶段 4 的 bbox 增强中处理。

### 第二步收尾执行记录

已完成：

- 新增 `src/hybrid_retriever.py`。
- 普通问题现在使用 hybrid retrieval，而不是单纯 vector retrieval。
- Hybrid retrieval 会同时取 vector 候选和 keyword 候选。
- 同一 chunk 会合并来源。
- 高度重叠 chunk 会被去重。
- 重排时考虑：
  - vector score
  - keyword score
  - 是否同时被 vector 和 keyword 找到
  - `quality_score`
  - chunk_type
- 前端新增诊断信息：
  - `vector_score`
  - `keyword_score`
  - `matched_terms`
  - `why_selected`
- References 已经过滤，不再进入普通语义检索结果。

当前观察：

- 对 `作者为什么提出 depletion radius`，top 结果能召回物理解释、定义、与 splashback radius 对比、Introduction / Conclusion 等相关证据。
- Hybrid retrieval 仍然只是“找证据”，不能真正组织“为什么”的自然语言答案。
- 第三步接入 LLM 后，模型可以基于这些候选证据生成更像回答的总结。

仍不作为阶段 2 阻塞项：

- 完美识别所有论文版面。
- 完美理解中文问题中的“为什么”。
- 自动判断哪些证据是“动机”、哪些是“结果”。
- 坐标级 bbox 版面重建。

## 后续待评估：bbox 坐标级版面重建

### 适合阶段

更适合放在阶段 4 期间或阶段 4 之后，而不是阶段 2 的阻塞任务。

原因：

- 阶段 3 的重点是接入 LLM，验证“检索证据 -> 生成回答”的闭环。
- bbox 的价值主要体现在 figure 页面定位、页面高亮、figure 裁剪和双栏阅读顺序恢复。
- 如果现在深入做 bbox，阶段 2 容易变成一个完整 PDF layout parser 项目。

### 可能要做的事

- 在 `PageText.blocks` 中保存每个 block 的 bbox。
- 根据 bbox 过滤页眉、页脚和页码。
- 判断单栏/双栏布局。
- 对双栏论文按左栏从上到下、右栏从上到下排序。
- 识别 caption 和 figure 附近正文。
- 为每个 chunk 保存 bbox 或多个 bbox。
- 支持在 PDF 页面中高亮检索结果。
- 支持裁剪 figure 区域，未来交给 vision 模型分析。

### 风险

- 不同论文模板差异很大。
- figure、caption、公式、脚注会打断正文流。
- 跨页段落恢复需要谨慎，不能把不相干文本硬拼在一起。

## 当前建议

短期优先级：

1. 阶段 2 继续保持 chunk 可读、metadata 清楚、检索可调试。
2. 进入阶段 3，接入 LLM 回答模块。
3. 阶段 4 做 figure-based explanation。
4. 当需要页面高亮、figure 裁剪、vision 模型读图时，再系统引入 bbox。

## 新交互构想：回答引用与 PDF 原文联动

用户提出希望形成左右分栏的论文阅读界面：

- 左侧显示 PDF 原文。
- 右侧显示小助手回答。
- 鼠标移动到回答后的论文证据引用时，左侧对应原文高亮。
- 点击引用后可以跳转并固定高亮。

判断：

- 这是 `paper-buddy` 很有辨识度的核心交互，不只是视觉装饰。
- 它能让用户快速检查 LLM 回答是否忠于论文证据。
- 精确实现依赖 chunk 与 PDF `bbox` 的映射、稳定的 `evidence_id` 和可控制的 PDF 阅读器。

安排：

1. 阶段 3 先完成 DeepSeek 证据化回答，并预留 `evidence_id / chunk_id / page`。
2. 阶段 3 完成后可先实现点击引用跳转到对应页。
3. 阶段 4 中后段实现 `bbox + PDF.js` 精确高亮。
4. 在开发计划中将其单列为“阶段 4.5：证据与 PDF 联动阅读”。

## 阶段 3：基础 LLM 回答模块

### 已完成的第一版实现

- 新增 `src/qa_engine.py`。
- 使用 DeepSeek 的 OpenAI 兼容 API。
- 从 `.env` 读取：
  - `DEEPSEEK_API_KEY`
  - `DEEPSEEK_MODEL`
  - `DEEPSEEK_BASE_URL`
- 新增 `.env.example`，并确认 `.env` 被 Git 忽略。
- 每次回答默认选择最多 10 条证据，并限制上下文总长度。
- 给证据生成受控编号 `E1 / E2 / ...`。
- LLM 只引用 Evidence ID，程序再渲染成 `[page X, chunk_type]`。
- 每条证据保留稳定 `chunk_id`，为后续 PDF 跳转和高亮做准备。
- Streamlit 增加“生成回答”按钮。
- 回答和证据保存到 `session_state`，避免普通 rerun 重复调用 API。
- 无 API key 时按钮禁用，检索功能继续可用。

### 离线验证

使用假 API 客户端完成端到端测试：

```text
RetrievalResult
-> Evidence 选择
-> Context 格式化
-> 模型返回 [E1][E2]
-> 程序转换为真实页码和 chunk_type
```

已验证：

- `[E1]` 能转换为 `[page 8, body]`。
- `[E2]` 能转换为 `[page 2, introduction]`。
- 引用使用的证据 ID 可以被程序识别。
- Python 编译检查通过。

### 2026-06-24 至 2026-06-25：真实 API 初步验收

已完成：

- 本地配置 DeepSeek API，当前模型为 `deepseek-v4-pro`。
- API key 只保存在被 Git 忽略的 `.env` 中，文件权限限制为当前用户可读写。
- 使用固定测试论文完成第一轮真实问答：
  - `作者为什么提出 depletion radius？`
  - `两种 depletion radius 有什么区别？`
  - `What does Figure 1 show?`
  - `图5说明了什么？`
  - `Figure 5 和 Figure 1 有什么关系？`
- 回答整体言之有理、较为流畅，引用可以映射到实际 Evidence。
- 当前不足是回答偏短、偏克制，物理解释和论证展开仍不够深入。
- 这一不足不阻塞基础问答闭环验收，后续通过回答深度模式、Prompt 调整和 Query Planner 改进。

### 证据选择与引用改进

- 证据类型加分改为问题感知：
  - Figure 问题优先 `caption / figure_discussion / figure_context`。
  - 全文总结优先 `conclusion / introduction / body`。
  - 普通概念、原因和比较问题以相关 `body` 为主。
- Evidence 保存原始 `retrieval_rank`。
- 证据列表显示“来自检索结果 #N”。
- 回答引用显示为：

```text
[E1 · Page 4 · caption · Figure 1]
```

- 页面会显示哪些候选没有发送给模型。
- 修复切换 10/20 条检索结果后仍显示旧回答的缓存问题。

### Context 预算观察

当前默认最多发送：

```text
10 条证据
14,000 个正文字符
```

在 Figure 1 测试中，前 9 条证据共 12,583 字符；加入第 10 条后为 14,046 字符，因此第 10 条没有发送。

14,000 字符是 MVP 阶段的工程预算，不是 DeepSeek 的硬性限制。后续应考虑改成真实 token 计数，并为用户提供简洁、详细、深入等回答模式。

### 当前阶段判断

阶段 3 的基础闭环已经建立：

```text
检索论文证据
-> 选择并编号 Evidence
-> DeepSeek 生成回答
-> 程序渲染真实页码与 chunk 类型
-> 用户核查原始证据
```

接下来先补做证据不足测试和 Prompt 深度调整，再进入阶段 3.5 的 Query Planner 与多轮追问。

## 阶段 3 后续计划：LLM 干预检索

### 想法

接入大模型后，不只让 LLM 在检索结果上生成回答，还可以让它先读懂用户问题，再设计检索方案。

这个方向可以叫：

- query planning
- query rewriting
- agentic retrieval

### 例子

用户问：

```text
两种 depletion radius 有什么区别？
```

LLM 可以先判断这是一个“概念比较问题”，然后规划需要找：

1. 定义 `inner depletion radius` 的片段。
2. 定义 `characteristic depletion radius` 的片段。
3. 同时提到二者关系的片段。
4. Introduction / Conclusion 中总结二者意义的片段。

然后系统再执行多个检索 query，例如：

```text
inner depletion radius
characteristic depletion radius
maximum inflow radius
minimum bias radius
two characterisations
```

### 为什么重要

这样可以减少强手写 query expansion。

手写规则容易只适合某一篇论文；LLM query planning 可以根据不同论文和不同问题动态生成检索方案。

### 计划位置

先完成阶段 3 的最小 LLM 回答模块。

然后增加一个轻量 `query_planner`：

```text
用户问题 -> LLM 生成检索计划 -> hybrid retrieval 多路召回 -> LLM 基于证据回答
```

### 新增需求：支持真正的多轮追问

当前问答为单轮模式。用户提出后续需要支持：

```text
第一轮：两种 depletion radius 有什么区别？
第二轮：那作者更推荐哪一种？
```

不能只把第二句话独立检索，也不能只把全部聊天记录直接交给模型。

计划和 Query Planner 一起实现：

1. 保存当前论文下的最近对话。
2. 判断新问题是否为追问。
3. 将依赖历史的追问改写成独立问题。
4. 使用独立问题重新检索论文证据。
5. 只保留与当前问题相关的历史和上一轮证据。
6. 最终回答仍必须引用本轮检索到的论文证据。

该功能列入阶段 3.5，不作为当前基础 DeepSeek 问答闭环的阻塞项。
