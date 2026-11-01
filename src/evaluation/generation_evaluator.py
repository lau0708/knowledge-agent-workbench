
import json
from typing import Any

from src.rag.llm import call_deepseek
PROMPT_VERSION = "v1"

def build_evaluation_prompt(
    question: str,
    context: list[dict],
    answer: str,
) -> str:
    """构造生成质量评估 Prompt。"""

    context_text = "\n\n".join(
        [
            f"参考资料{i}：\n{item['content']}"
            for i, item in enumerate(context, start=1)
        ]
    )

    prompt = f"""
你是一个严格的 RAG 问答质量评估员。

请根据用户问题、参考资料和模型答案，评估模型答案的质量。

用户问题：
{question}

参考资料：
{context_text}

模型答案：
{answer}

请从以下三个相互独立的维度进行评分：

1. faithfulness（忠实度）：
判断答案中的事实性陈述是否有参考资料支持。
如果答案虽然偏离用户问题，但内容确实有参考资料支持，
不能仅仅因为跑题就降低忠实度。
如果答案包含无依据或与参考资料矛盾的事实，应降低分数。

2. relevance（相关性）：
判断答案是否直接回应用户的问题。
如果答案讨论的是其他主题，即使内容正确，也应降低分数。

3. completeness（完整性）：
判断答案是否覆盖了回答用户问题所必需的核心信息。

注意：
- 完整性应以用户问题为判断依据，而不是要求答案包含参考资料中的所有信息。
- 不要因为答案没有提及参考资料中的补充知识、扩展用途或次要细节，就直接判定完整性不足。
- 如果答案已经准确回答问题的核心内容，只是没有展开补充信息，完整性仍然可以较高。
- 如果答案遗漏了回答问题必不可少的核心信息，才应明显降低完整性。
- 如果答案完全没有回答用户问题，完整性应为低分。

请注意：
- 三个维度必须独立判断，不能因为某一个维度低就自动降低其他维度。
- 忠实度关注参考资料，相关性关注用户问题，完整性关注答案覆盖程度。
- 不要为了让三个分数一致而给出相同分数。

每个维度的分数范围是 0 到 1。
请只返回 JSON，不要输出其他内容。格式如下：

{{
    "faithfulness": 0.0,
    "relevance": 0.0,
    "completeness": 0.0,
    "reason": "简要说明评分理由"
}}
"""
    return prompt


def parse_evaluation_result(raw_result: str) -> dict[str, Any]:
    """解析并校验模型返回的评估结果。"""

    try:
        result = json.loads(raw_result)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"评估结果不是合法 JSON：{raw_result}"
        ) from e

    if not isinstance(result, dict):
        raise ValueError("评估结果必须是 JSON 对象")

    score_fields = [
        "faithfulness",
        "relevance",
        "completeness",
    ]

    for field in score_fields:
        if field not in result:
            raise ValueError(f"评估结果缺少字段：{field}")

        score = result[field]

        # bool 是 int 的子类，需要单独排除
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError(f"{field} 必须是数字")

        if not 0 <= score <= 1:
            raise ValueError(f"{field} 必须在 0 到 1 之间")

        result[field] = float(score)

    if "reason" not in result or not isinstance(result["reason"], str):
        raise ValueError("评估结果缺少有效的 reason 字段")

    return result


def evaluate_generation(
    question: str,
    context: list[dict],
    answer: str,
) -> dict[str, Any]:
    """调用 DeepSeek 评估生成答案的质量。"""

    prompt = build_evaluation_prompt(
        question=question,
        context=context,
        answer=answer,
    )

    raw_result = call_deepseek(prompt)

    return parse_evaluation_result(raw_result)
