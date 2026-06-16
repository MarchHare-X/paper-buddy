# paper-guide

最小版“论文 RAG + 图像锚点讲解助手”。

当前 MVP 使用 Streamlit 做前端，PyMuPDF 解析 PDF 文本，并用本地关键词匹配代替真实 LLM API 和 embedding。上传 PDF 后，应用会：

- 显示 PDF 文件名和总页数
- 尝试提取 Figure caption，支持 `Figure 1.`、`Fig. 1.`、`FIG. 1` 等格式
- 将正文和 caption 切成 chunks，并保存 `page`、`chunk_type`、`figure_id` 等 metadata
- 根据用户问题做简单关键词检索，返回最相关的 5 个 chunk

## 项目结构

```text
paper-guide/
  app.py
  requirements.txt
  README.md
  src/
    pdf_parser.py
    figure_extractor.py
    chunker.py
    retriever.py
```

## 安装与运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 说明

这是第一版 MVP，暂时不接真实 LLM API，不做 embedding。后续可以把 `src/retriever.py` 替换为向量检索模块，再在 Streamlit 层接入 LLM 生成回答。
