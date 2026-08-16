"""ヘッズアップ1ハンドを台本通りに進め、core.engineのreducerループ(apply_action)、
分析用action_logの記録、HandRecordの組み立てまでを通しで検証するスクリプト。

pokerkitのAPIはengine.py実装時に実機で個別確認済みだが、この検証は
「engine.py全体を通しで動かしても壊れないか」を確かめる最終チェックにあたる。

実行:
    ./.venv/Scripts/python scripts/verify_engine_e2e.py
"""

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
from poker_trainer.records.schema import build_hand_record

# (street, 意図) ではなく単純な意図の並び。'call'はcheck_or_call、'bet'はmin額でのベット。
# preflop: SBコール/BBチェック -> flop: BBベット/SBコール -> turn/riverは両者チェック -> ショーダウン。
SCRIPT = ["call", "call", "bet", "call", "call", "call", "call", "call"]


def main() -> None:
    seats = (
        SeatConfig(seat_index=0, display_name="Human", is_human=True, playstyle=None, noise=None),
        SeatConfig(
            seat_index=1,
            display_name="CPU (TAG)",
            is_human=False,
            playstyle=PlaystyleType.TAG,
            noise=10.0,
        ),
    )
    hand_state = create_hand(
        hand_id="hand-0001",
        session_id="session-0001",
        seats=seats,
        starting_stacks=(200, 200),
        small_blind=1,
        big_blind=2,
        ante=0,
    )

    for step_number, intent in enumerate(SCRIPT, start=1):
        assert not is_hand_complete(hand_state), f"hand ended early at step {step_number}"
        legal = get_legal_actions(hand_state)
        print(
            f"[step {step_number}] actor={legal.actor_seat} "
            f"street={hand_state.pokerkit_state.street_index} "
            f"can_fold={legal.can_fold} "
            f"can_check_or_call={legal.can_check_or_call}(amount={legal.check_or_call_amount}) "
            f"can_bet_or_raise={legal.can_bet_or_raise}"
            f"(min={legal.min_bet_or_raise_to}, max={legal.max_bet_or_raise_to})"
        )

        if intent == "bet":
            assert legal.can_bet_or_raise, f"step {step_number}: script says bet but it's not legal"
            action = Action.bet_or_raise_to(legal.min_bet_or_raise_to)
        else:
            assert legal.can_check_or_call, f"step {step_number}: script says call but it's not legal"
            action = Action.check_or_call()

        hand_state = apply_action(hand_state, action)
        print(f"           -> {hand_state.action_log[-1]}")

    assert is_hand_complete(hand_state), "hand did not complete after running the script"
    assert len(hand_state.action_log) == len(SCRIPT), (
        f"action_log has {len(hand_state.action_log)} entries, expected {len(SCRIPT)}"
    )
    print(f"\nOK: hand completed after exactly {len(SCRIPT)} scripted actions")

    result = extract_hand_result(hand_state)
    print("\n=== hand result ===")
    print("board_cards:", result.board_cards)
    for outcome in result.seat_outcomes:
        print(" ", outcome)
    print("pot_total:", result.pot_total)

    payoff_sum = sum(outcome.net_result for outcome in result.seat_outcomes)
    assert payoff_sum == 0, f"payoffs are not zero-sum: {payoff_sum}"
    print("OK: payoffs are zero-sum")

    hand_record = build_hand_record(
        hand_state,
        result,
        hand_number=1,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    print("\n=== hand record ===")
    print(hand_record)
    print("\nOK: reducer loop, action logging, and HandRecord construction all verified.")


if __name__ == "__main__":
    main()
