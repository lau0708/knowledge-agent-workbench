
import json
from pathlib import Path

from src.rag.embedder import load_embedding_model
from src.rag.retriever import search


PROJECT_ROOT = Path(__file__).resolve().parent.parent

INDEX_PATH = PROJECT_ROOT / "data" / "index" / "index.json"
EVAL_PATH = PROJECT_ROOT / "data" / "eval" / "rag_eval.json"

TOP_K = 3

THRESHOLDS = [0.40, 0.45, 0.50, 0.60]


def load_json(path: Path):
    """加载 JSON 文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate():
    """评估 RAG 的检索效果和拒答判断。"""

    # 1. 加载索引、测试集和 Embedding 模型
    index = load_json(INDEX_PATH)
    test_cases = load_json(EVAL_PATH)
    model = load_embedding_model()

    total = len(test_cases)

    # 文档命中率统计
    hit_count = 0
    answerable_count = 0

    # 不同阈值下的混淆矩阵统计
    threshold_results = {
        threshold: {
            "tp": 0,
            "tn": 0,
            "fp": 0,
            "fn": 0,
        }
        for threshold in THRESHOLDS
    }

    print("========== RAG 检索评估 ==========")

    # 2. 遍历测试问题
    for i, case in enumerate(test_cases, start=1):
        question = case["question"]
        expected_sources = case["expected_sources"]
        should_answer = case["should_answer"]

        # 3. 检索知识
        results = search(
            query=question,
            index=index,
            model=model,
            top_k=TOP_K,
        )

        # 4. 获取实际检索到的文档名称
        actual_sources = {
            Path(item["source"]).name
            for item in results
        }

        # 5. 判断是否命中预期文档
        hit = bool(
            actual_sources.intersection(expected_sources)
        )

        # 只统计有预期文档的问题
        if expected_sources:
            answerable_count += 1

            if hit:
                hit_count += 1

        # 6. 根据不同相似度阈值判断是否允许回答
        for threshold in THRESHOLDS:
            predicted_answer = (
                bool(results)
                and results[0]["score"] >= threshold
            )

            stats = threshold_results[threshold]

            if should_answer and predicted_answer:
                stats["tp"] += 1

            elif not should_answer and not predicted_answer:
                stats["tn"] += 1

            elif not should_answer and predicted_answer:
                stats["fp"] += 1

            else:
                stats["fn"] += 1

        # 7. 输出当前问题的检索结果
        print(f"\n测试 {i}：{question}")
        print(f"预期文档：{expected_sources}")
        print(f"实际文档：{sorted(actual_sources)}")

        print(
            f"最高相似度：{results[0]['score']:.4f}"
            if results
            else "最高相似度：无结果"
        )

        print(f"文档命中：{'是' if hit else '否'}")
        print(f"预期回答：{'是' if should_answer else '否'}")

    # 8. 统计文档命中率
    hit_rate = (
        hit_count / answerable_count
        if answerable_count
        else 0
    )

    print("\n========== 文档命中率 ==========")
    print(f"可回答问题文档命中率：{hit_rate:.2%}")
    print(f"命中问题数：{hit_count}/{answerable_count}")

    # 9. 阈值对比实验
    print("\n========== 阈值对比实验 ==========")

    for threshold, stats in threshold_results.items():

        tp = stats["tp"]
        tn = stats["tn"]
        fp = stats["fp"]
        fn = stats["fn"]

        accuracy = (
            (tp + tn) / total
            if total
            else 0
        )

        print(f"\n相似度阈值：{threshold}")
        print(f"准确率：{accuracy:.2%}")
        print(f"TP（正确放行）：{tp}")
        print(f"TN（正确拒答）：{tn}")
        print(f"FP（错误放行）：{fp}")
        print(f"FN（误拒回答）：{fn}")


if __name__ == "__main__":
    evaluate()
