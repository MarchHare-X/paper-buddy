# paper-buddy

一个最小版“论文 RAG + 图像锚点讲解助手”原型。

当前可运行项目在 [`paper-guide/`](paper-guide/) 目录中。它使用 Streamlit 做前端，PyMuPDF 解析 PDF，提取 Figure captions，并结合图像锚点规则、ChromaDB 向量检索和关键词 fallback 返回相关论文片段。

## 当前功能

- 上传 PDF
- 显示 PDF 文件名和总页数
- 提取 Figure caption
- 将正文、caption、figure discussion、introduction、conclusion 切成 chunks
- 支持图像锚点检索，例如 `图1说了什么？`、`fig.1讲了什么？`
- 使用 sentence-transformers 生成本地 embedding
- 使用 ChromaDB 保存和查询向量索引
- 普通问题使用 hybrid retrieval，向量不可用时回退关键词检索
- 接入 DeepSeek，基于检索证据生成带页码引用的回答
- 使用受控 Evidence ID，保留原始检索排名和证据 metadata
- 返回相关 chunk、页码、chunk 类型和 score

## 运行

```bash
cd paper-guide
pip install -r requirements.txt
streamlit run app.py
```

## 下一步计划

- 增加 Query Planner 和多轮追问
- 增加 Figure-based explanation 功能
- 实现回答引用与 PDF 原文定位、高亮
- 后续扩展论文关联与研究网络
