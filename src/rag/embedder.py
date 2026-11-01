
from sentence_transformers import SentenceTransformer

from src.config import settings

MODEL_NAME = settings.embedding_model_name


def load_embedding_model() -> SentenceTransformer:
    """从本地缓存加载中文 Embedding 模型。"""
    model = SentenceTransformer(
        MODEL_NAME,
        local_files_only=settings.embedding_local_files_only,
        device="cpu",
    )
    return model

def encode_texts(model: SentenceTransformer, texts: list[str]):
    """将多个文本分块编码为向量。"""
    if not texts:
        return []

    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    return vectors



if __name__ == "__main__":
    model = load_embedding_model()

    texts = [
        "RAG 通过检索知识库中的相关内容来增强大模型回答。",
        "Embedding 可以将文本转换成数值向量。",
        "Python 是一种常用的编程语言。",
    ]

    vectors = encode_texts(model, texts)

    print("文本数量：", len(texts))
    print("向量矩阵形状：", vectors.shape)
    print("第一个向量的前 5 个值：", vectors[0][:5])
