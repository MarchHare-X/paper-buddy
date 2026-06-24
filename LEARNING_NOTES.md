# paper-buddy 开发学习笔记

这个笔记本用于记录开发 `paper-buddy` 过程中学到的概念、技术和工程判断。

记录原则：

- 每个知识点尽量对应项目中的某一步实践。
- 先用直觉解释，再补充技术解释。
- 记录它在 `paper-buddy` 中具体起什么作用。

## 1. Embedding 向量是什么

对应阶段：阶段 2，向量检索升级。

### 1.1 直觉理解

Embedding 是把文字变成一串数字。

例如一句话：

```text
作者为什么提出 depletion radius？
```

会被 embedding 模型变成类似这样的向量：

```text
[0.12, -0.03, 0.44, ..., 0.08]
```

这串数字不是给人看的，而是给计算机比较用的。

关键词检索只能看“字面上有没有出现同样的词”。Embedding 检索则希望判断“意思是否接近”。

例如：

```text
作者为什么提出 depletion radius？
```

和：

```text
The paper proposes a new characterization of the halo boundary.
```

字面词不完全一样，但它们可能在语义上有关。Embedding 的目标就是让这类语义相关的句子在向量空间里更接近。

### 1.2 它如何“识别语义”

Embedding 模型并不是像人类一样有语感，也不是先查一本词典再理解句子。

它的基本机制是：

1. 模型在大量文本上训练。
2. 训练过程中，模型反复看到哪些词、短语、句子经常出现在相似语境中。
3. 模型学会把相似语境中的表达压缩到相近的数字位置。
4. 最终，输入一句话时，模型输出一个向量。

所以“语义相近”不是人工规定的，而是模型从大量语言样本中学到的统计规律。

一个非常粗略的类比：

- `halo boundary`
- `depletion radius`
- `splashback radius`
- `virial radius`

这些词如果经常在类似论文语境中一起出现，模型就会倾向于把它们放在比较接近的区域。

### 1.3 如何比较两个向量

文字变成向量后，系统会计算两个向量的相似度。

常见方法是 cosine similarity，也就是比较两个向量的夹角。

直觉上：

- 方向越接近，表示语义越接近。
- 方向差很远，表示语义差异较大。

这就是为什么向量检索可以做：

```text
问题向量 vs 每个 chunk 向量
```

然后返回最相似的几个 chunks。

### 1.4 在 paper-buddy 中的作用

在阶段 2 之前，`paper-buddy` 主要靠关键词和规则检索。

例如用户问：

```text
作者为什么提出 depletion radius？
```

系统可能主要找包含 `depletion` 和 `radius` 的片段。

阶段 2 加入 embedding 后，系统会：

1. 把每个论文 chunk 转成 embedding。
2. 把用户问题也转成 embedding。
3. 在 ChromaDB 中查找最相似的 chunks。
4. 返回语义上更接近的问题证据。

这一步仍然不会生成流畅回答。它只是更聪明地找原文证据。

真正的自然语言回答要到阶段 3 接入 LLM 后实现。

### 1.5 局限

Embedding 不是完美理解。

它可能出错，尤其在这些情况下：

- chunk 切得太碎或太乱。
- 问题需要复杂推理。
- 论文有很多专业符号和公式。
- 模型没有很好学过相关领域语料。
- 两段话字面不同但逻辑关系很隐晦。

所以 embedding 不能替代好的 PDF 解析、chunk 设计和后续 LLM 判断。

在 `paper-buddy` 中，embedding 应该和 figure anchor 规则结合使用，而不是完全取代规则。

## 2. ChromaDB 在第二步中做什么

对应阶段：阶段 2，向量检索升级。

### 2.1 直觉理解

ChromaDB 是一个本地向量数据库。

如果 embedding 模型负责把文字变成向量，那么 ChromaDB 负责保存这些向量，并在用户提问时快速找出最相似的 chunks。

在 `paper-buddy` 中：

1. PDF 被解析成 chunks。
2. 每个 chunk 被 embedding 模型转成向量。
3. ChromaDB 保存：
   - chunk 原文
   - chunk 向量
   - page
   - chunk_type
   - figure_id
   - paper_id
4. 用户提问时，问题也被转成向量。
5. ChromaDB 返回向量距离最近的 chunks。

### 2.2 为什么需要 paper_id

`paper_id` 用来区分不同论文，并避免重复索引同一篇 PDF。

当前做法是：

```text
paper_id = 文件名 + 文件 hash 的前 16 位
```

文件 hash 来自 PDF bytes。即使两个文件名一样，只要内容不同，hash 也不同。

这样做的好处：

- 同一篇论文重复上传时，不会重复写入 ChromaDB。
- 查询时可以限制只在当前论文的 chunks 中搜索。
- 后续做多论文库和论文关联时，可以继续复用 `paper_id`。

### 2.3 第二步完成后系统能做什么

第二步完成后，系统已经能做语义检索，但仍然不会生成自然语言回答。

它能更聪明地找证据，例如：

```text
用户问题：作者为什么提出 depletion radius？
```

系统会返回语义上接近的原文 chunks，而不是只看关键词重合。

真正把这些 chunks 整理成流畅回答，要到阶段 3 接入 LLM 后实现。

## 3. Chunk metadata 是什么

对应阶段：阶段 1 到阶段 2，PDF 解析、chunk 切分、向量检索。

### 3.1 直觉理解

`metadata` 可以理解为“贴在每个 chunk 身上的标签”。

chunk 的 `text` 是原文内容，metadata 则告诉系统：

- 这段话来自哪一页？
- 它是正文、图注，还是图附近的讲解？
- 它和哪张图有关？
- 它属于哪篇论文？

如果只保存文本，系统就只能看到一段孤立的话。加上 metadata 后，系统才能把这段话放回论文结构里理解。

例如一个 chunk 可能是：

```text
Figure 1. The halo bias profile as a function of radius...
```

它的 metadata 会告诉系统：

```text
page: 4
chunk_type: caption
figure_id: Figure 1
```

这样用户问“图1说了什么？”时，系统就知道这段话是非常重要的证据。

### 3.2 当前项目已经保存的 metadata

在 Python 内存中，每个 chunk 当前包含：

```text
text
page
chunk_type
figure_id
section
section_title
paragraph_id
source_block
quality_score
paper_title
```

含义分别是：

- `text`：chunk 的原文内容。
- `page`：来自 PDF 第几页。
- `chunk_type`：chunk 类型，例如 `body`、`caption`、`figure_context`、`figure_discussion`、`introduction`、`conclusion`。
- `figure_id`：如果这个 chunk 和某张图有关，就保存 `Figure 1` 这样的编号；否则为空。
- `section`：粗略章节类型，例如 `introduction`、`methods`、`results`、`conclusion`。
- `section_title`：论文中的具体章节标题。
- `paragraph_id`：这个 chunk 在当前文本块或章节中的段落/切分编号。
- `source_block`：来自 PyMuPDF 解析出的第几个页面文本块。
- `quality_score`：对 chunk 完整度和可读性的粗略评分。
- `paper_title`：论文标题，用于未来多论文问答时显示来源。

写入 ChromaDB 时，还会保存：

```text
paper_id
index_version
chunk_index
page
chunk_type
figure_id
section
section_title
paragraph_id
source_block
quality_score
paper_title
```

其中：

- `paper_id`：这篇论文的唯一 ID，由文件名和文件 hash 生成。
- `index_version`：索引结构版本。metadata 结构变化时，旧索引会自动失效并重建。
- `chunk_index`：这个 chunk 在当前论文 chunk 列表中的序号。

这些 metadata 让 ChromaDB 不只是“保存一堆向量”，而是能在检索时知道每个向量属于哪篇论文、哪一页、哪类内容。

### 3.3 为什么 metadata 对 RAG 很重要

RAG 不只是“找相似文本”，还需要判断哪些证据更适合回答问题。

例如用户问：

```text
图1说了什么？
```

此时不同类型的 chunk 权重不同：

- `caption` 通常是最直接证据。
- `figure_discussion` 可能是正文中正式解释这张图的部分。
- `figure_context` 是图附近或提到该图的上下文。
- `introduction` 和 `conclusion` 可以提供这张图在全文中的意义。
- 普通 `body` 可能有用，但需要进一步判断。

这就是为什么 `figure_anchor` 检索不能只看文本相似度，还要看 metadata。

### 3.4 后续可能新增的 metadata

当前已经加入了一批轻量 metadata。后续还可能加入：

- `char_start` / `char_end`：在页面文本中的字符位置。
- `bbox`：在 PDF 页面上的坐标位置，用于以后做图像锚点和页面高亮。
- `matched_terms`：检索时命中了哪些关键词。

这些字段不是越早越多越好，而是要服务于具体功能。

当前最有价值的下一批 metadata 可能是：

```text
char_start / char_end
bbox
matched_terms
```

它们会直接帮助我们解决两个问题：

1. chunk 被切坏时，可以更容易定位和修复。
2. 检索结果可以按论文结构重排，例如动机问题优先看 Introduction，结论问题优先看 Conclusion。

### 3.5 当前阶段的工程判断

现在不需要一次性加入所有 metadata。

更合理的节奏是：

1. 先修复 chunk 切分，让文本尽量完整。
2. 同时加入少量马上有用的结构信息，例如 `section`、`paragraph_id`、`quality_score`。
3. 等进入图像锚点和页面高亮阶段，再加入 `bbox` 这类版面坐标信息。

这样可以避免项目过早复杂化，同时保证后面的 RAG 和 LLM 回答有更干净、更可解释的证据基础。

## 4. PyMuPDF 和 bbox 是什么

对应阶段：阶段 1 到阶段 4，PDF 解析、chunk 切分、图像锚点定位。

### 4.1 PyMuPDF 是什么

PyMuPDF 是一个 Python PDF 处理库。

在 `paper-buddy` 中，它目前主要负责：

- 打开 PDF。
- 读取每一页文本。
- 读取每一页的文本块 blocks。
- 获取 PDF 页数和基础 metadata。

当前代码中使用的是：

```python
page.get_text("text")
page.get_text("blocks")
```

其中：

- `text` 更像“这一页的纯文本”。
- `blocks` 更像“这一页按版面区域切出来的文本块”。

### 4.2 为什么 PDF 解析会出问题

PDF 不是像 Word 或 Markdown 那样天然保存“段落结构”的格式。

很多 PDF 更像是一张排版后的页面：文字、公式、图、页眉、页脚、栏位都摆在页面坐标上。

所以从 PDF 里提取正文时，常见问题包括：

- 双栏论文的左右栏顺序可能被提乱。
- 一句话跨页时，下一页会从半句话开始。
- 页眉、页脚、页码会混进正文。
- figure caption 可能和正文、图像区域混在一起。
- 公式、脚注、参考文献可能打断正常段落。

这就是为什么我们会看到类似这样的坏 chunk：

```text
to massive neighbours would not be identified as distinct haloes any more.
```

它不是 embedding 模型的问题，而是 PDF 文本提取和版面恢复的问题。

### 4.3 bbox 是什么

`bbox` 是 bounding box 的缩写，可以理解为“页面上的矩形坐标框”。

一个文本块的 bbox 通常类似：

```text
(x0, y0, x1, y1)
```

含义是：

- `x0`：左边界
- `y0`：上边界
- `x1`：右边界
- `y1`：下边界

如果我们保存 bbox，就不只知道一段文字“在第几页”，还知道它大概位于页面上的哪个位置。

### 4.4 bbox 能帮我们解决什么

bbox 对后续图像锚点助手很重要。

它可以帮助：

- 判断文本属于左栏还是右栏。
- 按页面坐标恢复更合理的阅读顺序。
- 过滤页眉、页脚、页码。
- 找到 caption 附近的正文。
- 在 PDF 页面中高亮检索到的 chunk。
- 裁剪 figure 区域，交给 vision 模型分析。

例如一篇双栏论文里，单纯按 PyMuPDF 返回的 block 顺序读，可能会出现跨栏错序。加入 bbox 后，可以根据坐标判断：

```text
先读左栏从上到下
再读右栏从上到下
```

这比只看纯文本更接近人类阅读 PDF 的方式。

### 4.5 为什么现在不立刻完整加入 bbox

bbox 很有用，但它也会让系统复杂很多。

原因是：

- 不同论文模板的栏位、页眉、caption 位置不同。
- figure 可能跨栏，也可能占半页或整页。
- 坐标级排序需要处理很多版面规则。
- 如果过早做，容易把阶段 2 拖成一个 PDF 版面解析项目。

所以当前阶段只做轻量修复：

- 句子级 chunk 切分。
- 页眉页脚过滤。
- 保守跨页续接合并。
- `quality_score` 标记 chunk 质量。

完整 bbox 版面重建更适合放在阶段 4，也就是我们开始做 figure-based explanation、PDF 页面定位、figure 裁剪和未来多模态读图的时候。

### 4.6 当前工程判断

当前的优先级是：

```text
阶段 2：让 chunks 足够干净，检索结果可用
阶段 3：接入 LLM，让系统能基于证据生成回答
阶段 4：围绕 figure 做结构化讲解
阶段 4 增强：再加入 bbox、页面高亮、figure 裁剪和更强版面重建
```

也就是说，bbox 是重要能力，但不是进入 LLM 阶段的前置条件。
