# paper-buddy 开发计划书

## 1. 项目目标

`paper-buddy` 的最终目标是做一个“论文 RAG + 图像锚点讲解 + 研究关联助手”。

它不只是一个 PDF 问答工具，而是一个帮助研究者围绕论文中的 figures 阅读、理解、整理和反思的助手。

项目有两条长期主线：

1. **图像锚点阅读**：以 figure 为入口理解单篇论文的论证结构。
2. **研究关联发现**：建立论文与论文之间、论文与用户工作之间的关系网络。

当前优先级是先把“图像锚点阅读”做好，再逐步细化“关联”功能。关联功能会引入参考文献抽取、文献搜索、文献网络、用户项目记忆等问题，复杂度明显更高，不应过早混入 MVP。

最终希望实现：

- 上传或导入一篇论文 PDF
- 自动解析正文、图例、页码和章节结构
- 以 figure 为锚点组织论文内容
- 支持普通论文问答
- 支持点击某张 figure 后生成结构化讲解
- 支持发现论文与论文之间的关系
- 支持发现论文与用户项目、研究问题、关心主题之间的关系
- 回答时引用证据来源，如 page、chunk_type、figure_id
- 区分论文直接证据、模型解释、与用户研究方向的可能相关性
- 在证据不足时明确说明，而不是编造

## 2. 当前状态

当前已完成第一版 MVP。

已有功能：

- Streamlit 前端
- PDF 上传
- PyMuPDF 解析 PDF
- Figure caption 提取
- 正文、caption、figure discussion、introduction、conclusion 切块
- 本地关键词检索
- ChromaDB 向量检索
- sentence-transformers 本地 embedding
- `paper_id` 去重索引
- Figure anchor 查询优化，例如 `图1说了什么？`、`fig.1讲了什么？`
- 当图像锚点片段不足时，补充 Introduction 和 Conclusion 作为全局上下文
- 根目录 README 和 GitHub 仓库已建立
- 已创建 `paper-figure-reading` Codex skill，用于沉淀图像锚点论文阅读流程

当前已经具备第一版语义检索能力，但仍然没有 LLM 生成回答，因此现在返回的仍是原文 chunks。

## 3. 核心概念

### 3.1 RAG

RAG 是 Retrieval-Augmented Generation，中文可以理解为“检索增强生成”。

基本流程：

1. 把论文切成 chunks
2. 根据用户问题检索相关 chunks
3. 把这些 chunks 作为 context 给 LLM
4. LLM 基于 context 回答

RAG 的关键不是“让模型记住整篇论文”，而是每次回答前先找证据。

### 3.2 Chunk

Chunk 是论文中的一个片段。

当前 chunk 类型包括：

- `body`：普通正文
- `caption`：figure caption
- `figure_discussion`：正文中正式讲解某张 figure 的段落
- `figure_context`：正文中提到某张 figure 的附近上下文
- `introduction`：引言片段
- `conclusion`：结论片段

### 3.3 Embedding

Embedding 是把文字转成数字向量。

它的作用是让系统可以用数学距离比较语义相似度，而不只是看关键词是否完全匹配。

例如用户问“作者如何定义边界”，正文可能写的是 `depletion boundary` 或 `characteristic depletion radius`。关键词检索可能漏掉，但 embedding 检索更可能找到相关片段。

### 3.4 Figure Anchor

Figure anchor 是本项目的特色。

普通 RAG 通常围绕用户问题检索文本；本项目还会围绕某张 figure 主动组织：

- caption
- 正文讲解
- 附近上下文
- introduction 中的研究动机
- conclusion 中的论文主张

这样可以回答“这张图在论文中扮演什么角色”。

### 3.5 Text-Grounded Figure Explanation

当前优先实现的是“基于文本证据的图像锚点讲解”，不是直接让模型看图片像素。

也就是说，系统先根据以下文本材料解释 figure：

- figure caption
- 正文中正式讲解该 figure 的段落
- figure 附近正文
- Introduction 中的研究问题和动机
- Conclusion / Discussion 中的论文主张

如果当前使用的 LLM API 不支持多模态图片输入，例如只能输入文本，那么它无法直接读出图里的曲线、坐标轴、legend 或视觉细节。它只能根据我们提供的文本证据进行解释。

这并不妨碍当前阶段继续开发。论文中很多 figure 的核心含义本来就由 caption 和正文说明。后续如果接入支持 vision 的模型，可以再加入直接读图能力。

### 3.6 Multimodal Figure Understanding

多模态 figure understanding 是后续增强能力。

理想流程：

1. 从 PDF 中截取单张 figure 或 figure 所在页面区域。
2. 把图像交给支持 vision 的模型分析。
3. 让模型识别坐标轴、legend、panel、曲线趋势、颜色编码和异常点。
4. 将视觉分析结果与 caption、正文、Introduction、Conclusion 的文本证据合并。
5. 输出时明确区分：
   - 视觉观察
   - 论文文字证据
   - 模型解释
   - 不确定之处

在没有 vision API 时，不应假装模型看到了图。回答应说明依据来自文本证据。

### 3.7 Research Link

Research link 是本项目的另一条长期主线，指论文之间、论文与用户工作之间的关联。

关联来源主要有三类：

1. **参考文献天然连接**：一篇论文引用了哪些论文，被哪些论文影响。
2. **内容语义连接**：两篇论文研究相似问题、使用相似方法、共享变量或概念。
3. **对话发现连接**：用户在交流中指出某篇论文和自己的项目、问题、数据、模型或想法有关。

这类关联不能只靠 PDF 内部解析完成。它通常需要参考文献解析、外部文献搜索、向量检索、用户项目记忆和人工确认。

## 4. 最终功能蓝图

最终版本应支持以下能力。

### 4.1 文档管理

- 上传 PDF
- 识别文件名、页数、hash
- 避免重复索引同一篇论文
- 显示已加载论文状态

### 4.2 PDF 结构解析

- 提取每页正文
- 提取版面 blocks
- 提取 Figure captions
- 识别 Introduction / Conclusion / Discussion
- 保留 page、chunk_type、figure_id、paper_id 等 metadata

### 4.3 检索

- 关键词检索 fallback
- ChromaDB 向量检索
- sentence-transformers 本地 embedding
- Figure anchor 专用检索逻辑
- 支持 top_k 参数
- 显示 score 和 metadata

### 4.4 LLM 问答

- 从环境变量读取 `OPENAI_API_KEY`
- 使用检索到的 chunks 作为 context
- 输出直接回答
- 输出引用依据
- 证据不足时明确说明
- 无 API key 时只显示检索结果

### 4.5 Figure-based Explanation

用户点击某个 figure 后，系统生成：

- 这张图展示什么
- caption 说了什么
- 附近正文补充了什么
- 横纵坐标/变量/符号含义
- 作者想用它证明什么
- 它和全文主线的关系
- 读者应该注意什么
- 与用户研究方向的可能相关性

当前优先做文本证据版。也就是说，回答依据来自 caption、正文、Introduction、Conclusion，而不是直接读取图片像素。

多模态直接读图作为后续增强功能。

### 4.6 研究笔记输出

未来可扩展：

- 一键生成 figure-centered reading notes
- 导出 Markdown
- 导出 Word / PDF
- 支持“直接证据 / 解释 / 研究启发”分栏

### 4.7 论文关联与研究网络

未来可扩展：

- 提取论文参考文献
- 根据 DOI、标题、arXiv ID 或 Crossref/Semantic Scholar/OpenAlex 查询参考文献信息
- 建立论文与论文之间的引用网络
- 识别同主题、同方法、同数据、同概念的论文
- 记录用户在对话中确认的相关关系
- 维护用户项目、研究问题和关心主题
- 回答“这篇论文和我之前读的哪篇有关？”
- 回答“这张图/这个方法对我的项目可能有什么启发？”

### 4.8 多模态图像理解

未来可扩展：

- 从 PDF 页面中裁剪 figure 图片
- 调用支持 vision 的模型
- 识别图中的坐标轴、legend、曲线、panel 和标注
- 将视觉观察与文本证据合并
- 明确标注哪些内容来自图像观察，哪些来自论文文字

## 5. 阶段路线

## 阶段 1：规则版 MVP 与 Figure Anchor 基础

### 目标

建立最小可运行系统，并把 figure 相关 metadata 打稳。

### 已完成内容

- Streamlit 前端
- PDF 上传
- PyMuPDF 解析文本与 blocks
- Figure caption 提取
- chunk 构建
- 关键词检索
- Figure 查询输入归一化
- `caption / figure_discussion / figure_context / introduction / conclusion` 分层
- Introduction / Conclusion fallback

### 技术

- Python
- Streamlit
- PyMuPDF
- 正则表达式
- 本地规则检索
- Git / GitHub

### 当前验收标准

进入下一阶段前，阶段 1 应满足：

- 上传测试论文后能显示文件名和总页数
- 能提取主要 Figure captions
- 问 `图1说了什么？` 能返回目标 figure caption 和正文讲解
- `fig.1`、`fig .1`、`figure.1`、`图1` 等写法都能识别
- 不再明显返回其他 figure 的 caption 作为主要结果
- 当图像相关片段不足时，会补充 Introduction / Conclusion

### 不追求解决的问题

阶段 1 不负责真正语义理解。

例如：

- 自动判断某张图“证明了什么”
- 主动联想到物理动机或公式意义
- 跨章节找隐含相关内容

这些应交给后续 embedding 和 LLM。

## 阶段 2：向量检索升级

### 目标

加入语义检索，让普通问题和间接表达的问题更容易找到相关片段。

当前状态：已实现第一版。

### 要实现的功能

1. 添加 ChromaDB 作为向量数据库。
2. 添加 sentence-transformers 作为本地 embedding 方案。
3. 默认使用 `all-MiniLM-L6-v2`。
4. 保留关键词检索作为 fallback。
5. 上传 PDF 后，把 chunks 写入 Chroma collection。
6. 用户提问后，返回 top_k=5 的相似 chunks。
7. 前端显示每个 chunk 的：
   - score
   - page
   - chunk_type
   - figure_id
8. 避免重复索引同一 PDF，使用文件名 + 文件 hash 作为 `paper_id`。

### 技术

- ChromaDB
- sentence-transformers
- all-MiniLM-L6-v2
- hashlib
- metadata filtering

### 实现思路

新增模块：

- `src/paper_id.py`：计算文件 hash 和 paper_id
- `src/vector_store.py`：封装 Chroma collection 创建、写入、查询
- 可选 `src/embeddings.py`：封装 sentence-transformers 模型加载

检索流程：

1. 上传 PDF
2. 解析 chunks
3. 计算 paper_id
4. 检查 Chroma 是否已有该 paper_id
5. 若没有，则 embedding 并写入
6. 用户提问时先走向量检索
7. 如果向量检索失败或无结果，fallback 到关键词检索

### 验收标准

进入下一阶段前应满足：

- 第一次上传 PDF 会索引 chunks
- 再次上传同一 PDF 不重复索引
- 普通自然语言问题比关键词检索更稳定
- 检索结果仍带 page、chunk_type、figure_id
- 无网络环境下可用本地 embedding
- 如果 Chroma 或模型加载失败，仍能 fallback 到关键词检索

### 风险

- 首次下载 embedding 模型需要网络
- 本地模型加载会变慢
- Chroma metadata 和 chunk id 需要设计清楚，否则后期难迁移
- PDF 版面解析会遇到双栏、跨页断句、页眉页脚等问题。阶段 2 只做轻量修复，例如句子级切分、页眉过滤、保守跨页续接合并；完整的坐标级版面重建不作为进入阶段 3 的阻塞条件。

## 阶段 3：LLM 回答模块

### 目标

从“返回 chunks”升级为“基于证据生成回答”。

### 要实现的功能

1. 新增 `src/qa_engine.py`。
2. 从环境变量 `OPENAI_API_KEY` 读取 API key。
3. 使用检索到的 top chunks 作为 context。
4. 回答必须包含：
   - 直接回答
   - 引用依据，格式为 `[page X, chunk_type]`
   - 证据不足时明确说“当前论文片段中没有足够依据”
5. Streamlit 前端增加“生成回答”按钮。
6. 如果没有 `OPENAI_API_KEY`，只显示检索结果，不调用 LLM。

### 技术

- OpenAI API
- prompt engineering
- context formatting
- environment variables

### 实现思路

新增：

- `src/qa_engine.py`

核心函数：

- `build_context(chunks)`
- `generate_answer(question, chunks)`

Prompt 原则：

- 只基于给定 context 回答
- 必须引用 page 和 chunk_type
- 不能编造
- 证据不足要明说

### 验收标准

进入下一阶段前应满足：

- 有 API key 时可以生成回答
- 无 API key 时系统不报错
- 回答能引用 page 和 chunk_type
- 当问题超出检索证据时，会说证据不足
- 回答不会把 interpretation 伪装成论文直接结论

### 风险

- LLM 可能过度总结或幻觉
- context 太多可能超过 token 限制
- 需要在 prompt 中明确 evidence discipline

### 阶段 3.5：Query Planner 与多轮追问

基础 LLM 回答通过真实 API 验收后，增加：

- 用 LLM 判断问题类型。
- 将用户问题改写为更适合检索的独立问题。
- 为比较、原因、定义、总结、Figure 等问题生成多路检索计划。
- 保存当前论文下的对话历史。
- 判断当前输入是否依赖上一轮语境。
- 解析“它”“那一种”“为什么”“图2呢”等追问中的指代和省略信息。
- 使用改写后的问题重新检索论文，而不是只沿用上一轮证据。
- 每轮回答继续保存和展示受控 Evidence ID。

推荐流程：

```text
用户追问 + 当前论文的相关对话历史
  -> 追问改写
  -> Query Planner
  -> 多路检索与重排
  -> 证据化回答
```

多轮问答不能只把全部聊天记录直接发送给模型。聊天历史主要用于理解指代，论文检索证据仍然是回答事实问题的依据。

验收问题：

```text
第一轮：两种 depletion radius 有什么区别？
追问：那作者更推荐哪一种？

第一轮：图1说了什么？
追问：图2呢？

第一轮：作者为什么提出 depletion radius？
追问：这个动机在结论中得到验证了吗？
```

切换 PDF 或 `paper_id` 后，应默认开始新的论文会话，避免引用上一篇论文的历史。

## 阶段 4：Figure-based Explanation

### 目标

实现本项目的核心特色：点击某张 figure，生成结构化图像锚点讲解。

### 要实现的功能

1. 前端显示所有提取到的 Figure captions。
2. 用户点击某个 `figure_id`。
3. 系统检索：
   - 该 figure 的 caption
   - caption 所在页附近正文 chunk
   - figure_discussion / figure_context
   - introduction / conclusion 中相关 chunk
4. 生成结构化讲解：
   - 这张图在展示什么
   - 横纵坐标/变量含义
   - 作者想用它证明什么
   - 它和全文主线的关系
   - 我作为读者应该注意什么
5. 如果没有 LLM API key，只显示相关 chunks。

### 技术

- Streamlit interactive widgets
- Figure metadata filtering
- Chroma metadata filtering
- LLM structured generation
- `paper-figure-reading` skill 的流程迁移
- 可选增强：PyMuPDF `bbox` 坐标、页面区域定位、figure 裁剪、双栏阅读顺序恢复

### 实现思路

新增：

- `src/figure_qa.py` 或 `src/figure_explainer.py`

前端：

- caption 列表改成可点击按钮或 selectbox
- 选中 figure 后显示 evidence chunks
- 有 API key 时显示结构化 explanation

Prompt 结构：

```text
Direct evidence:
- caption evidence
- nearby text evidence
- intro evidence
- conclusion evidence

Explanation:
1. What the figure shows
2. What variables mean
3. What claim it supports
4. Relation to paper argument
5. Reader notes
6. Evidence gaps
```

### 验收标准

进入下一阶段前应满足：

- 点击 Figure 1 能看到 caption 和正文讲解
- 生成回答结构稳定
- 引用清楚
- 不会把 Introduction/Conclusion 的全文背景当作该图直接证据
- 无 API key 时仍能作为“figure evidence browser”使用

### 可选增强：坐标级版面重建

更强的 `bbox` 版面重建适合放在阶段 4 期间或阶段 4 之后，而不是阶段 2 的必要条件。

适合引入它的时机：

- 需要在 PDF 页面中高亮检索到的原文位置。
- 需要裁剪单张 figure 给 vision 模型。
- 需要根据左右栏、上下位置恢复更准确的阅读顺序。
- 轻量 chunk 清洗仍频繁产生明显错序、半句或跨栏拼接。

它的目标不是替代 RAG，而是提升 PDF 结构恢复和图像锚点定位能力。

## 阶段 4.5：证据与 PDF 联动阅读

### 目标

实现“左侧阅读论文原文、右侧与小助手对话”的联动界面，让回答中的引用能够直接定位到 PDF 中的原始证据。

理想交互：

```text
左侧 PDF 原文                         右侧小助手

对应证据自动滚动到可见区域             回答正文……
引用对应的文字区域高亮                 [page 8, body]
                                      鼠标悬停或点击引用
```

### 分步实现

第一小步：页级定位。

- 左侧显示 PDF。
- 用户点击回答中的引用后，跳转到对应页。
- 暂时不要求精确高亮句子或段落。

第二小步：精确证据高亮。

- 使用 PyMuPDF 提取 word/block 的 `bbox` 坐标。
- 建立 chunk 与一个或多个 PDF 坐标区域的映射。
- 使用 PDF.js 或 Streamlit 自定义组件显示 PDF。
- 鼠标悬停引用时临时高亮对应原文。
- 点击引用时固定高亮并滚动到对应位置。
- 支持一个结论对应多个证据区域。

第三小步：Figure 证据联动。

- 高亮目标 figure 的 caption。
- 高亮正文中的 `figure_discussion` 和 `figure_context`。
- 后续可以框选 figure 图片所在区域。
- 在视觉模型接入后，同时展示图像观察和文字证据的位置。

### 数据结构要求

第三步接入 LLM 时就应预留稳定的证据标识，不让模型自行生成任意页码。

建议结构：

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

其中：

- `evidence_id`：一次回答中的稳定证据编号，例如 `E1`。
- `chunk_id`：指向实际检索 chunk。
- `page`：用于第一版页级跳转。
- `bbox`：用于后续精确高亮；第三步可以暂时为空。

LLM 在生成回答时引用 `evidence_id`，系统再将它渲染为用户可读的 `[page X, chunk_type]`。这样既能减少模型编造引用，也便于前端找到对应 PDF 位置。

### 验收标准

- 点击引用能够跳转到正确页面。
- 悬停引用能够高亮正确的原文区域。
- 移开鼠标后临时高亮消失。
- 点击后可以固定或取消固定高亮。
- 引用与 chunk、页码、bbox 的对应关系由程序控制，不依赖模型猜测。
- 多个引用之间切换时，PDF 页面和高亮状态保持稳定。

### 实施时机

该功能放在阶段 3 的基础 LLM 问答完成之后、阶段 4 Figure-based Explanation 的中后段实施。

它不作为第三步接入 DeepSeek 的阻塞项，但第三步必须预留 `evidence_id`、`chunk_id` 和 `page`。精确 `bbox`、PDF.js 和左右联动界面留到本阶段完成。

## 阶段 5：论文阅读报告

### 目标

从单图解释扩展到整篇论文阅读报告。

### 要实现的功能

- 自动选择重要 figures
- 逐图生成讲解
- 总结论文主线
- 汇总关键概念
- 输出研究启发
- 支持 Markdown 导出

### 技术

- 多步 LLM pipeline
- report template
- Markdown export
- 可选 Word/PDF 导出

### 验收标准

- 能生成一份结构化阅读笔记
- 每个 figure 都有证据引用
- 论文主线和 figure 之间的关系清楚
- 输出可保存、可复用

## 阶段 6：论文关联与研究网络

### 目标

在单篇论文阅读能力稳定后，逐步建立“论文与论文之间”和“论文与用户研究之间”的关联层。

这一阶段不应太早开始。它依赖前面已经具备：

- 稳定的 PDF 解析
- 可靠的 chunk 和 metadata
- 向量检索
- LLM 证据化回答
- Figure-based explanation

### 关联类型

1. **引用关系**
   - 当前论文引用了哪些论文
   - 哪些参考文献支撑了背景、方法或结论
   - 某个 figure 或概念是否来自前人工作

2. **语义关系**
   - 两篇论文是否研究相似问题
   - 是否使用相似方法或数据
   - 是否共享关键变量、定义、物理机制或模型

3. **用户项目关系**
   - 某篇论文是否与用户当前项目有关
   - 某张图是否启发用户的实验、模拟、模型或写作
   - 某个概念是否应加入用户的研究笔记

4. **对话中发现的关系**
   - 用户明确说“这篇和那篇有关”
   - 用户指出某个方法可以用于自己的项目
   - 系统从多次对话中归纳出稳定主题

### 要实现的功能

- 解析参考文献列表
- 尝试识别 DOI、arXiv ID、标题、作者、年份
- 支持用户手动确认或修正参考文献信息
- 调用外部文献数据库补全 metadata
- 建立本地 paper graph
- 给论文、figure、concept、user project 建立节点
- 给节点之间建立 relation，例如：
  - `cites`
  - `uses_method_from`
  - `addresses_same_problem_as`
  - `supports_user_project`
  - `user_marked_related`
- 在 UI 中显示关联论文和关联理由

### 可能技术

- GROBID 或 PyMuPDF + 规则解析参考文献
- Crossref API
- Semantic Scholar API
- OpenAlex API
- arXiv API
- SQLite 保存 paper metadata
- NetworkX 或轻量图结构保存关系
- ChromaDB 保存语义相似关系
- LLM 辅助判断关系类型，但需要证据引用和用户确认

### 难点

- PDF 参考文献格式差异很大
- 标题、作者、年份可能解析错误
- DOI 不一定存在
- 中文路径、特殊字符、断行会增加解析难度
- 外部 API 有速率限制和网络不稳定问题
- “语义相关”不等于“真的对用户项目有用”
- 用户项目需要持续记忆和明确边界，否则容易过度联想

### 分阶段实现建议

第一小步：只做手动关联。

- 用户可以把两篇论文标记为相关
- 用户可以写一句关联理由
- 系统保存这个关系

第二小步：做参考文献抽取。

- 从 PDF 中提取 References section
- 尝试按条目切分
- 先显示给用户确认，不急着自动建图

第三小步：做外部 metadata 补全。

- 用标题或 DOI 查询 Crossref / OpenAlex / Semantic Scholar
- 保存标准化 title、authors、year、venue、doi、url

第四小步：做论文关系图。

- 当前论文引用了哪些论文
- 用户手动标记了哪些关系
- 哪些论文语义相似

第五小步：做“和我的项目有什么关系”。

- 维护用户项目描述
- 检索论文中相关证据
- 生成谨慎的 relevance analysis
- 要求区分直接证据、推测、需要验证的想法

### 验收标准

进入更深入的关联功能前应满足：

- 能稳定保存至少两篇论文的 metadata
- 能手动创建和展示论文关系
- 能从一篇 PDF 中提取 References section
- 能让用户确认参考文献解析结果
- 不把自动推测的关联当作事实
- 每条自动关系都能给出证据或置信说明

## 阶段 7：稳定性与产品化

### 目标

让系统更稳定、更适合长期使用。

### 可能功能

- 多论文管理
- 历史记录
- 缓存已索引论文
- 支持 Zotero 路径导入
- 更好的 PDF 版面解析
- 支持表格、公式、参考文献过滤
- 多论文库和项目库管理
- 论文关系图浏览
- 单元测试
- 错误提示
- Docker 或一键启动脚本

### 技术

- persistent ChromaDB
- SQLite 或本地 metadata store
- NetworkX 或本地 graph schema
- pytest
- logging
- config 文件

## 6. 开发原则

### 6.1 先证据，后解释

任何回答都应先有 paper evidence。

### 6.2 不要让 LLM 拯救脏检索

RAG 的质量取决于 context。检索到的片段越干净，LLM 越可靠。

### 6.3 Figure 是阅读锚点，不是唯一证据

Figure caption 很重要，但真正理解 figure 通常还需要：

- 正文讲解
- 方法定义
- Introduction 的研究问题
- Conclusion 的论文主张

### 6.4 阶段性验收

每一步都要有明确可测试的问题。

例如：

- `图1说了什么？`
- `What does fig.1 show?`
- `作者为什么提出 depletion radius？`
- `Figure 5 和 Figure 1 有什么关系？`

### 6.5 关联功能要晚一点做

论文关联是重要主线，但不应抢在基础 RAG 和 figure explanation 之前。

原因：

- 参考文献解析本身就是一个复杂任务
- 外部文献搜索需要处理 API、网络、匹配错误和去重
- 论文关系需要持久化数据结构
- 用户项目相关性需要长期上下文和谨慎表达

因此，近期优先完成单篇论文内的图像锚点阅读。等单篇论文证据链稳定后，再加入跨论文关联。

## 7. 下一步建议

下一步应进入阶段 3：LLM 回答模块。

暂时不要开始参考文献网络和跨论文关联。它们已经作为长期主线写入计划，但需要等单篇论文的 RAG、LLM 回答和 Figure-based explanation 稳定后再做。

推荐顺序：

1. 新增 `src/qa_engine.py`。
2. 从环境变量读取 LLM API key。
3. 把检索到的 chunks 格式化为 context。
4. 让模型基于 context 生成回答。
5. 回答中必须包含引用依据。
6. 证据不足时明确说明。
7. 无 API key 时只显示检索结果。

阶段 3 完成后，再进入 Figure-based explanation。

关联功能的近期准备工作可以先很轻量地做：

- 在数据结构里预留 `paper_id`
- 在 chunk metadata 中保留 `paper_id`
- 后续保存用户项目描述时，注意和 paper metadata 分开
- 不急着解析 References section
