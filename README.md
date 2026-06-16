# paper-buddy

一个最小版“论文 RAG + 图像锚点讲解助手”原型。

当前可运行项目在 [`paper-guide/`](paper-guide/) 目录中。它使用 Streamlit 做前端，PyMuPDF 解析 PDF，提取 Figure captions，并用本地规则和关键词检索返回相关论文片段。

## 当前功能

- 上传 PDF
- 显示 PDF 文件名和总页数
- 提取 Figure caption
- 将正文、caption、figure discussion、introduction、conclusion 切成 chunks
- 支持图像锚点检索，例如 `图1说了什么？`、`fig.1讲了什么？`
- 返回相关 chunk、页码、chunk 类型和 score

## 运行

```bash
cd paper-guide
pip install -r requirements.txt
streamlit run app.py
```

## 下一步计划

- 接入 ChromaDB 和 sentence-transformers 做本地向量检索
- 加入 LLM 回答模块
- 增加 Figure-based explanation 功能
