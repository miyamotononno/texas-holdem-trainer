"""ハンド進行中に蓄積される行動ログ。プレー分析機能(REQUIREMENTS.md 2.2)が
ポットオッズ・エクイティ判定をstateの再走査なしに行えるだけの情報を持つ。"""

from dataclasses import dataclass
from enum import IntEnum

from poker_trainer.core.actions import ActionType


class Street(IntEnum):
    PREFLOP = 0
    FLOP = 1
    TURN = 2
    RIVER = 3


@dataclass(frozen=True)
class ActionRecord:
    """engine.apply_actionが行動のたびに1件追記する不変のログエントリ。"""

    seat_index: int
    street: Street
    action_type: ActionType
    amount: int | None  # BET_OR_RAISE_TO: レイズ後の絶対額 / CHECK_OR_CALLでコールした場合: コール額
    # (チェックの場合はNone) / FOLD: 常にNone
    pot_before: int  # 行動前の合計ポット
    to_call_before: int  # 行動前にコールに必要な額(チェック可能なら0)
    stacks_before: tuple[int, ...]  # 行動前の全席のスタック
    stack_after: int  # 行動者自身の行動直後スタック
