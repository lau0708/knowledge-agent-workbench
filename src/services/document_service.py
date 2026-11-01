from pathlib import Path

from src.config import settings
from src.database import db
from src.errors import AppError
from src.services.indexing_service import (
    StorageSyncError,
    delete_document_sync,
    sync_file,
)

DOCUMENTS_DIR = settings.documents_dir


class DocumentServiceError(AppError):
    """文档管理服务通用错误。"""

    status_code = 500
    code = "DOCUMENT_SERVICE_ERROR"
    default_message = "文档服务处理失败"


class DocumentNotFoundError(DocumentServiceError):
    """文档不存在。"""

    status_code = 404
    code = "DOCUMENT_NOT_FOUND"
    default_message = "文档不存在"


class UnsupportedDocumentTypeError(DocumentServiceError):
    """不支持的文件类型。"""

    status_code = 400
    code = "UNSUPPORTED_DOCUMENT_TYPE"
    default_message = "不支持的文件类型"


class DuplicateDocumentError(DocumentServiceError):
    """同名文档已存在。"""

    status_code = 409
    code = "DUPLICATE_DOCUMENT"
    default_message = "同名文档已存在"


def _ensure_documents_dir() -> None:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name

    if not name or name in {".", ".."}:
        raise UnsupportedDocumentTypeError("文件名无效")

    return name


def _is_markdown(filename: str) -> bool:
    return Path(filename).suffix.lower() == ".md"


def _is_inside_documents_dir(path: Path) -> bool:
    try:
        return path.resolve().is_relative_to(DOCUMENTS_DIR.resolve())
    except Exception:
        return False


def _raise_service_error(exc: Exception, action: str) -> None:
    if isinstance(exc, StorageSyncError):
        raise exc

    raise DocumentServiceError(f"{action}失败：{exc}") from exc


def create_document(collection, filename: str, content: bytes) -> dict:
    """上传 Markdown 文件并建立索引。"""

    safe_name = _safe_filename(filename)

    if not _is_markdown(safe_name):
        raise UnsupportedDocumentTypeError("目前只支持 Markdown 文件")

    _ensure_documents_dir()

    source_path = DOCUMENTS_DIR / safe_name
    source = str(source_path)

    if source_path.exists() or db.get_document_id_by_source(source) is not None:
        raise DuplicateDocumentError("同名文档已存在")

    source_path.write_bytes(content)

    try:
        sync_file(collection, source)
    except Exception as exc:
        source_path.unlink(missing_ok=True)
        _raise_service_error(exc, "文档索引")

    document_id = db.get_document_id_by_source(source)

    if document_id is None:
        raise DocumentServiceError("文档索引完成，但读取文档记录失败")

    return db.get_document_by_id(document_id)


def list_documents() -> list[dict]:
    """返回已入库文档列表。"""

    return db.get_all_documents()


def get_document(document_id: int) -> dict:
    """返回文档详情及 Chunk 信息。"""

    document = db.get_document_by_id(document_id)

    if document is None:
        raise DocumentNotFoundError("文档不存在")

    return document


def update_document(collection, document_id: int, content: str) -> dict:
    """更新文档内容并重新建立索引，失败时恢复原文件内容。"""

    document = db.get_document_by_id(document_id)

    if document is None:
        raise DocumentNotFoundError("文档不存在")

    source = document["source"]
    source_path = Path(source)

    if not _is_inside_documents_dir(source_path):
        raise DocumentServiceError("文档路径不在管理目录内")

    original_content = None

    if source_path.exists():
        original_content = source_path.read_text(encoding="utf-8")

    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(content, encoding="utf-8")

    try:
        sync_file(collection, source)
    except Exception as exc:
        if original_content is None:
            source_path.unlink(missing_ok=True)
        else:
            source_path.write_text(original_content, encoding="utf-8")

        _raise_service_error(exc, "文档更新")

    return db.get_document_by_id(document_id)


def delete_document(collection, document_id: int) -> dict:
    """同步删除文件、SQLite 和 ChromaDB 数据，失败时恢复原文件。"""

    document = db.get_document_by_id(document_id)

    if document is None:
        raise DocumentNotFoundError("文档不存在")

    source = document["source"]
    source_path = Path(source)

    original_content = None

    if source_path.exists():
        if not _is_inside_documents_dir(source_path):
            raise DocumentServiceError("文档路径不在管理目录内")

        original_content = source_path.read_bytes()

    if source_path.exists():
        source_path.unlink()

    try:
        delete_document_sync(collection, source)
    except Exception as exc:
        if original_content is not None:
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(original_content)

        _raise_service_error(exc, "文档删除")

    return {
        "deleted": True,
        "id": document_id,
        "source": source,
    }
