

def split_text(
    text: str,
    chunk_size: int = 200,
    chunk_overlap: int = 30,
) -> list[str]:
    """优先按段落和句子边界切分文本，并保留相邻片段的重叠内容。"""

    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap 不能小于 0")

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须小于 chunk_size")

    text = text.strip()
    if not text:
        return []

    # 按长度限制切分，优先寻找自然的文本边界。
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            # 在当前长度范围内，优先选择更自然的切分点。
            search_start = start + max(1, chunk_size // 2)
            boundaries = [
                text.rfind("\n\n", search_start, end),
                text.rfind("\n", search_start, end),
                text.rfind("。", search_start, end),
                text.rfind("！", search_start, end),
                text.rfind("？", search_start, end),
                text.rfind(".", search_start, end),
                text.rfind("!", search_start, end),
                text.rfind("?", search_start, end),
                text.rfind(" ", search_start, end),
            ]

            boundary = max(boundaries)

            if boundary >= search_start:
                # 标点和换行符保留在当前 Chunk 中。
                end = boundary + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        # 从上一个 Chunk 的末尾向前回退，保留重叠内容。
        next_start = max(start + 1, end - chunk_overlap)

        # 避免下一个 Chunk 以空白字符开头。
        while next_start < end and text[next_start].isspace():
            next_start += 1

        start = next_start

    return chunks


if __name__ == "__main__":
    sample_text = (
        "RAG 可以先检索相关文档，再将检索结果交给大模型生成答案。"
        "Embedding 可以把文本转换成向量，用于语义检索。"
    )

    chunks = split_text(
        sample_text,
        chunk_size=20,
        chunk_overlap=5,
    )

    for index, chunk in enumerate(chunks, start=1):
        print(f"\nChunk {index}：")
        print(chunk)

    print(f"\n共切分为 {len(chunks)} 个 Chunk")
