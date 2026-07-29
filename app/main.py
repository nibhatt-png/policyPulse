import streamlit as st
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
load_dotenv()

from rag.retriever import retrieve
from rag.synthesizer import synthesize
st.set_page_config(page_title="PolicyPulse", page_icon="🌿")
st.title("🌿 PolicyPulse")
st.caption("Ask questions about environmental legislation.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if query := st.chat_input("Ask about environmental policy..."):
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("Searching documents..."):
            chunks = retrieve(query, top_k=5)
            answer = synthesize(query, chunks)

        st.markdown(answer)

        if chunks:
            with st.expander(f"📄 {len(chunks)} sources"):
                for c in chunks:
                    st.markdown(f"**{c['source']}** ({c['doc_type']}, {c['date']})")
                    st.caption(c["content"][:300] + "...")
                    st.divider()

    st.session_state.messages.append({"role": "assistant", "content": answer})