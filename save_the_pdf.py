import os
import shutil
import hashlib

UPLOAD_DIR = "data/uploads"
CACHE_DIR = "data/cache"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

def get_file_hash(file_path):
    with open(file_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def save_pdf_locally(source_pdf_path):
    file_hash = get_file_hash(source_pdf_path)

    upload_path = os.path.join(UPLOAD_DIR, f"{file_hash}.pdf")
    cache_path = os.path.join(CACHE_DIR, f"{file_hash}.json")

    if os.path.exists(upload_path):
        print("✅ PDF already exists in uploads", upload_path)
    else:
        shutil.copy(source_pdf_path, upload_path)
        print("📄 PDF saved to uploads", upload_path)

    return file_hash, upload_path, cache_path


if __name__ == "__main__":
    source_pdf = "sample.pdf"
    file_hash, upload_path, cache_path = save_pdf_locally(source_pdf)
    print(f"File Hash: {file_hash}")
    print(f"Upload Path: {upload_path}")
    print(f"Cache Path: {cache_path}")
