from typing import Any, NotRequired, TypedDict

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


class AddPhonesMultiPayload(TypedDict):
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


# --- N-GATE v2.0 DB sync / history / rule config ---


class DbDeltaPayload(TypedDict):
    ops: list[dict[str, Any]]


class HistoryAckPayload(TypedDict):
    req_id: int
    acked: int


class RuleActionPayload(TypedDict):
    relay: int
    state: bool
    time: NotRequired[int]
    delay_ms: NotRequired[int]
    base_state: NotRequired[bool]


class RuleConditionPayload(TypedDict):
    input: int
    state: bool


class RulePayload(TypedDict):
    trigger: str
    trigger_dir: NotRequired[int]
    gate_id: NotRequired[int]
    conditions: NotRequired[list[RuleConditionPayload]]
    actions: list[RuleActionPayload]


class HwPortPayload(TypedDict):
    role: str
    id: int
    base_state: NotRequired[bool]
    dir: NotRequired[int]
    gate_id: NotRequired[int]


class RuleConfigPayload(TypedDict):
    hardware: NotRequired[list[HwPortPayload]]
    rules: NotRequired[list[RulePayload]]
    schedules: NotRequired[list[dict[str, Any]]]


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
    "DbDeltaPayload",
    "HistoryAckPayload",
    "RuleActionPayload",
    "RuleConditionPayload",
    "RulePayload",
    "HwPortPayload",
    "RuleConfigPayload",
]
