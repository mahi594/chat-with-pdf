from save_the_pdf import save_pdf_locally
from parse_pdf import parse_pdf_to_text
import os

if __name__ == "__main__":
    source_pdf = "sample.pdf"  
    
    if not os.path.exists(source_pdf):
        raise FileNotFoundError(f" PDF not found: {source_pdf}")
    
    file_hash, upload_path, cache_path = save_pdf_locally(source_pdf)
    
    if os.path.exists(cache_path):
        print(f"✅ Parsed data already exists in cache: {cache_path}")
    else:
        parsed_data = parse_pdf_to_text(upload_path, cache_path)
        
    print("\n File ID (hash):", file_hash)
    print(" Upload Path:", upload_path)
    print(" Cache Path:", cache_path)