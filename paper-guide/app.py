from __future__ import annotations

import hashlib
from io import BytesIO

import streamlit as st

from src.chunker import build_chunks
from src.figure_extractor import extract_figure_captions
from src.hybrid_retriever import RetrievalResult, hybrid_search
from src.paper_id import make_paper_id
from src.pdf_parser import parse_pdf
from src.qa_engine import (
    QAEngineError,
    generate_answer,
    get_model_name,
    is_llm_available,
)
from src.retriever import requested_figure_numbers, retrieve
from src.vector_store import index_chunks


st.set_page_config(page_title="paper-guide", page_icon="📄", layout="wide")

st.title("paper-guide")
st.caption("最小版论文 RAG + 图像锚点讲解助手")

uploaded_file = st.file_uploader("上传一篇 PDF", type=["pdf"])

if uploaded_file is None:
    st.info("请先上传一篇 PDF。")
    st.stop()

with st.spinner("正在解析 PDF..."):
    pdf_bytes = uploaded_file.getvalue()
    paper_id = make_paper_id(uploaded_file.name, pdf_bytes)
    parsed_pdf = parse_pdf(BytesIO(pdf_bytes), filename=uploaded_file.name)
    captions = extract_figure_captions(parsed_pdf.pages)
    chunks = build_chunks(parsed_pdf.pages, captions, paper_title=parsed_pdf.title)

index_status = "未索引"
index_error: str | None = None
with st.spinner("正在准备向量索引..."):
    try:
        wrote_new_index = index_chunks(paper_id, chunks)
        index_status = "已新建索引" if wrote_new_index else "已存在索引"
    except Exception as error:
        index_error = str(error)
        index_status = "向量索引不可用，已保留关键词检索 fallback"

left, right = st.columns([1, 1])

with left:
    st.subheader("论文信息")
    if parsed_pdf.title:
        st.write(f"**标题：** {parsed_pdf.title}")
    st.write(f"**文件名：** {parsed_pdf.filename}")
    st.write(f"**总页数：** {parsed_pdf.total_pages}")
    st.write(f"**Chunk 数：** {len(chunks)}")
    st.write(f"**Paper ID：** `{paper_id}`")
    st.write(f"**向量索引：** {index_status}")
    if index_error:
        st.warning(f"向量检索暂不可用：{index_error}")

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
st.subheader("检索问答")

question = st.text_input("输入你的问题", placeholder="例如：What does Figure 1 show?")
show_all_results = st.checkbox(
    "显示全部候选结果",
    value=False,
    help="用于调试检索召回。打开后会尽量展示所有候选 chunk，而不是只显示前几个。",
)
result_limit = st.slider(
    "显示结果数量",
    min_value=5,
    max_value=min(max(len(chunks), 5), 50),
    value=min(10, max(len(chunks), 5)),
    step=5,
    disabled=show_all_results,
)

if question:
    result_source = "keyword_fallback"
    results: list[RetrievalResult] = []
    top_k = len(chunks) if show_all_results else result_limit

    if requested_figure_numbers(question):
        figure_results = retrieve(question, chunks, top_k=top_k)
        results = [
            RetrievalResult(
                chunk=chunk,
                score=score,
                source="figure_anchor",
                why_selected="figure id detected; used figure_anchor priority rules",
            )
            for chunk, score in figure_results
        ]
        result_source = "figure_anchor"
    else:
        try:
            results = hybrid_search(paper_id, question, chunks, top_k=top_k)
            result_source = "hybrid"
        except Exception as error:
            st.warning(f"向量检索失败，已切换到关键词检索：{error}")

        if not results:
            keyword_results = retrieve(question, chunks, top_k=top_k)
            results = [
                RetrievalResult(
                    chunk=chunk,
                    score=score,
                    source="keyword_fallback",
                    why_selected="vector/hybrid unavailable; keyword fallback",
                )
                for chunk, score in keyword_results
            ]
            result_source = "keyword_fallback"

    if not results:
        st.warning("没有检索到相关 chunk。可以换一些论文中的关键词再试。")
    else:
        st.write(f"检索方式：`{result_source}`")
        st.write(f"检索到 {len(results)} 个候选 chunk：")

        llm_available = is_llm_available()
        if llm_available:
            st.caption(f"LLM：DeepSeek · `{get_model_name()}`")
        else:
            st.info(
                "尚未配置 `DEEPSEEK_API_KEY`。当前仍可查看检索结果；"
                "配置后即可生成基于论文证据的回答。"
            )

        result_signature = hashlib.sha256(
            "\x1f".join(
                f"{result.chunk.page}:{result.chunk.chunk_type}:{result.chunk.text}"
                for result in results
            ).encode("utf-8")
        ).hexdigest()[:12]
        answer_key = (
            f"qa_answer::{paper_id}::{question}::{result_source}::{result_signature}"
        )
        if st.button(
            "生成回答",
            type="primary",
            disabled=not llm_available,
            use_container_width=False,
        ):
            with st.spinner("正在基于论文证据生成回答..."):
                try:
                    st.session_state[answer_key] = generate_answer(question, results)
                except QAEngineError as error:
                    st.error(str(error))

        qa_response = st.session_state.get(answer_key)
        if qa_response is not None:
            st.markdown("### 小助手回答")
            st.markdown(qa_response.answer)
            st.caption(
                f"模型：{qa_response.model} · "
                f"送入 {len(qa_response.evidence)} 条证据 · "
                f"引用 {len(qa_response.cited_evidence_ids)} 条证据"
            )

            selected_ranks = {
                evidence.retrieval_rank for evidence in qa_response.evidence
            }
            omitted_ranks = [
                rank
                for rank in range(1, len(results) + 1)
                if rank not in selected_ranks
            ]
            with st.expander("本次发送给模型的证据"):
                for evidence in qa_response.evidence:
                    chunk = evidence.chunk
                    label = (
                        f"{evidence.evidence_id} · Page {chunk.page} · "
                        f"{chunk.chunk_type}"
                    )
                    if chunk.figure_id:
                        label += f" · {chunk.figure_id}"
                    st.markdown(f"**{label}**")
                    st.caption(
                        f"来自检索结果 #{evidence.retrieval_rank} · "
                        f"chunk_id: {evidence.chunk_id} · "
                        f"source: {evidence.retrieval_source} · "
                        f"score: {evidence.retrieval_score:.4f}"
                    )
                    st.write(chunk.text)
                if omitted_ranks:
                    omitted = ", ".join(f"#{rank}" for rank in omitted_ranks)
                    st.caption(
                        f"未发送的候选：{omitted}。原因通常是证据数量上限、"
                        "上下文长度上限或重复 chunk。"
                    )

            st.divider()
            st.markdown("### 检索结果")

        for index, result in enumerate(results, start=1):
            chunk = result.chunk
            title = f"#{index} · Page {chunk.page} · {chunk.chunk_type}"
            if chunk.figure_id:
                title += f" · {chunk.figure_id}"

            with st.expander(title, expanded=index == 1):
                st.markdown(f"**结果 #{index}**")
                st.caption(f"score: {result.score:.4f}")
                st.caption(f"source: {result.source}")
                if result.vector_score is not None:
                    st.caption(f"vector_score: {result.vector_score:.4f}")
                if result.keyword_score is not None:
                    st.caption(f"keyword_score: {result.keyword_score:.4f}")
                if result.matched_terms:
                    st.caption(f"matched_terms: {', '.join(result.matched_terms)}")
                if result.why_selected:
                    st.caption(f"why_selected: {result.why_selected}")
                metadata_parts = [
                    f"quality: {chunk.quality_score:.2f}",
                ]
                if chunk.section:
                    metadata_parts.append(f"section: {chunk.section}")
                if chunk.section_title:
                    metadata_parts.append(f"section_title: {chunk.section_title}")
                if chunk.paragraph_id:
                    metadata_parts.append(f"paragraph: {chunk.paragraph_id}")
                if chunk.source_block:
                    metadata_parts.append(f"source_block: {chunk.source_block}")
                st.caption(" · ".join(metadata_parts))
                st.write(chunk.text)
