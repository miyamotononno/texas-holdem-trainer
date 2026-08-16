"""analysis/配下のツール関数群をanthropicなしで検証するスクリプト。
(client.beta.messages.tool_runnerを使うorchestrator.pyはscripts/verify_analysis.pyで別途検証する)

実行:
    ./.venv/Scripts/python scripts/verify_analysis_tools.py
"""

import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from poker_trainer.analysis.positions import position_label
from poker_trainer.analysis.tools import (
    calculate_equity,
    calculate_hand_percentile,
    calculate_pot_odds,
    classify_made_hand,
    lookup_preflop_reference,
    narrow_opponent_range,
)
from poker_trainer.core.seats import PlaystyleType


def check_positions() -> None:
    print("=== 1. positions.position_label ===")
    assert position_label(0, 2) == "BB"
    assert position_label(1, 2) == "BTN"
    assert position_label(0, 6) == "SB"
    assert position_label(1, 6) == "BB"
    assert position_label(5, 6) == "BTN"
    assert position_label(2, 6) == "UTG"
    print("OK: 2人卓・6人卓のポジション名が期待通り")


def check_hand_percentile_and_preflop_reference() -> None:
    print("\n=== 2. calculate_hand_percentile / lookup_preflop_reference ===")
    aa = calculate_hand_percentile("AhAd")
    print("AA percentile:", aa)
    assert aa["percentile"] == 0.0

    weak = calculate_hand_percentile("7h2c")
    print("72o percentile:", weak)
    assert weak["percentile"] == 1.0

    print(lookup_preflop_reference("UTG", aa["percentile"]))
    print(lookup_preflop_reference("UTG", weak["percentile"]))
    print(lookup_preflop_reference("BB", weak["percentile"]))


def check_classify_and_pot_odds() -> None:
    print("\n=== 3. classify_made_hand / calculate_pot_odds ===")
    result = classify_made_hand("8h8d", "8c4d2h")
    print("set:", result)
    assert result["hand_type"] == "Trips"

    odds = calculate_pot_odds(pot=100, call_amount=50)
    print("pot odds (call 50 into 100):", odds)
    assert abs(odds["required_equity"] - 50 / 150) < 1e-3  # calculate_pot_oddsは小数第4位で丸める

    free_check = calculate_pot_odds(pot=100, call_amount=0)
    print("pot odds (free check):", free_check)
    assert free_check["required_equity"] == 0.0


def check_narrow_range_and_equity() -> None:
    print("\n=== 4. narrow_opponent_range / calculate_equity(検討事項4) ===")
    for playstyle in PlaystyleType:
        result = narrow_opponent_range(playstyle.value, "raised", facing_raise=False)
        combo_count = len(result["range"].split(","))
        print(f"  {playstyle.value:16s} open-raise range: {combo_count} 正準ハンド")
        assert combo_count > 0

    tag_range = narrow_opponent_range("tag", "raised", facing_raise=False)["range"]
    equity = calculate_equity(hero_hand="AhKh", villain_range=tag_range, board="")
    print(f"  AKs vs TAGのオープンレイズレンジ: {equity}")
    assert 0.0 <= equity["equity"] <= 1.0

    equity_flop = calculate_equity(
        hero_hand="AhKh", villain_range=tag_range, board="Kd7c2h"
    )
    print(f"  AK(トップペア) vs TAGレンジ on K72r: {equity_flop}")
    assert equity_flop["equity"] > equity["equity"]  # トップペアはプリフロップより強くなっているはず


def main() -> None:
    check_positions()
    check_hand_percentile_and_preflop_reference()
    check_classify_and_pot_odds()
    check_narrow_range_and_equity()
    print("\nOK: analysis/配下のツール関数はすべて期待通り動作した(anthropic不要)")


if __name__ == "__main__":
    main()
