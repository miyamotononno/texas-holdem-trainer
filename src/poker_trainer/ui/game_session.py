"""Streamlit非依存の、複数ハンドにわたるゲーム進行ロジック。

st.session_stateに直接pokerkitの生Stateやdataclassを保持できる(サーバ側インメモリの
ため、JSONシリアライズは不要)ことを前提に、GameSessionインスタンスをそのまま
st.session_stateへ格納して使う想定。Streamlit固有のコードはui/app.pyにのみ書く。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from poker_trainer.core.actions import Action
from poker_trainer.core.engine import (
    apply_action,
    create_hand,
    extract_hand_result,
    get_legal_actions,
    is_hand_complete,
)
from poker_trainer.core.seats import PlaystyleType, SeatConfig
from poker_trainer.core.state import HandResult, HandState
from poker_trainer.cpu.policy import CPUDecisionMaker
from poker_trainer.records.schema import SessionRecord, TableSettings, build_hand_record


@dataclass(frozen=True)
class Participant:
    """テーブルに固定的に座っている参加者。座席index(pokerkitの物理的な席順)への
    割り当ては毎ハンドローテーションするため、Participant自体は席順を持たない。"""

    display_name: str
    is_human: bool
    playstyle: PlaystyleType | None  # 人間はNone
    noise: float | None


@dataclass
class GameSession:
    participants: tuple[Participant, ...]
    small_blind: int
    big_blind: int
    cpu_policy: CPUDecisionMaker
    stacks: dict[int, int]  # participant index -> 現在のスタック(0なら脱落)
    session_record: SessionRecord
    hand_state: HandState | None = None
    hand_number: int = 0
    last_hand_result: HandResult | None = None
    _seat_to_participant: dict[int, int] = field(default_factory=dict)

    @staticmethod
    def new(
        participants: tuple[Participant, ...],
        small_blind: int,
        big_blind: int,
        starting_stack: int,
        cpu_policy: CPUDecisionMaker,
    ) -> "GameSession":
        session_id = f"session-{datetime.now(timezone.utc).isoformat()}"
        return GameSession(
            participants=participants,
            small_blind=small_blind,
            big_blind=big_blind,
            cpu_policy=cpu_policy,
            stacks={i: starting_stack for i in range(len(participants))},
            session_record=SessionRecord(
                session_id=session_id,
                started_at=datetime.now(timezone.utc).isoformat(),
                table_settings=TableSettings(
                    num_players=len(participants),
                    small_blind=small_blind,
                    big_blind=big_blind,
                    ante=0,
                    starting_stack=starting_stack,
                ),
            ),
        )

    def active_participant_indices(self) -> list[int]:
        return [i for i, stack in self.stacks.items() if stack > 0]

    def active_participant_count(self) -> int:
        return len(self.active_participant_indices())

    def human_participant_index(self) -> int | None:
        for i, p in enumerate(self.participants):
            if p.is_human:
                return i
        return None

    def start_new_hand(self) -> None:
        """脱落者(スタック0)を除いた参加者で新しいハンドを作る。hand_numberを使って
        参加者→座席indexの割り当てを1つずつローテーションする(ボタンローテーションの
        代替。固定ポジションだと特定のプレイスタイルが常に同じ席になり挙動が偏る---
        scripts/verify_rule_based_cpu.pyの検証で確認済みの問題と同じ)。"""
        active = self.active_participant_indices()
        if len(active) < 2:
            raise ValueError("cannot start a hand with fewer than 2 active participants")

        rotation = self.hand_number % len(active)
        rotated = active[rotation:] + active[:rotation]
        self._seat_to_participant = dict(enumerate(rotated))

        seats = tuple(
            SeatConfig(
                seat_index=seat_index,
                display_name=self.participants[p_idx].display_name,
                is_human=self.participants[p_idx].is_human,
                playstyle=self.participants[p_idx].playstyle,
                noise=self.participants[p_idx].noise,
            )
            for seat_index, p_idx in self._seat_to_participant.items()
        )
        starting_stacks = tuple(self.stacks[p_idx] for p_idx in rotated)

        self.hand_number += 1
        self.last_hand_result = None
        self.hand_state = create_hand(
            hand_id=f"{self.session_record.session_id}-hand-{self.hand_number}",
            session_id=self.session_record.session_id,
            seats=seats,
            starting_stacks=starting_stacks,
            small_blind=self.small_blind,
            big_blind=self.big_blind,
        )
        self.advance_cpu_turns()
        self.finalize_hand_if_complete()  # 全員フォールド等でCPUだけでハンドが終わる場合もある

    def is_awaiting_human_action(self) -> bool:
        if self.hand_state is None or is_hand_complete(self.hand_state):
            return False
        legal = get_legal_actions(self.hand_state)
        participant_idx = self._seat_to_participant[legal.actor_seat]
        return self.participants[participant_idx].is_human

    def advance_cpu_turns(self) -> None:
        """手番がCPUの間、cpu_policy.decide() -> apply_actionをループする。
        人間の手番になるかハンドが終了したら停止する。"""
        assert self.hand_state is not None
        while not is_hand_complete(self.hand_state):
            legal = get_legal_actions(self.hand_state)
            participant_idx = self._seat_to_participant[legal.actor_seat]
            if self.participants[participant_idx].is_human:
                return
            action = self.cpu_policy.decide(self.hand_state, legal.actor_seat, legal)
            self.hand_state = apply_action(self.hand_state, action)

    def submit_human_action(self, action: Action) -> None:
        assert self.hand_state is not None
        self.hand_state = apply_action(self.hand_state, action)
        self.advance_cpu_turns()

    def finalize_hand_if_complete(self) -> None:
        """ハンドが終了していれば結果を記録し、スタックを更新する。まだ進行中なら何もしない。"""
        if self.hand_state is None or not is_hand_complete(self.hand_state):
            return
        if self.last_hand_result is not None:
            return  # 既に確定処理済み

        result = extract_hand_result(self.hand_state)
        self.last_hand_result = result
        record = build_hand_record(
            self.hand_state,
            result,
            hand_number=self.hand_number,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.session_record.hands.append(record)

        for outcome in result.seat_outcomes:
            participant_idx = self._seat_to_participant[outcome.seat_index]
            self.stacks[participant_idx] = outcome.ending_stack
