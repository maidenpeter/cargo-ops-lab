import streamlit as st

from lab import ask as A
from lab import ui

ui.page("ask")
live = A.api_key() is not None
ui.short(
    "Have a question the pages do not answer straight away?",
    "Ask it here in your own words, or pick one below. The answers come from the lab's stored results and glossary, "
    "so every number matches the pages. You can also paste a shipment number, such as AWB0192080.",
    "Not everyone wants to read charts. A question in plain words deserves an answer in plain words, with a pointer "
    "to the page that shows the evidence.",
)
ui.note(f"Answers are written by an AI model from the lab's stored facts only. Each visit can ask up to "
        f"{A.MAX_QUESTIONS} questions." if live else
        "Answers are matched from the lab's stored results, so they are fixed and always the same. Nothing you type "
        "leaves the app.")


def md(text: str) -> str:
    """Plain text for st.markdown: no HTML, and dollar amounts not read as math."""
    return ui.esc(text).replace("$", "\\$")

if "chat" not in st.session_state:
    st.session_state.chat = []
chat = st.session_state.chat
asked = sum(1 for m in chat if m["role"] == "user")

pick = st.pills("Try one of these", A.SUGGESTIONS, selection_mode="single", key=f"pick_{asked}")
typed = st.chat_input("Ask about the lab, a measure, a word, or a shipment number")
question = typed or pick

for m in chat:
    with st.chat_message(m["role"], avatar=":material/person:" if m["role"] == "user" else ":material/flight_land:"):
        st.markdown(md(m["content"]))
        if m.get("page"):
            p = ui.PAGE[m["page"]]
            st.page_link(p["file"], label=f"See the evidence: {p['nav']}", icon=":material/arrow_forward:")

if question:
    if live and st.session_state.get("n_asked", 0) >= A.MAX_QUESTIONS:
        st.info("That is the limit for this visit. The suggested questions above are answered on the pages too.")
    else:
        st.session_state.n_asked = st.session_state.get("n_asked", 0) + 1  # not reset by a new conversation
        chat.append({"role": "user", "content": question})
        with st.chat_message("user", avatar=":material/person:"):
            st.markdown(md(question))
        with st.chat_message("assistant", avatar=":material/flight_land:"):
            text, page = A.answer(question)
            if live:
                text = st.write_stream(A.claude_stream(chat))
                text = text if isinstance(text, str) else "".join(text)
            else:
                st.markdown(md(text))
            if page:
                p = ui.PAGE[page]
                st.page_link(p["file"], label=f"See the evidence: {p['nav']}", icon=":material/arrow_forward:")
        chat.append({"role": "assistant", "content": text, "page": page})
        st.rerun()

if chat:
    if st.button("Start a new conversation", icon=":material/refresh:"):
        st.session_state.chat = []
        st.rerun()
ui.footer()
