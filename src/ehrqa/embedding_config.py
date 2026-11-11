"""
Module quản lý cấu hình Embedding cho Vector Database (ChromaDB).
Centralized Embedding Configuration for MIMIC-IV RAG Engine.

Mục đích:
- Thay thế mô hình nhúng mặc định của ChromaDB (`all-MiniLM-L6-v2` - chỉ tiếng Anh)
- Hỗ trợ các mô hình đa ngữ (Multilingual) phù hợp với tiếng Việt y tế:
  1. `paraphrase-multilingual-MiniLM-L12-v2` (118M params, ~470MB, siêu nhẹ, chạy tốt trên RTX 3050 Laptop 4GB VRAM)
  2. `intfloat/multilingual-e5-small` (118M params)
  3. `BAAI/bge-m3` (568M params, model mạnh nhất, cần >=8GB VRAM hoặc Google Colab T4)
"""

import os
from chromadb.utils import embedding_functions

# Mô hình mặc định được tối ưu cho Laptop RTX 3050 (4GB VRAM / 16GB RAM)
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")

_CACHED_EF = {}

def get_embedding_function(model_name: str = None):
    """
    Trả về SentenceTransformerEmbeddingFunction cho ChromaDB.
    Sử dụng cache trong bộ nhớ để tránh load lại model nhiều lần.
    """
    if model_name is None:
        model_name = DEFAULT_EMBEDDING_MODEL

    if model_name not in _CACHED_EF:
        print(f" [Embedding] Loading model '{model_name}' ...")
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name
        )
        _CACHED_EF[model_name] = ef
    return _CACHED_EF[model_name]
