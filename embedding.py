import json
import os
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings


def build_chroma_index(chunks_json_path, chroma_save_path):

    if not os.path.exists(chunks_json_path):
        raise FileNotFoundError(f" Chunks file not found: {chunks_json_path}")

    with open(chunks_json_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    texts = [chunk["text"] for chunk in chunks]

    metadatas = []
    ids = []

    for chunk in chunks:
        ids.append(chunk["chunk_id"])

        citations_list = chunk.get("citations", [])

        # Convert list citations to string (Chroma does not allow list)
        if isinstance(citations_list, list):
            citations_str = ", ".join(citations_list)
        else:
            citations_str = str(citations_list)

        metadatas.append({
            "chunk_id": chunk["chunk_id"],
            "page": int(chunk["page"]),
            "citations": citations_str,
            "chunk_type": chunk["chunk_type"]
        })

    print(" Total chunks loaded:", len(texts))

    print("🔄 Loading embedding model...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    print("🔄 Creating ChromaDB persistent database...")

    vector_db = Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        ids=ids,
        persist_directory=chroma_save_path
    )

    vector_db.persist()

    print("\n Phase 6 Completed Successfully!")
    print(" Chroma DB saved at:", chroma_save_path)


if __name__ == "__main__":

    file_hash = "962ae562ca933789fddeee27ca086458"

    chunks_json_path = f"data/cache/{file_hash}_chunks_final.json"
    chroma_db_path = f"data/chroma_db/{file_hash}"

    os.makedirs("data/chroma_db", exist_ok=True)

    build_chroma_index(chunks_json_path, chroma_db_path)
