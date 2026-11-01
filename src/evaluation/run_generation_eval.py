
import json
from pathlib import Path

from src.evaluation.generation_evaluator import evaluate_generation, PROMPT_VERSION
from src.evaluation.eval_report import save_evaluation_report
from src.rag.llm import MODEL_NAME

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EVAL_PATH = (
    PROJECT_ROOT
    / "data"
    / "eval"
    / "generation_eval.json"
)

# 暂定评分判断阈值
SCORE_THRESHOLDS = {
    "faithfulness": 0.7,
    "relevance": 0.7,
    "completeness": 0.5,
}


def load_eval_data():
    """加载生成质量测试集。"""
    with open(EVAL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def detect_issues(scores: dict) -> list[str]:
    """根据各维度独立阈值识别质量问题。"""

    issues = []

    for dimension, threshold in SCORE_THRESHOLDS.items():
        if scores[dimension] < threshold:
            issues.append(dimension)

    return issues

def run_evaluation():
    """批量执行生成质量评估。"""

    test_cases = load_eval_data()

    total = len(test_cases)
    passed = 0
    case_results = []
    dimensions = [
        "faithfulness",
        "relevance",
        "completeness",
    ]

    stats = {
        dimension: {
            "tp": 0,
            "fp": 0,
            "tn": 0,
            "fn": 0,
        }
        for dimension in dimensions
    }
    print("========== 生成质量评估测试 ==========")

    for case in test_cases:
        case_id = case["id"]

        print(f"\n测试用例：{case_id}")
        print(f"测试类型：{case['type']}")

        try:
            result = evaluate_generation(
                question=case["question"],
                context=case["context"],
                answer=case["answer"],
            )
            print(f"案例：{case_id}")
            print(f"评分结果：{result}")
            predicted_issues = detect_issues(result)

            expected_issue = case["expected_issue"]

            if isinstance(expected_issue, list):
                expected_issues = expected_issue
            elif expected_issue:
                expected_issues = [expected_issue]
            else:
                expected_issues = []

            is_passed = set(predicted_issues) == set(expected_issues)

            case_results.append({
                "case_id": case_id,
                "type": case["type"],
                "scores": {
                    "faithfulness": result["faithfulness"],
                    "relevance": result["relevance"],
                    "completeness": result["completeness"],
                },
                "reason": result["reason"],
                "expected_issues": expected_issues,
                "predicted_issues": predicted_issues,
                "passed": is_passed,
            })
            if is_passed:
                passed += 1
            for dimension in dimensions:
                expected_has_issue = dimension in expected_issues
                predicted_has_issue = dimension in predicted_issues

                if expected_has_issue and predicted_has_issue:
                    stats[dimension]["tp"] += 1

                elif not expected_has_issue and predicted_has_issue:
                    stats[dimension]["fp"] += 1

                elif not expected_has_issue and not predicted_has_issue:
                    stats[dimension]["tn"] += 1

                else:
                    stats[dimension]["fn"] += 1
            print(f"忠实度：{result['faithfulness']:.2f}")
            print(f"相关性：{result['relevance']:.2f}")
            print(f"完整性：{result['completeness']:.2f}")
            print(f"评估理由：{result['reason']}")
            print(f"预期问题：{expected_issues}")
            print(f"实际识别：{predicted_issues}")
            print(f"测试结果：{'通过' if is_passed else '未通过'}")

        except Exception as e:
            print(f"评估失败：{e}")

    print("\n========== 测试汇总 ==========")
    print(f"测试总数：{total}")
    print(f"通过数量：{passed}")
    print(f"失败数量：{total - passed}")

    accuracy = passed / total if total else 0
    print(f"评估识别准确率：{accuracy:.2%}")

    dimension_metrics = {}
    print("\n========== 分维度评估统计 ==========")

    for dimension in dimensions:
        item = stats[dimension]

        tp = item["tp"]
        fp = item["fp"]
        tn = item["tn"]
        fn = item["fn"]

        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0

        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0
        )

        accuracy = (
            (tp + tn) / (tp + tn + fp + fn)
            if tp + tn + fp + fn
            else 0
        )
        dimension_metrics[dimension] = {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "accuracy": accuracy,
        }

        print(f"\n维度：{dimension}")
        print(f"TP={tp}, FP={fp}, TN={tn}, FN={fn}")
        print(f"Precision：{precision:.2%}")
        print(f"Recall：{recall:.2%}")
        print(f"F1：{f1:.2%}")
        print(f"Accuracy：{accuracy:.2%}")

        report = {
        "evaluation_info": {
            "model": MODEL_NAME,
            "prompt_version": PROMPT_VERSION,
            "threshold_version": "v1",
            "thresholds": SCORE_THRESHOLDS,
        },
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "accuracy": passed / total if total else 0,
        },
        "dimension_metrics": dimension_metrics,
        "cases": case_results,
    }

    report_path = save_evaluation_report(report)

    print("\n========== 评估报告保存 ==========")
    print(f"报告路径：{report_path}")

if __name__ == "__main__":
    run_evaluation()
