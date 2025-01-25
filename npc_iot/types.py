from typing import NotRequired, TypedDict


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


class PinStateInfo(TypedDict):
    id: int
    state: bool


class SensorStateInfo(TypedDict):
    id: int
    value: float


class BaseResponse(TypedDict):
    request_id: str
    code: NotRequired[int]


class GetStateResponse(BaseResponse):
    relay: list[PinStateInfo]
    output: list[PinStateInfo]
    input: list[PinStateInfo]
    temperature: NotRequired[list[SensorStateInfo]]
    humidity: NotRequired[list[SensorStateInfo]]
