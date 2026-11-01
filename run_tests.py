import argparse
import subprocess
import sys


UNIT_COMMAND = [
    sys.executable,
    "-m",
    "unittest",
    "discover",
    "-s",
    "tests/unit",
    "-v",
]

INTEGRATION_COMMAND = [sys.executable, "-m", "tests.test_indexing_service"]

REGRESSION_COMMANDS = [UNIT_COMMAND, INTEGRATION_COMMAND]

COMMANDS = {
    "unit": [UNIT_COMMAND],
    "integration": [INTEGRATION_COMMAND],
    "regression": REGRESSION_COMMANDS,
    "all": REGRESSION_COMMANDS,
}


def run_commands(commands: list[list[str]]) -> int:
    for command in commands:
        print("\n$", " ".join(command))
        result = subprocess.run(command)

        if result.returncode != 0:
            return result.returncode

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="运行本地知识库自动化测试矩阵",
    )
    parser.add_argument(
        "--category",
        choices=sorted(COMMANDS),
        default="all",
        help="测试类别：unit、integration、regression 或 all（默认）",
    )
    args = parser.parse_args()

    return run_commands(COMMANDS[args.category])


if __name__ == "__main__":
    raise SystemExit(main())
