
from pathlib import Path


def load_markdown(file_path: str) -> str:
    """读取一个 Markdown 文件并返回文本内容。"""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{path}")

    if path.suffix.lower() != ".md":
        raise ValueError("目前只支持 Markdown 文件")

    return path.read_text(encoding="utf-8")


def load_all_markdown(directory: str) -> list[dict[str, str]]:
    """递归读取目录中的所有 Markdown 文件。"""
    root = Path(directory)

    if not root.exists():
        raise FileNotFoundError(f"目录不存在：{root}")

    documents = []

    for path in sorted(root.rglob("*.md")):
        content = load_markdown(str(path))

        documents.append({
            "source": str(path),
            "content": content,
        })

    return documents



if __name__ == "__main__":
    documents = load_all_markdown("data/documents")

    print(f"共读取 {len(documents)} 篇文档")

    for document in documents:
        print("-" * 30)
        print(f"来源：{document['source']}")
        print(f"内容长度：{len(document['content'])} 个字符")

