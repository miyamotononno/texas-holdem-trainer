"""保存JSON(1セッションの全記録)の第一版スキーマ。プリミティブ型・tuple・
str-encodedカードのみで構成し、dataclasses.asdict + json.dumpsで素直に
シリアライズできる形にしている(JSON I/O自体はこのモジュールのスコープ外、
REQUIREMENTS.md 4.4: 明示的な「保存」操作時のみ出力し毎ハンド自動保存はしない)。
"""

from dataclasses import dataclass, field

from poker_trainer.core.history import ActionRecord
from poker_trainer.core.seats import PlaystyleType, SeatConfig
from poker_trainer.core.state import HandResult, HandState


@dataclass(frozen=True)
class SeatResult:
    """1ハンド終了時点の1席分の結果。"""

    seat_index: int
    display_name: str
    is_human: bool
    playstyle: PlaystyleType | None
    starting_stack: int
    ending_stack: int
    net_result: int  # pokerkitのpayoffs[seat_index]
    hole_cards: str  # 例: "AhKs"。常に実際に配られたカード(1人用ローカルアプリのため
    # 対戦相手を隠すプライバシー境界はなく、ショーダウンで公開されなくても保持する)
    showed_down: bool  # ショーダウンで対戦相手に公開されたか


@dataclass(frozen=True)
class HandRecord:
    """1ハンドの全記録。分析機能がpokerkitへ再アクセスせずにハンドを
    再構築・レビューできるだけの情報を持つ。"""

    hand_id: str
    session_id: str
    hand_number: int  # セッション内の1始まりの通し番号
    started_at: str  # ISO 8601
    num_players: int
    button_seat: int
    small_blind: int
    big_blind: int
    ante: int
    seats: tuple[SeatConfig, ...]  # そのハンドで実際に使われたプレイスタイル/noiseのスナップショット
    starting_stacks: tuple[int, ...]
    action_log: tuple[ActionRecord, ...]
    board_cards: tuple[str, ...]
    results: tuple[SeatResult, ...]
    pot_total: int


@dataclass(frozen=True)
class TableSettings:
    """セッション全体で固定のテーブル設定(v1では途中リバイ/リシートは扱わない)。"""

    num_players: int
    small_blind: int
    big_blind: int
    ante: int
    starting_stack: int


@dataclass
class SessionRecord:
    """1セッションの全記録。明示的な「保存」操作時のみJSONへ出力する。"""

    session_id: str
    started_at: str
    table_settings: TableSettings
    hands: list[HandRecord] = field(default_factory=list)
    ended_at: str | None = None


def build_hand_record(
    hand_state: HandState,
    hand_result: HandResult,
    hand_number: int,
    started_at: str,
) -> HandRecord:
    """終了済みのHandState(進行中に蓄積されたaction_log)とHandResult
    (engine.extract_hand_resultの出力)から、保存用のHandRecordを組み立てる。"""
    seats_by_index = {seat.seat_index: seat for seat in hand_state.seats}
    results = tuple(
        SeatResult(
            seat_index=outcome.seat_index,
            display_name=seats_by_index[outcome.seat_index].display_name,
            is_human=seats_by_index[outcome.seat_index].is_human,
            playstyle=seats_by_index[outcome.seat_index].playstyle,
            starting_stack=outcome.starting_stack,
            ending_stack=outcome.ending_stack,
            net_result=outcome.net_result,
            hole_cards=outcome.hole_cards,
            showed_down=outcome.showed_down,
        )
        for outcome in hand_result.seat_outcomes
    )
    starting_stacks = tuple(outcome.starting_stack for outcome in hand_result.seat_outcomes)

    return HandRecord(
        hand_id=hand_state.hand_id,
        session_id=hand_state.session_id,
        hand_number=hand_number,
        started_at=started_at,
        num_players=len(hand_state.seats),
        button_seat=hand_state.button_seat,
        small_blind=hand_state.small_blind,
        big_blind=hand_state.big_blind,
        ante=hand_state.ante,
        seats=hand_state.seats,
        starting_stacks=starting_stacks,
        action_log=tuple(hand_state.action_log),
        board_cards=hand_result.board_cards,
        results=results,
        pot_total=hand_result.pot_total,
    )
