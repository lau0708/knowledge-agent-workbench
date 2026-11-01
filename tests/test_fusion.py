
from src.rag.fusion import rrf_fusion
vector_results = [
    {"chunk_id": "A", "content": "内容 A", "score": 0.89},
    {"chunk_id": "B", "content": "内容 B", "score": 0.82},
    {"chunk_id": "C", "content": "内容 C", "score": 0.76},
]

bm25_results = [
    {"chunk_id": "B", "content": "内容 B", "bm25_score": 0.32},
    {"chunk_id": "A", "content": "内容 A", "bm25_score": 0.15},
    {"chunk_id": "D", "content": "内容 D", "bm25_score": 0.08},
]

results = rrf_fusion(
    vector_results=vector_results,
    bm25_results=bm25_results,
    top_k=4,
)

for rank, result in enumerate(results, start=1):
    print(
        f"排名：{rank}，"
        f"Chunk：{result['chunk_id']}，"
        f"RRF 分数：{result['rrf_score']:.6f}"
    )
