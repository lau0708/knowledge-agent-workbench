class AppError(Exception):
    """业务异常基类，FastAPI 统一异常处理器会识别该类。"""

    status_code = 500
    code = "INTERNAL_ERROR"
    default_message = "服务内部错误"

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    default_message = "资源不存在"


class BadRequestError(AppError):
    status_code = 400
    code = "BAD_REQUEST"
    default_message = "请求参数错误"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    default_message = "资源冲突"
