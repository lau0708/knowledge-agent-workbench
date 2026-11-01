

import logging

from src.config import settings
from src.rag.embedder import load_embedding_model
from src.rag.retriever import search
from src.rag.llm import call_deepseek
from src.evaluation.generation_evaluator import evaluate_generation
from src.rag.vector_store import get_collection

logger = logging.getLogger(__name__)

MIN_SIMILARITY = settings.min_similarity


def build_prompt(question: str, results: list[dict]) -> str:
    """将检索结果和用户问题组合成 Prompt。"""

    context_parts = []

    for i, item in enumerate(results, start=1):
        context_parts.append(
            f"参考资料{i}：\n{item['content']}"
        )

    context = "\n\n".join(context_parts)

    prompt = f"""
你是一个专业的知识库问答助手。

请严格根据下面提供的参考资料回答用户问题。

要求：
1. 优先依据参考资料回答，不要编造资料中没有的信息。
2. 如果参考资料不足以回答问题，请明确说明不知道。
3. 回答尽量清晰、简洁。

参考资料：
{context}

用户问题：
{question}

请给出回答：
"""
    return prompt


def ask(
    question: str,
    model,
    collection,
    top_k: int | None = None,
) -> dict:

    top_k = settings.top_k if top_k is None else top_k

    results = search(
        query=question,
        model=model,
        collection=collection,
        top_k=top_k,
    )
    logger.info("检索到 %s 条结果", len(results))

    for i, item in enumerate(results, start=1):
        logger.debug("检索结果 %s：source=%s score=%.4f", i, item["source"], item["score"])

    if not results or results[0]["score"] < MIN_SIMILARITY:
        return {
            "question": question,
            "context": [],
            "answer": "知识库中没有找到足够相关的资料，暂时无法回答。",
            "evaluation": None,
        }

    # 4. 构造 Prompt
    prompt = build_prompt(question, results)

    # 5. 调用 DeepSeek 生成答案
    answer = call_deepseek(prompt)

    # 6. 整理评估所需的参考资料
    context = [
        {
            "source": item["source"],
            "content": item["content"],
            "score": item["score"],
        }
        for item in results
    ]

    # 7. 评估生成答案的质量
    evaluation = evaluate_generation(
        question=question,
        context=context,
        answer=answer,
    )

    # 8. 返回答案和评估结果
    return {
        "question": question,
        "context": context,
        "answer": answer,
        "evaluation": evaluation,
    }
