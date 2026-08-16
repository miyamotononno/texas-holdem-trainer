"""Streamlitのst.session_stateに格納される想定のreducer状態(HandState)と、
アクション選択に必要な情報(LegalActions)、ハンド終了後の結果(HandResult)を定義する。"""

from dataclasses import dataclass, field

from pokerkit import State

from poker_trainer.core.history import ActionRecord
from poker_trainer.core.seats import SeatConfig


@dataclass
class HandState:
    """engine.apply_actionのreducer状態。pokerkitのStateをカード/ポット/スタックの
    正とし、それ以外の(pokerkitが知らない)メタデータ---席のプレイスタイル/noiseの
    割り当てと、分析機能向けの行動ログ---をこのラッパーが保持する。"""

    hand_id: str
    session_id: str
    pokerkit_state: State
    seats: tuple[SeatConfig, ...]
    small_blind: int
    big_blind: int
    ante: int
    button_seat: int
    action_log: list[ActionRecord] = field(default_factory=list)


@dataclass(frozen=True)
class LegalActions:
    """現在の手番プレイヤーが取りうる行動。将来のStreamlit UI(どのボタン/スライダーを
    描画するか)とCPU DecisionMaker(何を選べるか)の両方から参照される。"""

    actor_seat: int
    can_fold: bool
    can_check_or_call: bool
    check_or_call_amount: int  # 0=チェック、>0=コール額
    can_bet_or_raise: bool
    min_bet_or_raise_to: int | None  # can_bet_or_raiseがFalseならNone
    max_bet_or_raise_to: int | None  # オールイン上限。can_bet_or_raiseがFalseならNone


@dataclass(frozen=True)
class SeatOutcome:
    """ハンド終了後の1席分の結果。records.schema.SeatResultへ詰め替える際の
    材料になる(display_name/is_human/playstyleはSeatConfigから補う)。"""

    seat_index: int
    starting_stack: int
    ending_stack: int
    net_result: int  # pokerkit の payoffs[seat_index]
    hole_cards: str | None  # 例: "AhKs"。ショーダウンで公開されなければNone
    showed_down: bool


@dataclass(frozen=True)
class HandResult:
    """extract_hand_resultの戻り値。records.schema.HandRecordを組み立てるのに
    必要な、pokerkit由来の情報一式(pokerkitへの依存はここまでに閉じ込める)。"""

    board_cards: tuple[str, ...]
    seat_outcomes: tuple[SeatOutcome, ...]
    pot_total: int
