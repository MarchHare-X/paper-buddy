# paper-guide

最小版“论文 RAG + 图像锚点讲解助手”。

当前版本使用 Streamlit 做前端，PyMuPDF 解析 PDF 文本，使用 ChromaDB + sentence-transformers 做本地向量检索，并保留关键词检索作为 fallback。配置 DeepSeek API 后，还可以基于检索证据生成带引用的回答。上传 PDF 后，应用会：

- 显示 PDF 文件名和总页数
- 尝试提取 Figure caption，支持 `Figure 1.`、`Fig. 1.`、`FIG. 1` 等格式
- 将正文和 caption 切成 chunks，并保存 `page`、`chunk_type`、`figure_id` 等 metadata
- 根据用户问题做图像锚点检索或向量检索，返回最相关的 chunks
- 使用 DeepSeek 根据检索证据回答，并显示 `[page X, chunk_type]` 引用
- 在没有 API key 时继续作为本地论文检索工具使用

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
    paper_id.py
    embeddings.py
    vector_store.py
    hybrid_retriever.py
    qa_engine.py
```

## 安装与运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 配置 DeepSeek

在 `paper-guide` 目录下复制环境变量示例：

```bash
cp .env.example .env
```

然后编辑 `.env`：

```text
DEEPSEEK_API_KEY=你的_API_key
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

`.env` 已被 Git 忽略，不要把真实 API key 提交到仓库。

配置完成后重新启动：

```bash
streamlit run app.py
```

输入问题并等待检索结果出现，然后点击“生成回答”。模型会根据选中的论文证据回答；原始检索结果仍会保留在页面下方供核查。

## 回答与引用

发送给模型的每条证据都有受控编号，例如 `E1`。模型只引用这些编号，程序再将其转换为：

```text
[E1 · Page 8 · body]
```

这样页码和 chunk 类型来自程序 metadata，而不是由模型自行猜测。每条证据还保留 `chunk_id`，用于后续实现点击引用跳转和 PDF 原文高亮。

## 说明

首次使用向量检索时，`sentence-transformers/all-MiniLM-L6-v2` 模型需要从 Hugging Face 下载；下载完成后可本地复用缓存。DeepSeek 调用会产生 API 用量；只有用户点击“生成回答”时才会发起请求，普通 Streamlit rerun 不会自动调用。
