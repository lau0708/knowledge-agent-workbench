from collections import defaultdict
import logging
from pathlib import Path

from src.config import settings
from src.database.db import (
    delete_document_by_source,
    get_all_chunks_by_source as get_sqlite_chunks_by_source,
    get_all_document_sources as get_sqlite_sources,
    get_document_chunks as get_sqlite_snapshot,
    replace_document_chunks,
    restore_document_snapshot,
)
from src.rag.indexer import build_document_chunks, build_index
from src.rag.vector_store import (
    add_chunks,
    delete_chunks_by_source,
    get_all_sources as get_chroma_sources,
    get_chunks_by_source as get_chroma_chunks,
    restore_chunks,
)
from src.errors import AppError

logger = logging.getLogger(__name__)


class StorageSyncError(AppError):
    """双存储同步失败。"""

    status_code = 500
    code = "STORAGE_SYNC_ERROR"
    default_message = "双存储同步失败"


def sync_file(
    collection,
    source: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> int:
    """为单个 Markdown 文件构建索引并同步到 SQLite 与 ChromaDB。"""

    chunk_size = settings.chunk_size if chunk_size is None else chunk_size
    chunk_overlap = settings.chunk_overlap if chunk_overlap is None else chunk_overlap

    chunks = build_document_chunks(
        source,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    return sync_document_chunks(collection, source, chunks)


def sync_document_chunks(collection, source: str, chunks: list[dict]) -> int:
    """同步单个文档到 SQLite 和 ChromaDB，失败时执行跨存储补偿。"""

    if not source or not source.strip():
        raise ValueError("source 不能为空")

    if not isinstance(chunks, list):
        raise TypeError("chunks 必须是列表")

    chunk_ids = [chunk["chunk_id"] for chunk in chunks]

    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("chunk_id 不能重复")

    sqlite_snapshot = get_sqlite_snapshot(source)
    chroma_snapshot = get_chroma_chunks(collection, source)

    try:
        replace_document_chunks(source, chunks)
    except Exception as exc:
        raise StorageSyncError(f"SQLite 更新失败：{source}") from exc

    try:
        add_chunks(collection, chunks)

        old_ids = {record["id"] for record in chroma_snapshot}
        new_ids = set(chunk_ids)
        obsolete_ids = old_ids - new_ids

        if obsolete_ids:
            collection.delete(ids=sorted(obsolete_ids))

    except Exception as chroma_error:
        compensation_errors = []

        try:
            restore_document_snapshot(source, sqlite_snapshot)
        except Exception as rollback_error:
            compensation_errors.append(f"SQLite 回滚失败：{rollback_error}")

        try:
            delete_chunks_by_source(collection, source)
            restore_chunks(collection, chroma_snapshot)
        except Exception as chroma_rollback_error:
            compensation_errors.append(f"ChromaDB 补偿失败：{chroma_rollback_error}")

        message = f"ChromaDB 更新失败：{source}（{chroma_error}）"

        if compensation_errors:
            message += "；补偿未完全成功：" + "；".join(compensation_errors)

        raise StorageSyncError(message) from chroma_error

    return len(chunks)


def delete_document_sync(collection, source: str) -> bool:
    """同步删除 SQLite 与 ChromaDB 中同一个文档的数据。"""

    if not source or not source.strip():
        raise ValueError("source 不能为空")

    sqlite_snapshot = get_sqlite_snapshot(source)
    chroma_snapshot = get_chroma_chunks(collection, source)

    try:
        delete_document_by_source(source)
    except Exception as exc:
        raise StorageSyncError(f"SQLite 删除失败：{source}") from exc

    try:
        delete_chunks_by_source(collection, source)
    except Exception as chroma_error:
        compensation_errors = []

        try:
            restore_document_snapshot(source, sqlite_snapshot)
        except Exception as rollback_error:
            compensation_errors.append(f"SQLite 回滚失败：{rollback_error}")

        try:
            delete_chunks_by_source(collection, source)
            restore_chunks(collection, chroma_snapshot)
        except Exception as chroma_rollback_error:
            compensation_errors.append(f"ChromaDB 补偿失败：{chroma_rollback_error}")

        message = f"ChromaDB 删除失败：{source}（{chroma_error}）"

        if compensation_errors:
            message += "；补偿未完全成功：" + "；".join(compensation_errors)

        raise StorageSyncError(message) from chroma_error

    return True


def verify_consistency(collection) -> dict:
    """检查 SQLite 与 ChromaDB 的文档来源和 Chunk ID/内容是否一致。"""

    sqlite_sources = get_sqlite_sources()
    chroma_sources = get_chroma_sources(collection)
    sqlite_chunks_by_source = get_sqlite_chunks_by_source()

    only_sqlite = sqlite_sources - chroma_sources
    only_chroma = chroma_sources - sqlite_sources
    mismatched_sources = {}

    for source in sqlite_sources & chroma_sources:
        expected_chunks = sqlite_chunks_by_source.get(source, {})
        chroma_records = get_chroma_chunks(collection, source)
        actual_chunks = {record["id"]: record for record in chroma_records}

        missing_in_chroma = sorted(set(expected_chunks) - set(actual_chunks))
        extra_in_chroma = sorted(set(actual_chunks) - set(expected_chunks))
        content_mismatch = sorted(
            chunk_id
            for chunk_id, content in expected_chunks.items()
            if chunk_id in actual_chunks and actual_chunks[chunk_id]["document"] != content
        )

        if missing_in_chroma or extra_in_chroma or content_mismatch:
            mismatched_sources[source] = {
                "missing_in_chroma": missing_in_chroma,
                "extra_in_chroma": extra_in_chroma,
                "content_mismatch": content_mismatch,
            }

    return {
        "is_consistent": not only_sqlite and not only_chroma and not mismatched_sources,
        "only_sqlite": sorted(only_sqlite),
        "only_chroma": sorted(only_chroma),
        "mismatched_sources": mismatched_sources,
    }


def print_consistency_report(report: dict) -> None:
    """打印双存储一致性检查结果。"""

    print("===== 双存储一致性检查 =====")

    if report["is_consistent"]:
        print("结果：一致")
        return

    print("结果：不一致")

    for source in report["only_sqlite"]:
        print("仅 SQLite 存在：", source)

    for source in report["only_chroma"]:
        print("仅 ChromaDB 存在：", source)

    for source, detail in report["mismatched_sources"].items():
        print("Chunk 不一致：", source, detail)


def _is_managed_source(source: str, directory_path: Path) -> bool:
    """判断 source 是否位于本次同步管理目录下。"""

    try:
        return Path(source).resolve().is_relative_to(directory_path)
    except Exception:
        return False


def get_managed_sources(collection, directory: str) -> set[str]:
    """读取两边存储中属于指定管理目录的文档来源。"""

    directory_path = Path(directory).resolve()
    candidates = get_sqlite_sources() | get_chroma_sources(collection)

    return {
        source
        for source in candidates
        if _is_managed_source(source, directory_path)
    }


def prune_missing_documents(
    collection,
    directory: str,
    current_sources: set[str] | list[str],
) -> list[str]:
    """清理管理目录下已不存在于当前文件列表的文档。"""

    current_sources = set(current_sources or [])
    missing_sources = get_managed_sources(collection, directory) - current_sources
    removed_sources = []

    for source in sorted(missing_sources):
        delete_document_sync(collection, source)
        removed_sources.append(source)
        logger.info("已删除文档同步：%s", source)

    return removed_sources


def build_and_sync(
    directory: str,
    collection,
    prune_missing: bool = True,
) -> int:
    """构建索引，同步到 ChromaDB 和 SQLite，并清理已删除文档。"""

    chunks = build_index(
        directory,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    current_sources = {chunk["source"] for chunk in chunks}

    pruned_sources = []

    if prune_missing:
        pruned_sources = prune_missing_documents(
            collection=collection,
            directory=directory,
            current_sources=current_sources,
        )

    if not chunks:
        if pruned_sources:
            logger.info("本次仅清理 %s 个已删除文档", len(pruned_sources))
        else:
            logger.info("没有找到可索引的文档")

        return 0

    grouped_chunks = defaultdict(list)

    for chunk in chunks:
        grouped_chunks[chunk["source"]].append(chunk)

    total = 0

    for source, document_chunks in grouped_chunks.items():
        sync_document_chunks(
            collection=collection,
            source=source,
            chunks=document_chunks,
        )

        total += len(document_chunks)
        logger.info("同步完成：%s，共 %s 个 Chunk", source, len(document_chunks))

    return total
