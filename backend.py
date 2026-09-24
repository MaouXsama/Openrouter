import json
import os
import uuid
from typing import List, Optional
from urllib.parse import urlparse
import chromadb

import psycopg2
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from langchain_chroma import Chroma
from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI, OpenAIError
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from azure.storage.blob import BlobServiceClient

load_dotenv()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_EMBEDDING_MODEL = "nvidia/nemotron-3-embed-1b:free"
DEFAULT_FALLBACK_MODEL = "openrouter/free"

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    raise RuntimeError(
        "OPENROUTER_API_KEY was not found. Add it to a .env file next to backend.py."
    )

client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
model = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
fallback_model = os.getenv("OPENROUTER_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)

llm = ChatOpenAI(
    model=model,
    base_url=OPENROUTER_BASE_URL,
    api_key=api_key,
    extra_body={"models": [fallback_model]},
)

embeddings = OpenAIEmbeddings(
    model=DEFAULT_EMBEDDING_MODEL,
    base_url=OPENROUTER_BASE_URL,
    api_key=api_key,
    check_embedding_ctx_length=False,
    model_kwargs={"encoding_format": "float"},
)

CHROMA_HOST = os.environ.get("CHROMA_HOST") or os.environ.get("CHROMADB_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT") or os.environ.get("CHROMADB_PORT", "8000"))

chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)

vectorstore = Chroma(
    client=chroma_client,
    collection_name="pdf_chats",
    embedding_function=embeddings,
)

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "appdb"),
    "user": os.getenv("DB_USER", "azureadmin"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT", "5432"),
    "sslmode": "require"
}

AZURE_STORAGE_SAS_URL = os.getenv("AZURE_STORAGE_SAS_URL")
AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "pdf-container")


if not DB_CONFIG["host"] or not DB_CONFIG["password"]:
    raise RuntimeError("DB_HOST and DB_PASSWORD must be configured.")

def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()

def init_cloud_table():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS advanced_chats (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                pdf_path TEXT,
                pdf_name TEXT,
                pdf_uuid TEXT
            );
            """)
            conn.commit()
        conn.close()
        print("🚀 [Success] Cloud table 'advanced_chats' verified/created successfully.")
    except Exception as e:
        print(f"⚠️ [Warning] Cloud table initialization skipped or already exists: {str(e)}")

init_cloud_table()

def get_blob_container():
    if not AZURE_STORAGE_SAS_URL:
        raise RuntimeError("AZURE_STORAGE_SAS_URL is missing in .env file.")

    parsed_sas_url = urlparse(AZURE_STORAGE_SAS_URL)
    account_url = f"{parsed_sas_url.scheme}://{parsed_sas_url.netloc}"
    sas_token = parsed_sas_url.query
    if not parsed_sas_url.scheme or not parsed_sas_url.netloc or not sas_token:
        raise RuntimeError("AZURE_STORAGE_SAS_URL must be a full Azure Blob SAS URL.")

    blob_service_client = BlobServiceClient(account_url=account_url, credential=sas_token)
    container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER)
    
    try:
        if not container_client.exists():
            container_client.create_container()
            print(f"📁 [Cloud] Container '{AZURE_STORAGE_CONTAINER}' verified/created.")
    except Exception as e:
        print(f"⚠️ [Warning] Container auto-initialization status: {str(e)}")
    return container_client

class ChatRequest(BaseModel):
    messages: List[dict]

class SaveChatRequest(BaseModel):
    chat_id: str
    chat_name: str
    messages: List[dict]
    pdf_name: Optional[str] = None
    pdf_path: Optional[str] = None
    pdf_uuid: Optional[str] = None

class RAGChatRequest(BaseModel):
    messages: List[dict]
    pdf_uuid: str

class DeleteChatRequest(BaseModel):
    chat_id: str

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/chat/")
async def chat(request: ChatRequest):
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=request.messages,
            extra_body={"models": [fallback_model]},
        )
        content = completion.choices[0].message.content
        if not content:
            raise HTTPException(status_code=502, detail="The model returned an empty response.")
        return PlainTextResponse(content)

    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.post("/rag_chat/")
async def rag_chat(request: RAGChatRequest):
    try:
        chat_history = []
        for message in request.messages[:-1]:
            if message.get("role") == "user":
                chat_history.append(HumanMessage(content=message.get("content", "")))
            elif message.get("role") == "assistant":
                chat_history.append(AIMessage(content=message.get("content", "")))

        user_input = request.messages[-1]["content"] if request.messages else ""
        retriever = vectorstore.as_retriever(
            search_kwargs={
                "k": 4,
                "filter": {"pdf_uuid": request.pdf_uuid},
            }
        )

        contextualize_q_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Rewrite the user's latest question as a standalone question using the chat history when needed.",
                ),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
            ]
        )
        history_aware_retriever = create_history_aware_retriever(
            llm, retriever, contextualize_q_prompt
        )

        qa_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Answer using the provided PDF context. If the context does not contain the answer, say you do not know.\n\n{context}",
                ),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
            ]
        )
        question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
        rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

        response = rag_chain.invoke({"input": user_input, "chat_history": chat_history})
        answer = response.get("answer", "")
        if not answer:
            raise HTTPException(status_code=502, detail="The model returned an empty response.")
        return PlainTextResponse(answer)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/load_chat/")
async def load_chat(db: psycopg2.extensions.connection = Depends(get_db)):
    try:
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT id, name, file_path, pdf_name, pdf_path, pdf_uuid "
                "FROM advanced_chats ORDER BY last_update DESC"
            )
            rows = cursor.fetchall()

        records = []
        if not rows:
            return records

        container_client = get_blob_container()

        for row in rows:
            chat_id = row["id"]
            blob_name = f"chat_logs/{chat_id}.json"
            blob_client = container_client.get_blob_client(blob_name)

            if blob_client.exists():
                blob_data = blob_client.download_blob().readall()
                messages = json.loads(blob_data.decode('utf-8'))
            else:
                messages = []

            records.append(
                {
                    "id": chat_id,
                    "chat_name": row["name"],
                    "messages": messages,
                    "pdf_name": row["pdf_name"],
                    "pdf_path": row["pdf_path"],
                    "pdf_uuid": row["pdf_uuid"],
                }
            )

        return records

    except Exception as e:
        import traceback
        traceback.print_exc() 
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/save_chat/")
async def save_chat(request: SaveChatRequest, db: psycopg2.extensions.connection = Depends(get_db)):
    try:
        file_path = f"chat_logs/{request.chat_id}.json"
        chat_json_data = json.dumps(request.messages, ensure_ascii=False, indent=4)

        container_client = get_blob_container()
        blob_client = container_client.get_blob_client(file_path)
        blob_client.upload_blob(chat_json_data.encode('utf-8'), overwrite=True)

        with db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO advanced_chats (id, name, file_path, last_update, pdf_path, pdf_name, pdf_uuid)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
                ON CONFLICT (id)
                DO UPDATE SET name = EXCLUDED.name, 
                              file_path = EXCLUDED.file_path, 
                              last_update = CURRENT_TIMESTAMP, 
                              pdf_path = EXCLUDED.pdf_path, 
                              pdf_name = EXCLUDED.pdf_name, 
                              pdf_uuid = EXCLUDED.pdf_uuid
                """,
                (request.chat_id, request.chat_name, file_path, request.pdf_path, request.pdf_name, request.pdf_uuid),
            )
        db.commit()
        return {"message": "Chat saved successfully in cloud structure"}

    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc() 
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/delete_chat/")
async def delete_chat(request: DeleteChatRequest, db: psycopg2.extensions.connection = Depends(get_db)):
    try:
        file_path = None
        with db.cursor() as cursor:
            cursor.execute("SELECT file_path FROM advanced_chats WHERE id = %s", (request.chat_id,))
            result = cursor.fetchone()
            if result:
                file_path = result[0]
            else:
                raise HTTPException(status_code=404, detail="Chat not found")

        with db.cursor() as cursor:
            cursor.execute("DELETE FROM advanced_chats WHERE id = %s", (request.chat_id,))
        db.commit()

        if file_path:
            container_client = get_blob_container()
            blob_client = container_client.get_blob_client(file_path)
            if blob_client.exists():
                blob_client.delete_blob()

        return {"message": "Chat deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    try:
        pdf_uuid = str(uuid.uuid4())
        file_path = f"pdf_store/{pdf_uuid}_{file.filename}"
        pdf_content = await file.read()

        container_client = get_blob_container()
        blob_client = container_client.get_blob_client(file_path)
        blob_client.upload_blob(pdf_content, overwrite=True)

        os.makedirs("pdf_store", exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(pdf_content)

        loader = PyPDFLoader(file_path)
        documents = loader.load()
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        texts = text_splitter.split_documents(documents)

        vectorstore.add_texts(
            [doc.page_content for doc in texts],
            ids=[str(uuid.uuid4()) for _ in texts],
            metadatas=[
                {"pdf_uuid": pdf_uuid, "pdf_name": file.filename}
                for _ in texts
            ],
        )

        if os.path.exists(file_path):
            os.remove(file_path)

        return {
            "pdf_uuid": pdf_uuid,
            "pdf_name": file.filename,
            "pdf_path": file_path
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
