import os
import shutil
import hashlib
import json

from fastapi import FastAPI, UploadFile, File, Body
import requests
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq

from linking import build_phase4_links
from make_chunks import make_chunks
from embedding import build_chroma_index

from pdf_inspection import analyze_pdf


# ---------------- Load env ----------------
load_dotenv()

UPLOAD_DIR = "data/uploads"
CACHE_DIR = "data/cache"
CHROMA_DIR = "data/chroma_db"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(CHROMA_DIR, exist_ok=True)

# ---------------- Create App ----------------
app = FastAPI(title="Chat With PDF Backend")


# ---------------- Add CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# ---------------- Helper: Hash PDF ----------------
def get_file_hash(file_path):
    with open(file_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


# ---------------- Upload Endpoint ----------------
@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):

    temp_path = f"temp_{file.filename}"

    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_hash = get_file_hash(temp_path)

    upload_path = os.path.join(UPLOAD_DIR, f"{file_hash}.pdf")
    phase4_path = os.path.join(CACHE_DIR, f"{file_hash}_phase4.json")
    chunks_path = os.path.join(CACHE_DIR, f"{file_hash}_chunks.json")
    chroma_path = os.path.join(CHROMA_DIR, file_hash)

    # Save PDF permanently
    if not os.path.exists(upload_path):
        shutil.copy(temp_path, upload_path)

    os.remove(temp_path)
    
    stats = analyze_pdf(upload_path)

    # If already processed
    if os.path.exists(chroma_path) and os.path.exists(phase4_path):
        
        return {
            "success": True,
            "message": "PDF already uploaded and indexed",
            "file_hash": file_hash,
            "filename": file.filename,
            "pages": stats.get("pages", 0),
            "words": stats.get("words", 0),
            "tables": stats.get("tables", 0),
            "images": stats.get("images", 0),
            "flowcharts": stats.get("flowcharts_or_graphs", 0)
        }
        

    # Phase 4
    parsed_data = build_phase4_links(upload_path, phase4_path)

    # Phase 5
    make_chunks(phase4_path, chunks_path)

    # Phase 6
    build_chroma_index(chunks_path, chroma_path)

    return {
        "success": True,
        "message": "PDF uploaded successfully",
        "file_hash": file_hash,
        "filename": file.filename,
        "pages": stats.get("pages", 0),
        "words": stats.get("words", 0),
        "tables": stats.get("tables", 0),
        "images": stats.get("images", 0),
        "flowcharts": stats.get("flowcharts_or_graphs", 0)
    }

@app.post("/upload_url")
async def upload_pdf_url(payload: dict = Body(...)):
    url = payload.get("url")

    if not url:
        return {"success": False, "message": "No URL provided"}

    try:
        r = requests.get(url, stream=True, timeout=20)

        if r.status_code != 200:
            return {"success": False, "message": "Unable to download PDF from URL"}

        temp_path = "temp_downloaded.pdf"

        with open(temp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)

        file_hash = get_file_hash(temp_path)

        upload_path = os.path.join(UPLOAD_DIR, f"{file_hash}.pdf")
        phase4_path = os.path.join(CACHE_DIR, f"{file_hash}_phase4.json")
        chunks_path = os.path.join(CACHE_DIR, f"{file_hash}_chunks.json")
        chroma_path = os.path.join(CHROMA_DIR, file_hash)

        if not os.path.exists(upload_path):
            shutil.copy(temp_path, upload_path)

        os.remove(temp_path)

        stats = analyze_pdf(upload_path)

        if os.path.exists(chroma_path) and os.path.exists(phase4_path):
            return {
                "success": True,
                "message": "PDF already uploaded and indexed",
                "file_hash": file_hash,
                "filename": os.path.basename(url),
                "pages": stats.get("pages", 0),
                "words": stats.get("words", 0),
                "tables": stats.get("tables", 0),
                "images": stats.get("images", 0),
                "flowcharts": stats.get("flowcharts_or_graphs", 0)
            }

        build_phase4_links(upload_path, phase4_path)
        make_chunks(phase4_path, chunks_path)
        build_chroma_index(chunks_path, chroma_path)

        return {
            "success": True,
            "message": "PDF uploaded successfully from URL",
            "file_hash": file_hash,
            "filename": os.path.basename(url),
            "pages": stats.get("pages", 0),
            "words": stats.get("words", 0),
            "tables": stats.get("tables", 0),
            "images": stats.get("images", 0),
            "flowcharts": stats.get("flowcharts_or_graphs", 0)
        }

    except Exception as e:
        return {"success": False, "message": str(e)}
   
# ---------------- Question Model ----------------
class QuestionRequest(BaseModel):
    file_hash: str
    question: str
    


# ---------------- Ask Endpoint ----------------
@app.post("/ask")
async def ask_question(req: QuestionRequest):

    chroma_path = os.path.join(CHROMA_DIR, req.file_hash)

    if not os.path.exists(chroma_path):
        return {"error": "PDF not indexed. Upload PDF first."}

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    vector_db = Chroma(
        persist_directory=chroma_path,
        embedding_function=embeddings
    )
    
    search_query = f"""
Find the abstract, introduction, methodology, dataset, models used, results and conclusion.
User question: {req.question}
"""

    retrieved_docs = vector_db.similarity_search(search_query, k=15)

    context = ""
    pages_used = set()

    for i, doc in enumerate(retrieved_docs, start=1):
       context += f"\n================ CHUNK {i} ================\n"
       context += doc.page_content + "\n\n"

       meta = doc.metadata
       if meta.get("page"):
         pages_used.add(int(meta["page"]))

    pages_used = sorted(list(pages_used))
    
    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0,
        groq_api_key=os.getenv("GROQ_API_KEY")
    )

    prompt = f"""
You are an expert PDF assistant.

RULES:
1. Use ONLY the given CONTEXT.
2. Do NOT use outside knowledge.
3. You ARE allowed to summarize and combine information from multiple chunks.
4. If the context contains partial information, give the best possible answer.
5. Only say "Not found in the document." if the context is completely irrelevant.

OUTPUT FORMAT:
Answer:
<summary in 15-20 lines>

Key Points:
- point 1
- point 2
- point 3

Context Used:
Pages: {pages_used}

CONTEXT:
{context}

QUESTION:
{req.question}

FINAL RESPONSE:
"""

    response = llm.invoke(prompt)

    return {
        "question": req.question,
        "answer": response.content,
        "pages_used": pages_used
    }


# ---------------- List Uploaded PDFs ----------------
@app.get("/list_pdfs")
async def list_pdfs():
    pdfs = []
    for f in os.listdir(UPLOAD_DIR):
        if f.endswith(".pdf"):
            pdfs.append(f.replace(".pdf", ""))
    return {"pdf_hashes": pdfs}


@app.get("/pdf/{file_hash}")
async def get_pdf(file_hash: str):
    pdf_path = os.path.join(UPLOAD_DIR, f"{file_hash}.pdf")

    if not os.path.exists(pdf_path):
        return {"error": "PDF not found"}

    return FileResponse(pdf_path, media_type="application/pdf")