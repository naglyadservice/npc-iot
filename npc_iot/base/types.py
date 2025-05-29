from typing import NotRequired, TypedDict


class BaseResponse(TypedDict):
    request_id: str
    code: NotRequired[int]


class AckResponse(BaseResponse):
    pass


__all__ = ["AckResponse", "BaseResponse"]
