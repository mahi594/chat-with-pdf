import os
import shutil
import hashlib
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from dotenv import load_dotenv

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq

from linking import build_phase4_links
from make_chunks import make_chunks
from embedding import build_chroma_index


# ---------------- Load env ----------------
load_dotenv()

UPLOAD_DIR = "data/uploads"
CACHE_DIR = "data/cache"
CHROMA_DIR = "data/chroma_db"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(CHROMA_DIR, exist_ok=True)

app = FastAPI(title="Chat With PDF Backend")


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

    # If already processed
    if os.path.exists(chroma_path):
        return {
            "message": "PDF already uploaded and indexed",
            "file_hash": file_hash
        }

    # ---------------- Phase 4 ----------------
    build_phase4_links(upload_path, phase4_path)

    # ---------------- Phase 5 ----------------
    make_chunks(phase4_path, chunks_path)

    # ---------------- Phase 6 ----------------
    build_chroma_index(chunks_path, chroma_path)

    return {
    "message": "PDF uploaded successfully",
    "file_hash": file_hash,
    "stats": {
        "total_pages": parsed_data.get("total_pages", 0),
        "text_blocks": len(parsed_data.get("text_blocks", [])),
        "tables": len(parsed_data.get("tables", [])),
        "images": len(parsed_data.get("images_found", [])) if "images_found" in parsed_data else 0,
        "ocr_blocks": len(parsed_data.get("images_and_flowcharts", [])) if "images_and_flowcharts" in parsed_data else 0
    }
}


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
