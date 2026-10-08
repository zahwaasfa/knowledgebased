"""Arcana Bappenas Chatbot - Streamlit entrypoint (via KB API).

UI design:
    - Clean header with online status.
    - Welcome message tailored for Kementerian PPN/Bappenas.
    - Quick-reply buttons for fast queries.
    - Responsive chat layout with smooth scrolling.
"""
from __future__ import annotations

import logging
import os
import uuid
import requests
import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

# ---------------------------------------------------------------------------
# 1. Page Config (Layout terpusat & sidebar disembunyikan persis app.py)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ARCANA - Asisten Knowledge Base Bappenas",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Logging & Konfigurasi API
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("arcana.app")

# Ambil endpoint API dari environment Docker (default: kb-api:8000 atau localhost:8000)
API = os.getenv("KB_API_URL", "http://kb-api:8000")

# ---------------------------------------------------------------------------
# Asset Maskot Avatar ARCANA (Data URI SVG)
# ---------------------------------------------------------------------------
ARCANA_BOT_AVATAR = (
    "data:image/svg+xml;utf8,"
    "%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%20100%20100%22%20width%3D%22100%25%22%20height%3D%22100%25%22%3E"
    "%3Crect%20width%3D%22100%22%20height%3D%22100%22%20rx%3D%2226%22%20fill%3D%22%23123B88%22/%3E"
    "%3Ccircle%20cx%3D%2250%22%20cy%3D%2222%22%20r%3D%228%22%20fill%3D%22%2349C3F8%22/%3E"
    "%3Cpath%20d%3D%22M%2018%2036%20C%2018%2028%2C%2082%2028%2C%2082%2036%20L%2082%2072%20C%2082%2082%2C%2018%2082%2C%2018%2072%20Z%22%20fill%3D%22%231B56D3%22/%3E"
    "%3Cellipse%20cx%3D%2236%22%20cy%3D%2256%22%20rx%3D%2211%22%20ry%3D%2214%22%20fill%3D%22%23FFFFFF%22/%3E"
    "%3Cellipse%20cx%3D%2264%22%20cy%3D%2256%22%20rx%3D%2211%22%20ry%3D%2214%22%20fill%3D%22%23FFFFFF%22/%3E"
    "%3Cpath%20d%3D%22M%2046%2071%20Q%2050%2075%2054%2071%22%20stroke%3D%22%23FFFFFF%22%20stroke-width%3D%222%22%20fill%3D%22none%22%20stroke-linecap%3D%22round%22/%3E"
    "%3C/svg%3E"
)

# ---------------------------------------------------------------------------
# Global CSS (Persis styling custom app.py)
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
        [data-testid="stSidebar"], [data-testid="collapsedControl"] {
            display: none !important;
        }
        .block-container {
            padding-top: 2.5rem !important;
            padding-bottom: 7rem !important;
            max-width: 780px;
        }
        html, body, [data-testid="stAppViewContainer"] {
            overflow-y: auto !important;
            height: 100%;
        }
        .arcana-header {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 14px 20px;
            border-radius: 14px;
            background: linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 100%);
            color: #ffffff;
            box-shadow: 0 4px 14px rgba(30, 58, 138, 0.25);
            margin-bottom: 1.5rem;
            margin-top: 0.5rem;
        }
        .arcana-avatar {
            width: 44px;
            height: 44px;
            border-radius: 50%;
            background-color: #ffffff;
            background-size: cover;
            background-position: center;
            flex-shrink: 0;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
        }
        .arcana-titles {
            display: flex;
            flex-direction: column;
            line-height: 1.25;
        }
        .arcana-name {
            font-size: 1.2rem;
            font-weight: 700;
            letter-spacing: 0.5px;
        }
        .arcana-status {
            font-size: 0.8rem;
            opacity: 0.95;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            margin-top: 4px;
        }
        .arcana-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #34d399;
            display: inline-block;
        }
        .stChatMessage {
            padding-top: 0.6rem;
            padding-bottom: 0.6rem;
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]),
        .stChatMessage:has([data-testid="chatAvatarIcon-user"]) {
            flex-direction: row-reverse !important;
            text-align: right !important;
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"],
        .stChatMessage:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] {
            background-color: #1976D2 !important;
            color: #FFFFFF !important;
            border-radius: 18px 18px 4px 18px !important;
            padding: 12px 18px !important;
            display: inline-block !important;
            text-align: left !important;
            box-shadow: 0 1px 3px rgba(25, 118, 210, 0.15) !important;
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) p,
        .stChatMessage:has([data-testid="chatAvatarIcon-user"]) p {
            color: #FFFFFF !important;
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]),
        .stChatMessage:has([data-testid="chatAvatarIcon-assistant"]) {
            flex-direction: row !important;
            text-align: left !important;
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"],
        .stChatMessage:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] {
            background-color: #F8FAFC !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 4px 18px 18px 18px !important;
            padding: 14px 18px !important;
            color: #1E293B !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02) !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session State Init
# ---------------------------------------------------------------------------
def init_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "Halo, ada yang bisa saya bantu? "
                    "Saya ARCANA — Asisten cerdas Knowledge Base Kementerian PPN/Bappenas. "
                    "Layanan ini dikonfigurasi untuk menyajikan informasi berbasis data dokumen perencanaan pembangunan, "
                    "laporan kinerja, regulasi, serta tata kelola data Pusdatinrenbang.\n\n"
                    "Silakan pilih topik atau ketik pertanyaan perencanaan Anda di bawah."
                ),
                "citations": [],
            }
        ]
    if "history" not in st.session_state:
        st.session_state.history = []
    if "pengguna_id" not in st.session_state:
        st.session_state.pengguna_id = "user_" + uuid.uuid4().hex[:12]

# ---------------------------------------------------------------------------
# Header Component
# ---------------------------------------------------------------------------
def render_header() -> None:
    st.markdown(
        f"""
        <div class="arcana-header">
            <div class="arcana-avatar" style="background-image: url('{ARCANA_BOT_AVATAR}');"></div>
            <div class="arcana-titles">
                <span class="arcana-name">ARCANA</span>
                <span class="arcana-status">
                    <span class="arcana-dot"></span> Online &nbsp;·&nbsp; Asisten Knowledge Base Bappenas
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Quick replies
# ---------------------------------------------------------------------------
QUICK_REPLIES = [
    "Apa manfaat Laporan Kinerja Kementerian PPN/Bappenas 2025?",
    "Regulasi apa yang menjadi landasan laporan kinerja?",
    "Bagaimana proses penyusunan laporan perkembangan ekonomi?",
]

def render_quick_replies() -> None:
    if len(st.session_state.messages) > 1:
        return
    for q in QUICK_REPLIES:
        if st.button(q, key=f"quick_{q[:20]}", use_container_width=True):
            st.session_state["pending_input"] = q

# ---------------------------------------------------------------------------
# Turn handler (Menghubungkan pertanyaan ke endpoint KB API)
# ---------------------------------------------------------------------------
def answer_turn(question: str) -> None:
    st.session_state.messages.append({"role": "user", "content": question, "citations": []})
    st.session_state.history.append(HumanMessage(content=question))
    
    with st.chat_message("user", avatar="🧑"):
        st.markdown(question)

    with st.chat_message("assistant", avatar=ARCANA_BOT_AVATAR):
        with st.spinner("Arcana sedang memeriksa data graf Bappenas..."):
            citations = []
            try:
                # Memanggil service kb-api sama seperti di app2.py
                response = requests.post(
                    f"{API}/kb/query",
                    json={"question": question, "top_k": 5},
                    timeout=(10, 300),
                )
                response.raise_for_status()
                data = response.json()
                
                answer = data.get("answer", "Maaf, tidak dapat menemukan jawaban terkait.")
                citations = data.get("citations", [])
            except Exception as exc:
                logger.exception("Chat turn failed.")
                answer = (
                    "Maaf, terjadi kendala saat menghubungi basis data pengetahuan. "
                    f"Keterangan: {exc}"
                )

        st.markdown(answer)
        
        # Tampilkan sitasi sumber dalam accordion rapi di bawah bubble
        if citations:
            with st.expander(f"📚 Lihat {len(citations)} Sitasi Dokumen"):
                for i, c in enumerate(citations, 1):
                    breadcrumb = (c.get("breadcrumb") or "").split(" > ")[-1]
                    st.markdown(f"**[{i}] {c.get('title')}** — _{breadcrumb}_")
                    st.caption(f"{c.get('doc_id')} | {c.get('chunk_id')} | Halaman: {c.get('page') or '-'}")
                    st.write(c.get("snippet"))
                    if c.get("url"):
                        st.markdown(f"[Buka Dokumen]({c['url']})")
                    st.divider()

    st.session_state.messages.append({"role": "assistant", "content": answer, "citations": citations})
    st.session_state.history.append(AIMessage(content=answer))

# ---------------------------------------------------------------------------
# Main Routine
# ---------------------------------------------------------------------------
def main() -> None:
    init_state()
    render_header()

    # Tampilkan riwayat chat yang tersimpan
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar=("🧑" if msg["role"] == "user" else ARCANA_BOT_AVATAR)):
            st.markdown(msg["content"])
            if msg.get("citations"):
                with st.expander(f"📚 Lihat {len(msg['citations'])} Sitasi Dokumen"):
                    for i, c in enumerate(msg["citations"], 1):
                        breadcrumb = (c.get("breadcrumb") or "").split(" > ")[-1]
                        st.markdown(f"**[{i}] {c.get('title')}** — _{breadcrumb}_")
                        st.caption(f"{c.get('doc_id')} | {c.get('chunk_id')} | Halaman: {c.get('page') or '-'}")
                        st.write(c.get("snippet"))
                        if c.get("url"):
                            st.markdown(f"[Buka Dokumen]({c['url']})")
                        st.divider()

    render_quick_replies()

    if "pending_input" in st.session_state and st.session_state["pending_input"]:
        q = st.session_state.pop("pending_input")
        answer_turn(q)
        st.rerun()

    if user_input := st.chat_input("Tulis pertanyaan seputar perencanaan pembangunan Bappenas..."):
        answer_turn(user_input)

if __name__ == "__main__":
    main()