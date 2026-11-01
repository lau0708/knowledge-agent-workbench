import json
from datetime import datetime
from pathlib import Path


REPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "eval" / "reports"


def save_evaluation_report(report: dict) -> Path:
    """
    保存一次评估报告，返回报告文件路径。
    """

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report_path = REPORT_DIR / f"generation_eval_{timestamp}.json"

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=4
        )

    return report_path