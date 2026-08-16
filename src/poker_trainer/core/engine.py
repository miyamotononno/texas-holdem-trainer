"""reducer本体。apply_action(state, action) -> new_state の形でpokerkitを駆動する。

pokerkitのAutomation/State APIは実機で検証済み(検証コマンド履歴はplanファイル参照)。
プレイヤーの意思決定(fold/check_or_call/complete_bet_or_raise_to)以外はすべて
Automationに委ねる、というpokerkit公式推奨パターンに従う。CHIPS_PUSHING/
CHIPS_PULLINGを自動化することで、サイドポット処理は自前実装しない
(REQUIREMENTS.md 検討事項5)。
"""

import copy

from pokerkit import Automation, NoLimitTexasHoldem, State

from poker_trainer.core.actions import Action, ActionType
from poker_trainer.core.cards import card_to_str
from poker_trainer.core.history import ActionRecord, Street
from poker_trainer.core.seats import SeatConfig
from poker_trainer.core.state import HandResult, HandState, LegalActions, SeatOutcome

HAND_AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.CARD_BURNING,
    Automation.HOLE_DEALING,
    Automation.BOARD_DEALING,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
    Automation.RUNOUT_COUNT_SELECTION,
)


def create_hand(
    hand_id: str,
    session_id: str,
    seats: tuple[SeatConfig, ...],
    starting_stacks: tuple[int, ...],
    small_blind: int,
    big_blind: int,
    ante: int = 0,
    min_bet: int | None = None,
) -> HandState:
    """新しいハンドを開始する。len(seats) == len(starting_stacks)(2-8人)。
    min_betは省略時big_blindを用いる(ノーリミットの最小レイズ幅の標準的な慣習)。

    pokerkitは席の座席順を固定の規約で扱う(実機確認済み): 2人卓ではseat0=BB/
    seat1=SB兼ボタン、3人以上ではseat0=SB/seat1=BB/seat2以降=UTG,...,ボタンは
    最終座席(seat len(seats)-1)。ハンドをまたいだボタンのローテーションは
    この関数の外(将来のテーブル進行オーケストレーション)の責務とする。
    button_seatはこの規約から自動算出し、HandRecord用に記録する
    (pokerkit自体の挙動には影響しない)。
    """
    if len(seats) != len(starting_stacks):
        raise ValueError("seats and starting_stacks must have the same length")
    if not (2 <= len(seats) <= 8):
        raise ValueError("num players must be between 2 and 8")

    pokerkit_state = NoLimitTexasHoldem.create_state(
        HAND_AUTOMATIONS,
        True,  # uniform antes(本プロジェクトではボタンアンテ等の非一様antesは扱わない)
        ante,
        (small_blind, big_blind),
        min_bet if min_bet is not None else big_blind,
        starting_stacks,
        len(seats),
    )
    return HandState(
        hand_id=hand_id,
        session_id=session_id,
        pokerkit_state=pokerkit_state,
        seats=seats,
        small_blind=small_blind,
        big_blind=big_blind,
        ante=ante,
        button_seat=1 if len(seats) == 2 else len(seats) - 1,
    )


def get_legal_actions(hand_state: HandState) -> LegalActions:
    """現在の手番の合法な行動を副作用なく読み取る。UIとCPU DecisionMakerの両方から
    呼ばれる想定。手番が存在しない(ハンド終了済み)場合はValueError。"""
    state = hand_state.pokerkit_state
    actor = state.actor_index
    if actor is None:
        raise ValueError(
            "hand has no pending actor (already complete); check is_hand_complete first"
        )

    can_check_or_call = state.can_check_or_call()
    can_bet_or_raise = state.can_complete_bet_or_raise_to()

    return LegalActions(
        actor_seat=actor,
        can_fold=state.can_fold(),
        can_check_or_call=can_check_or_call,
        check_or_call_amount=state.checking_or_calling_amount if can_check_or_call else 0,
        can_bet_or_raise=can_bet_or_raise,
        min_bet_or_raise_to=(
            state.min_completion_betting_or_raising_to_amount if can_bet_or_raise else None
        ),
        max_bet_or_raise_to=(
            state.max_completion_betting_or_raising_to_amount if can_bet_or_raise else None
        ),
    )


def _validate_action(action: Action, legal: LegalActions) -> None:
    if action.type is ActionType.FOLD:
        if not legal.can_fold:
            raise ValueError(f"fold is not legal for seat {legal.actor_seat}")
    elif action.type is ActionType.CHECK_OR_CALL:
        if not legal.can_check_or_call:
            raise ValueError(f"check_or_call is not legal for seat {legal.actor_seat}")
    elif action.type is ActionType.BET_OR_RAISE_TO:
        if not legal.can_bet_or_raise:
            raise ValueError(f"bet_or_raise_to is not legal for seat {legal.actor_seat}")
        assert legal.min_bet_or_raise_to is not None
        assert legal.max_bet_or_raise_to is not None
        if not (legal.min_bet_or_raise_to <= action.amount <= legal.max_bet_or_raise_to):
            raise ValueError(
                f"bet_or_raise_to amount {action.amount} out of legal range "
                f"[{legal.min_bet_or_raise_to}, {legal.max_bet_or_raise_to}] "
                f"for seat {legal.actor_seat}"
            )
    else:
        raise ValueError(f"unknown action type: {action.type}")


def apply_action(hand_state: HandState, action: Action) -> HandState:
    """reducer: apply_action(state, action) -> new_state。

    1. get_legal_actionsで合法性を再検証する(illegalならValueError)。UI/CPUの
       実装ミスや、noise=100%時のCPU行動が暴走してもゲームロジックが壊れないための
       最終防衛ライン(REQUIREMENTS.md 検討事項3)。
    2. 変更前のpokerkit_stateからpot_before/to_call_before/stacks_beforeを記録。
    3. pokerkit_stateをdeepcopyしてから、コピー側に対してのみpokerkitのアクション
       メソッドを呼ぶ(渡されたhand_stateは変更しない)。
    4. ActionRecordを新しいaction_logに追記し、新しいHandStateを返す。
    """
    legal = get_legal_actions(hand_state)
    _validate_action(action, legal)

    state = hand_state.pokerkit_state
    actor = legal.actor_seat
    pot_before = state.total_pot_amount
    to_call_before = legal.check_or_call_amount
    stacks_before = tuple(state.stacks)
    street = Street(state.street_index)

    new_state: State = copy.deepcopy(state)
    if action.type is ActionType.FOLD:
        new_state.fold()
        amount = None
    elif action.type is ActionType.CHECK_OR_CALL:
        new_state.check_or_call()
        amount = to_call_before if to_call_before > 0 else None
    else:  # BET_OR_RAISE_TO
        new_state.complete_bet_or_raise_to(action.amount)
        amount = action.amount

    record = ActionRecord(
        seat_index=actor,
        street=street,
        action_type=action.type,
        amount=amount,
        pot_before=pot_before,
        to_call_before=to_call_before,
        stacks_before=stacks_before,
        stack_after=new_state.stacks[actor],
    )

    return HandState(
        hand_id=hand_state.hand_id,
        session_id=hand_state.session_id,
        pokerkit_state=new_state,
        seats=hand_state.seats,
        small_blind=hand_state.small_blind,
        big_blind=hand_state.big_blind,
        ante=hand_state.ante,
        button_seat=hand_state.button_seat,
        action_log=[*hand_state.action_log, record],
    )


def is_hand_complete(hand_state: HandState) -> bool:
    return not hand_state.pokerkit_state.status


def _final_pot_total(action_log: list[ActionRecord]) -> int:
    """pokerkitはハンド終了と同時にCHIPS_PUSHING/CHIPS_PULLINGでポットを払い出して
    しまうため、終了後にtotal_pot_amountを読むと0になっている。ハンドは必ず
    FOLDかCHECK_OR_CALL(チェックで場が閉じる、または最後のコール)で終わり、
    応答待ちのBET_OR_RAISE_TOで終わることはないため、最後の行動記録から
    最終ポット額を復元できる。"""
    if not action_log:
        return 0
    last = action_log[-1]
    contribution = last.to_call_before if last.action_type is ActionType.CHECK_OR_CALL else 0
    return last.pot_before + contribution


def extract_hand_result(hand_state: HandState) -> HandResult:
    """is_hand_complete(hand_state)がTrueの前提で、payoffs/board_cards/hole_cards
    からHandResultを構築する。records.schema.HandRecordへ詰め替える材料になる。"""
    if not is_hand_complete(hand_state):
        raise ValueError("hand is not complete yet")
    state = hand_state.pokerkit_state

    board_cards = tuple(
        card_to_str(card) for group in state.board_cards for card in group
    )

    seat_outcomes = tuple(
        SeatOutcome(
            seat_index=i,
            starting_stack=state.starting_stacks[i],
            ending_stack=state.stacks[i],
            net_result=state.payoffs[i],
            hole_cards=(
                "".join(card_to_str(c) for c in state.hole_cards[i])
                if state.hole_cards[i]
                else None
            ),
            showed_down=bool(state.hole_cards[i]),
        )
        for i in range(len(hand_state.seats))
    )

    return HandResult(
        board_cards=board_cards,
        seat_outcomes=seat_outcomes,
        pot_total=_final_pot_total(hand_state.action_log),
    )
