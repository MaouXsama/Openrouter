import uuid
import requests
import streamlit as st
import os


st.set_page_config(page_title="Chatbot Client", layout="wide")

st.title("Chatbot Stage5 (frontend + backend + database + RAG + Docker compose + Azure VM)")

# 💡 توحيد الرابط الأساسي للـ Backend

#BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:5000")

LOAD_CHAT_URL = f"{BACKEND_URL}/load_chat/"
SAVE_CHAT_URL = f"{BACKEND_URL}/save_chat/"
DELETE_CHAT_URL = f"{BACKEND_URL}/delete_chat/"
UPLOAD_PDF_URL = f"{BACKEND_URL}/upload_pdf/"
CHAT_URL = f"{BACKEND_URL}/chat/"
RAG_CHAT_URL = f"{BACKEND_URL}/rag_chat/"

if "history_chats" not in st.session_state:
    st.session_state["history_chats"] = []
if "current_chat" not in st.session_state:
    st.session_state["current_chat"] = None
if "chat_names" not in st.session_state:
    st.session_state["chat_names"] = {}
if "chats_loaded" not in st.session_state:
    st.session_state["chats_loaded"] = False

# =====================================================================
# 2. تعريف الدوال البرمجية للاتصال بالسيرفر وإدارة الجلسات
# =====================================================================

def load_chats_from_db():
    try:
        response = requests.get(LOAD_CHAT_URL, timeout=5)
        response.raise_for_status()
    except requests.RequestException as error:
        st.error(f"Could not reach the backend: {error}")
        return

    st.session_state["history_chats"] = []
    for record in response.json():
        chat_id = record["id"]
        st.session_state["history_chats"].append(
            {
                "id": chat_id,
                "messages": record["messages"],
                "pdf_name": record.get("pdf_name"),
                "pdf_path": record.get("pdf_path"),
                "pdf_uuid": record.get("pdf_uuid"),
            }
        )
        st.session_state["chat_names"][chat_id] = record["chat_name"]


def save_chat_to_db(chat_id, chat_name, messages, pdf_name, pdf_path, pdf_uuid):
    payload = {
        "chat_id": chat_id,
        "chat_name": chat_name,
        "messages": messages,
        "pdf_name": pdf_name,
        "pdf_path": pdf_path,
        "pdf_uuid": pdf_uuid,
    }
    try:
        response = requests.post(SAVE_CHAT_URL, json=payload)
        response.raise_for_status()
    except requests.RequestException as error:
        st.error(f"Failed to save chat: {error}")

def delete_chat():
    chat_id = st.session_state["current_chat"]
    if not chat_id:
        return
    payload = {"chat_id": chat_id}
    try:
        response = requests.post(DELETE_CHAT_URL, json=payload)
        response.raise_for_status()
        st.session_state["history_chats"] = [c for c in st.session_state["history_chats"] if c["id"] != chat_id]
        if chat_id in st.session_state["chat_names"]:
            del st.session_state["chat_names"][chat_id]
        st.session_state["current_chat"] = None
        st.rerun()
    except requests.RequestException as error:
        st.error(f"Failed to delete chat: {error}")

def select_chat(chat_id):
    """💡 تحديث الجلسة النشطة المستدعاة في أداة الـ radio"""
    st.session_state["current_chat"] = chat_id

def create_chat_with_pdf(chat_name, uploaded_pdf):
    with st.spinner("Uploading and processing document, please wait..."):
        files = {"file": (uploaded_pdf.name, uploaded_pdf.getvalue(), "application/pdf")}
        try:
            response = requests.post(UPLOAD_PDF_URL, files=files)
            response.raise_for_status()
        except requests.RequestException as error:
            st.error(f"Failed to upload PDF: {error}")
            return

        pdf_path = response.json()["pdf_path"]
        pdf_uuid = response.json()["pdf_uuid"]

        new_chat_id = str(uuid.uuid4())
        new_chat = {
            "id": new_chat_id,
            "messages": [],
            "pdf_name": uploaded_pdf.name,
            "pdf_path": pdf_path,
            "pdf_uuid": pdf_uuid,
        }
        st.session_state["history_chats"].insert(0, new_chat)
        st.session_state["chat_names"][new_chat_id] = chat_name
        st.session_state["current_chat"] = new_chat_id
        save_chat_to_db(new_chat_id, chat_name, [], uploaded_pdf.name, pdf_path, pdf_uuid)
        st.success("PDF uploaded and chat created.")
        st.rerun()


def create_chat(chat_name):
    new_chat_id = str(uuid.uuid4())
    new_chat = {"id": new_chat_id, "messages": [], "pdf_name": None, "pdf_path": None, "pdf_uuid": None}
    st.session_state["history_chats"].insert(0, new_chat)
    st.session_state["chat_names"][new_chat_id] = chat_name
    st.session_state["current_chat"] = new_chat_id
    save_chat_to_db(new_chat_id, chat_name, [], None, None, None)
    st.rerun()

# تحميل المحادثات مرة واحدة عند إقلاع التطبيق
if not st.session_state["chats_loaded"]:
    load_chats_from_db()
    st.session_state["chats_loaded"] = True

# =====================================================================
# 3. بناء واجهة التوجيه الجانبية (Sidebar)
# =====================================================================
with st.sidebar:
    st.title("Chat Management")

    uploaded_pdf = st.file_uploader("Upload PDF", type="pdf", key="pdf_uploader")
    chat_name_input = st.text_input("Enter Chat Name:", key="new_chat_name")

    if st.button("Create New Chat"):
        if chat_name_input.strip():
            create_chat(chat_name_input.strip())
        else:
            st.warning("Chat name cannot be empty.")

    if st.button("Create New Chat with PDF"):
        if not uploaded_pdf:
            st.warning("Please upload a PDF file before creating the chat.")
        elif chat_name_input.strip():
            create_chat_with_pdf(chat_name_input.strip(), uploaded_pdf)
        else:
            st.warning("Chat name cannot be empty.")

    if st.session_state["history_chats"]:
        chat_options = {
            chat["id"]: st.session_state["chat_names"][chat["id"]]
            for chat in st.session_state["history_chats"]
        }
        
        # ضبط الفهرس النشط الآمن تلافياً لأخطاء الـ Index
        current_id = st.session_state["current_chat"]
        if current_id not in chat_options:
            current_id = list(chat_options.keys())[0] if chat_options else None
            st.session_state["current_chat"] = current_id

        if current_id:
            selected_chat = st.radio(
                "Select Chat",
                options=list(chat_options.keys()),
                format_func=lambda x: chat_options[x],
                index=list(chat_options.keys()).index(current_id),
                key="chat_selector",
                on_change=lambda: select_chat(st.session_state.chat_selector),
            )
            st.session_state["current_chat"] = selected_chat

        st.button("Delete Chat", on_click=delete_chat, type="primary")

# =====================================================================
# 4. إعداد نطاق الكائنات والمحتوى الرئيسي الآمن (Main Screen Context)
# =====================================================================
current_chat = None
chat_id = st.session_state["current_chat"]
chat_name = st.session_state["chat_names"].get(chat_id, "Untitled Chat")

if chat_id:
    for chat_session in st.session_state["history_chats"]:
        if chat_session["id"] == chat_id:
            current_chat = chat_session
            break

# عرض المحادثات والصندوق الرئيسي إذا تم تحديد غرفة شات
if current_chat:
    if current_chat.get("pdf_name"):
        st.info(f"📄 Connected Context: **{current_chat['pdf_name']}** (Using RAG)")
    else:
        st.caption("🌐 Standard Chat Mode")

    # طباعة تاريخ المحادثة التفاعلي الفعال
    for message in current_chat["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # صندوق الإدخال الذكي والوحيد بالصفحة (يقوم بالتوجيه التلقائي وفقاً لنوع الشات)
    if prompt := st.chat_input("Your Message:"):
        current_chat["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            payload = {
                "messages": [
                    {"role": m["role"], "content": m["content"]}
                    for m in current_chat["messages"]
                ]
            }

            # توجيه الطلب لرابط الـ RAG أو الشات العادي بشكل آلي
            if current_chat.get("pdf_uuid"):
                payload["pdf_uuid"] = current_chat["pdf_uuid"]
                chat_target_url = RAG_CHAT_URL
            else:
                chat_target_url = CHAT_URL

            def get_stream_response():
                with requests.post(chat_target_url, json=payload, stream=True, timeout=90) as r:
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
                        if chunk:
                            yield chunk

            try:
                response = st.write_stream(get_stream_response())
                current_chat["messages"].append({"role": "assistant", "content": response})
                
                # تحديث الحفظ التلقائي بقاعدة البيانات
                save_chat_to_db(
                    chat_id,
                    chat_name,
                    current_chat["messages"],
                    current_chat.get("pdf_name"),
                    current_chat.get("pdf_path"),
                    current_chat.get("pdf_uuid"),
                )
            except requests.RequestException as error:
                st.error(f"Backend request failed: {error}")
                current_chat["messages"].pop()
else:
    st.info("👈 Please select an existing chat or create a new one from the sidebar to begin!")

#python -m streamlit run frontend.py
