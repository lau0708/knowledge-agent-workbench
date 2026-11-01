from src.evaluation.generation_evaluator import evaluate_generation
from src.evaluation.generation_evaluator import parse_evaluation_result


question = "什么是 Embedding？"

context = [
    {
        "source": "embedding.md",
        "content": "Embedding 是将文本、图片等数据转换为向量表示的技术。",
        "score": 0.85,
    }
]

answer = "Embedding 是将文本、图片等数据转换为向量表示的技术。"


result = evaluate_generation(
    question=question,
    context=context,
    answer=answer,
)

print("========== 生成质量评估 ==========")
print(f"忠实度：{result['faithfulness']}")
print(f"相关性：{result['relevance']}")
print(f"完整性：{result['completeness']}")
print(f"评估理由：{result['reason']}")



print("\n========== 异常数据测试 ==========")

test_cases = [
    '{"faithfulness": 0.9, "relevance": 0.8, "completeness": 0.7, "reason": "正常"}',
    '{"faithfulness": 1.5, "relevance": 0.8, "completeness": 0.7, "reason": "超出范围"}',
    '{"faithfulness": true, "relevance": 0.8, "completeness": 0.7, "reason": "布尔值"}',
    '这不是 JSON',
]

for test_data in test_cases:
    try:
        result = parse_evaluation_result(test_data)
        print("校验通过：", result)
    except ValueError as e:
        print("校验失败：", e)