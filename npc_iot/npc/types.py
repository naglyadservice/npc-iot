from typing import NotRequired, TypedDict

from ..base.types import AckResponse, BaseResponse


class RebootPayload(TypedDict):
    delay: int


class SetStateRelay(TypedDict):
    id: int
    state: bool
    duration: NotRequired[int]


class SetStateOutput(TypedDict):
    id: int
    state: bool
    duration: NotRequired[int]
    period: NotRequired[int]


class SetStatePayload(TypedDict):
    relay: NotRequired[list[SetStateRelay]]
    output: NotRequired[list[SetStateOutput]]


class GetStatePayload(TypedDict):
    relay: NotRequired[list[int]]
    output: NotRequired[list[int]]
    input: NotRequired[list[int]]
    temperature: NotRequired[list[int]]
    humidity: NotRequired[list[int]]


class AddPhonesMultyPayload(TypedDict):
    phones: list[str]


class DelPhonesPayload(TypedDict):
    phones: list[str]


class PinStateInfo(TypedDict):
    id: int
    state: bool


class SensorStateInfo(TypedDict):
    id: int
    value: float


class GetStateResponse(BaseResponse):
    relay: list[PinStateInfo]
    output: list[PinStateInfo]
    input: list[PinStateInfo]
    temperature: NotRequired[list[SensorStateInfo]]
    humidity: NotRequired[list[SensorStateInfo]]


__all__ = [
    "AckResponse",
    "BaseResponse",
    "RebootPayload",
    "SetStateRelay",
    "SetStateOutput",
    "SetStatePayload",
    "GetStatePayload",
    "GetStateResponse",
    "PinStateInfo",
    "SensorStateInfo",
]
