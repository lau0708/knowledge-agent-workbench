
import json
import re
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    """
    对文本进行分词。
    中文使用 jieba，英文、数字和编号保留完整。
    """
    tokens = []

    # 提取英文、数字、订单编号等连续标识符
    parts = re.findall(
        r"[a-zA-Z0-9_-]+|[\u4e00-\u9fff]+",
        text.lower()
    )

    for part in parts:
        if re.fullmatch(r"[a-zA-Z0-9_-]+", part):
            tokens.append(part)
        else:
            tokens.extend(
                word.strip()
                for word in jieba.cut(part)
                if word.strip()
            )

    return tokens


class BM25Retriever:

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks

        # 对所有 Chunk 的内容进行分词
        self.tokenized_corpus = [
            tokenize(chunk["content"])
            for chunk in chunks
        ]

        # 构建 BM25 索引
        self.bm25 = (
            BM25Okapi(self.tokenized_corpus)
            if self.tokenized_corpus
            else None
        )

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        if not query.strip() or not self.chunks or top_k <= 0:
            return []

        query_tokens = tokenize(query)

        if not query_tokens or self.bm25 is None:
            return []

        scores = [float(score) for score in self.bm25.get_scores(query_tokens)]

        if not any(score > 0 for score in scores):
            scores = [
                float(
                    sum(
                        1
                        for token in query_tokens
                        if token in tokenized_chunk
                    )
                )
                for tokenized_chunk in self.tokenized_corpus
            ]

        # 按 BM25 分数从高到低排序
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda index: scores[index],
            reverse=True
        )

        results = []

        for index in ranked_indices:
            score = scores[index]

            # 不返回没有关键词匹配的 Chunk
            if score <= 0:
                continue

            result = self.chunks[index].copy()
            result["bm25_score"] = score
            results.append(result)

            if len(results) >= top_k:
                break

        return results


def load_chunks(index_path: Path) -> list[dict]:
    with index_path.open("r", encoding="utf-8") as file:
        return json.load(file)
