import os
import shutil
import uuid
import hashlib

UPLOAD_DIR= "data/uploads"
CACHE_DIR= "data/cache"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)   

def get_file_hash(file_path):
    with open(file_path, "rb") as f:
        file_data = f.read()
        return hashlib.md5(file_data).hexdigest()
    
def save_pdf_locally(file_path):
    file_hash = get_file_hash(file_path)
    cached_path= os.path.join(CACHE_DIR, f"{file_hash}.pdf") # Use .pdf extension for cached files
    
    if os.path.exists(cached_path):
        print(f"File already cached: {cached_path}")
        return file_hash, cached_path, False  # Return False indicating file was not newly saved
    
    file_id= str(uuid.uuid4())
    dest_path= os.path.join(UPLOAD_DIR, f"{file_id}.pdf") # Use .pdf extension for uploaded files
    shutil.copy(file_path, dest_path)
    
    print("📄 PDF saved locally")
    return file_hash, dest_path, True  # Return True indicating file was newly saved