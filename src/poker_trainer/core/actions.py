"""Reducer入力型。人間(将来のStreamlit UI)もCPU(cpu.policy.CPUDecisionMaker実装)も、
pokerkitのStateに直接触れずAction経由でengine.apply_actionを呼ぶ。"""

from dataclasses import dataclass
from enum import Enum


class ActionType(str, Enum):
    FOLD = "fold"
    CHECK_OR_CALL = "check_or_call"
    BET_OR_RAISE_TO = "bet_or_raise_to"


@dataclass(frozen=True)
class Action:
    """apply_actionへの唯一の入力型。

    amountはpokerkitのcomplete_bet_or_raise_toと同じ意味論(レイズ後の絶対額であり、
    上乗せ分の差額ではない)。BET_OR_RAISE_TO以外ではamountはNoneでなければならない。
    """

    type: ActionType
    amount: int | None = None

    def __post_init__(self) -> None:
        if self.type is ActionType.BET_OR_RAISE_TO and self.amount is None:
            raise ValueError("BET_OR_RAISE_TO requires an amount")
        if self.type is not ActionType.BET_OR_RAISE_TO and self.amount is not None:
            raise ValueError(f"{self.type} must not carry an amount")

    @staticmethod
    def fold() -> "Action":
        return Action(ActionType.FOLD)

    @staticmethod
    def check_or_call() -> "Action":
        return Action(ActionType.CHECK_OR_CALL)

    @staticmethod
    def bet_or_raise_to(amount: int) -> "Action":
        return Action(ActionType.BET_OR_RAISE_TO, amount)
