import os
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq


def run_rag_query(file_hash, query, k=6):

    load_dotenv()

    chroma_path = f"data/chroma_db/{file_hash}"

    if not os.path.exists(chroma_path):
        raise FileNotFoundError(f" Chroma DB not found: {chroma_path}")

    print(" Loading embedding model...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    print(" Loading ChromaDB...")
    vector_db = Chroma(
        persist_directory=chroma_path,
        embedding_function=embeddings
    )

    print(" Searching relevant chunks...")
    retrieved_docs = vector_db.similarity_search(query, k=k)

    context = ""
    sources = set()

    for i, doc in enumerate(retrieved_docs, start=1):
        context += f"\n--- Retrieved Chunk {i} ---\n"
        context += doc.page_content + "\n\n"

        meta = doc.metadata

        # Add page source
        if meta.get("page"):
            sources.add(f"Page {meta['page']}")

        # Add citations (table/figure captions)
        if meta.get("citations"):
            citations_text = meta["citations"].strip()
            if citations_text:
                for c in citations_text.split(","):
                    sources.add(c.strip())

    sources = sorted(list(sources))

    print(" Sending context to Groq LLM...")

    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0,
        groq_api_key=os.getenv("GROQ_API_KEY")
    )

    prompt = f"""
You are an expert assistant for answering questions from a PDF document using Retrieval-Augmented Generation (RAG).

STRICT RULES (MUST FOLLOW):
1. Use ONLY the provided CONTEXT below.
2. Do NOT use outside knowledge.
3. Do NOT guess or hallucinate.
4. If the answer is not explicitly present in the context, respond exactly:
   Not found in the document.
5. If the user asks for values (accuracy, numbers, formulas), give EXACT values.
6. If the question refers to a table/figure, explicitly mention the table/figure name.
7. Be accurate and professional.

ANSWER STYLE:
- Give the answer in 5-10 lines.
- Use bullet points if needed.
- Keep it clear and direct.
- Do not add extra unrelated explanations.

OUTPUT FORMAT (MUST FOLLOW EXACTLY):

Answer:
<your answer>

Key Evidence (quote or short extracted lines from context):
- <evidence 1>
- <evidence 2>

Context Used:
- Page numbers / Table / Figure names

Context:
{context}

Question:
{query}

Answer:
"""

    response = llm.invoke(prompt)

    print("\n================== FINAL ANSWER ==================\n")
    print(response.content)

    print("\n================== SOURCES USED ==================\n")
    if sources:
        for s in sources:
            print("", s)
    else:
        print("No sources found.")


if __name__ == "__main__":

    file_hash = "962ae562ca933789fddeee27ca086458"

    query = input("\nAsk a question: ")

    run_rag_query(file_hash, query, k=6)
