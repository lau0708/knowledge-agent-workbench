
def rrf_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    top_k: int = 3,
    k: int = 60,
) -> list[dict]:

    # 保存每个 Chunk 的融合分数
    fused_scores = {}

    # 保存 Chunk 原始数据
    chunk_map = {}

    # 两路检索结果分别参与排名融合
    result_lists = [vector_results, bm25_results]

    for results in result_lists:
        for rank, chunk in enumerate(results, start=1):

            chunk_id = chunk["chunk_id"]

            # RRF 只使用排名，不使用原始检索分数
            score = 1 / (k + rank)

            fused_scores[chunk_id] = (
                fused_scores.get(chunk_id, 0) + score
            )

            chunk_map[chunk_id] = chunk

    # 按融合分数降序排列
    ranked_ids = sorted(
        fused_scores,
        key=lambda chunk_id: fused_scores[chunk_id],
        reverse=True,
    )

    fused_results = []

    for chunk_id in ranked_ids[:top_k]:
        result = chunk_map[chunk_id].copy()
        result["rrf_score"] = fused_scores[chunk_id]
        fused_results.append(result)

    return fused_results
