from __future__ import annotations

import streamlit as st

from src.chunker import build_chunks
from src.figure_extractor import extract_figure_captions
from src.pdf_parser import parse_pdf
from src.retriever import retrieve


st.set_page_config(page_title="paper-guide", page_icon="📄", layout="wide")

st.title("paper-guide")
st.caption("最小版论文 RAG + 图像锚点讲解助手")

uploaded_file = st.file_uploader("上传一篇 PDF", type=["pdf"])

if uploaded_file is None:
    st.info("请先上传一篇 PDF。")
    st.stop()

with st.spinner("正在解析 PDF..."):
    parsed_pdf = parse_pdf(uploaded_file, filename=uploaded_file.name)
    captions = extract_figure_captions(parsed_pdf.pages)
    chunks = build_chunks(parsed_pdf.pages, captions)

left, right = st.columns([1, 1])

with left:
    st.subheader("论文信息")
    st.write(f"**文件名：** {parsed_pdf.filename}")
    st.write(f"**总页数：** {parsed_pdf.total_pages}")
    st.write(f"**Chunk 数：** {len(chunks)}")

with right:
    st.subheader("Figure captions")
    if captions:
        for caption in captions:
            st.markdown(
                f"- **{caption.figure_id}** · Page {caption.page}: "
                f"{caption.caption}"
            )
    else:
        st.write("暂未提取到 Figure caption。")

st.divider()
st.subheader("关键词检索问答")

question = st.text_input("输入你的问题", placeholder="例如：What does Figure 1 show?")

if question:
    results = retrieve(question, chunks, top_k=5)

    if not results:
        st.warning("没有检索到相关 chunk。可以换一些论文中的关键词再试。")
    else:
        st.write("最相关的 5 个 chunk：")

        for index, (chunk, score) in enumerate(results, start=1):
            title = f"{index}. Page {chunk.page} · {chunk.chunk_type}"
            if chunk.figure_id:
                title += f" · {chunk.figure_id}"

            with st.expander(title, expanded=index == 1):
                st.caption(f"score: {score:.4f}")
                st.write(chunk.text)
