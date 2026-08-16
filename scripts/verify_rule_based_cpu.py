"""RuleBasedPlayerの検証スクリプト(scripts/verify_engine_e2e.pyと同じ流儀: pytest等は
導入せず、stdoutに結果を出してassertする)。

実行:
    ./.venv/Scripts/python scripts/verify_rule_based_cpu.py
"""

import random
import sys
from collections import defaultdict

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from pokerkit import Card

from poker_trainer.core.actions import ActionType
from poker_trainer.core.engine import apply_action, create_hand, get_legal_actions, is_hand_complete
from poker_trainer.core.history import Street
from poker_trainer.core.seats import PlaystyleType, SeatConfig
from poker_trainer.cpu.chen import CHEN_PERCENTILE, canonical_hand_key
from poker_trainer.cpu.hand_strength import HandTier, classify_hand_strength
from poker_trainer.cpu.rule_based import RuleBasedPlayer


def check_chen_table_ordering() -> None:
    print("=== 1. Chenテーブルの順序妥当性 ===")
    assert CHEN_PERCENTILE["AA"] == 0.0, "AA must be the strongest hand"
    assert CHEN_PERCENTILE["77"] < CHEN_PERCENTILE["72o"], "77 should beat 72o"
    assert CHEN_PERCENTILE["AKs"] < CHEN_PERCENTILE["AKo"], "suited should beat offsuit"
    assert CHEN_PERCENTILE["87s"] < CHEN_PERCENTILE["82o"], "connector should beat a disconnected hand"
    print("OK: AA=0.0最強, ペア/スーテッド/コネクターの順序性がすべて妥当")


def check_hand_strength_fixtures() -> None:
    print("\n=== 2. hand_strengthの単体チェック ===")

    def cards(s: str) -> tuple[Card, ...]:
        return tuple(Card.parse(s))

    cases: list[tuple[str, str, HandTier]] = [
        ("8h8d", "8c4d2h", HandTier.TWO_PAIR_PLUS),  # トップセット
        ("AhAd", "Kd7c2h", HandTier.STRONG_PAIR),  # オーバーペア
        ("Ah2c", "Kd7c2h", HandTier.WEAK_PAIR),  # ボトムペア
        ("AhKh", "2h9hQh", HandTier.NUTTED),  # フラッシュ
        ("AhAd", "AcAs2h", HandTier.NUTTED),  # クアッズ
        ("Ah2c", "Kd7c9h", HandTier.NOTHING),  # 何もない
    ]
    for hole_str, board_str, expected in cases:
        tier = classify_hand_strength(cards(hole_str), cards(board_str))
        assert tier == expected, f"{hole_str}/{board_str}: expected {expected}, got {tier}"
        print(f"  {hole_str} on {board_str} -> {tier.name} OK")
    print("OK: 全フィクスチャが期待通りのtierに分類された")


def _make_seats(playstyles: list[PlaystyleType], noise: float) -> tuple[SeatConfig, ...]:
    return tuple(
        SeatConfig(
            seat_index=i,
            display_name=f"CPU-{style.value}-{i}",
            is_human=False,
            playstyle=style,
            noise=noise,
        )
        for i, style in enumerate(playstyles)
    )


def _run_session(playstyles: list[PlaystyleType], noise: float, num_hands: int, seed: int):
    """seat_index(=pokerkitの固定席順、SB/BB/UTG/Buttonの並びは席順で決まる)に対する
    playstyleの割り当てを毎ハンド1つずつローテーションする(ボタンローテーションの簡易代替)。
    ローテーションしないと、特定のプレイスタイルが常に同じポジション(例: 常にBB)に
    固定され、実際のVPIP/PFR統計(複数ポジションの平均)とは比較にならない数値になる
    (実機テストで確認: 常にBBに固定されたLAGはVPIPがTAGより低く出た)。"""
    player = RuleBasedPlayer(rng=random.Random(seed + 1))
    n = len(playstyles)
    stacks = tuple(200 for _ in playstyles)

    results = []
    for hand_number in range(num_hands):
        rotation = hand_number % n
        seat_styles = [playstyles[(i + rotation) % n] for i in range(n)]
        seats = _make_seats(seat_styles, noise)
        hand_state = create_hand(
            hand_id=f"hand-{hand_number}",
            session_id="session-verify",
            seats=seats,
            starting_stacks=stacks,
            small_blind=1,
            big_blind=2,
        )
        while not is_hand_complete(hand_state):
            legal = get_legal_actions(hand_state)
            action = player.decide(hand_state, legal.actor_seat, legal)
            hand_state = apply_action(hand_state, action)
        results.append((hand_state.action_log, seat_styles))
    return results


def check_noise_100_never_illegal() -> None:
    print("\n=== 3. noise=100%での合法性ストレステスト ===")
    for num_players in (2, 3, 5, 8):
        playstyles = [
            [PlaystyleType.TAG, PlaystyleType.LAG, PlaystyleType.NIT, PlaystyleType.CALLING_STATION][
                i % 4
            ]
            for i in range(num_players)
        ]
        results = _run_session(playstyles, noise=100.0, num_hands=100, seed=num_players)
        total_actions = sum(len(log) for log, _seat_styles in results)
        print(f"  {num_players}人卓 x100ハンド: {total_actions}アクション、例外なし OK")
    print("OK: apply_actionが一度もValueErrorを投げなかった(検討事項3の担保)")


def check_vpip_pfr_calibration() -> None:
    print("\n=== 4/5. VPIP/PFR較正 & 相対順序チェック ===")
    playstyles = [PlaystyleType.TAG, PlaystyleType.LAG, PlaystyleType.NIT, PlaystyleType.CALLING_STATION]
    results = _run_session(playstyles, noise=0.0, num_hands=500, seed=42)

    vpip_count: dict[PlaystyleType, int] = defaultdict(int)
    pfr_count: dict[PlaystyleType, int] = defaultdict(int)
    bet_pct_sum: dict[PlaystyleType, float] = defaultdict(float)
    bet_pct_n: dict[PlaystyleType, int] = defaultdict(int)
    hands = len(results)

    for log, seat_styles in results:
        # PFR/VPIPは「ハンド単位」の統計(1ハンドにつき最大1)。同一ハンド内で
        # 3ベット/4ベットのように複数回レイズしても2重カウントしないよう、
        # レイズ/VPIPそれぞれ別のsetで一度ハンド内の該当席を集めてから加算する
        # (レイズ回数をそのままpfr_countに積むと、複数回レイズするLAG等で
        # PFR%がVPIP%を上回るという矛盾したバグを生む---最初の実装はこれだった)。
        voluntary_seats_this_hand: set[int] = set()
        raised_seats_this_hand: set[int] = set()
        for record in log:
            style = seat_styles[record.seat_index]
            if record.street is not Street.PREFLOP:
                if record.action_type is ActionType.BET_OR_RAISE_TO and record.pot_before > 0:
                    pct = (record.amount - record.to_call_before) / record.pot_before
                    bet_pct_sum[style] += pct
                    bet_pct_n[style] += 1
                continue
            if record.action_type is ActionType.BET_OR_RAISE_TO:
                voluntary_seats_this_hand.add(record.seat_index)
                raised_seats_this_hand.add(record.seat_index)
            elif record.action_type is ActionType.CHECK_OR_CALL and record.amount:
                voluntary_seats_this_hand.add(record.seat_index)
        for seat_index in voluntary_seats_this_hand:
            vpip_count[seat_styles[seat_index]] += 1
        for seat_index in raised_seats_this_hand:
            pfr_count[seat_styles[seat_index]] += 1

    anchors = {
        PlaystyleType.TAG: "18-22%/~VPIP",
        PlaystyleType.LAG: "28%/24%",
        PlaystyleType.NIT: "13%/5-8%",
        PlaystyleType.CALLING_STATION: "35%+/3-5%",
    }
    measured_vpip = {}
    for style in playstyles:
        vpip = 100 * vpip_count[style] / hands
        pfr = 100 * pfr_count[style] / hands
        measured_vpip[style] = vpip
        avg_bet_pct = 100 * bet_pct_sum[style] / bet_pct_n[style] if bet_pct_n[style] else 0.0
        print(
            f"  {style.value:16s} VPIP={vpip:5.1f}% PFR={pfr:5.1f}% "
            f"(要件アンカー: {anchors[style]})  平均postflopベット={avg_bet_pct:5.1f}%pot"
        )

    print(
        f"\n  相対順序: LAG({measured_vpip[PlaystyleType.LAG]:.1f}) > "
        f"TAG({measured_vpip[PlaystyleType.TAG]:.1f}) > "
        f"NIT({measured_vpip[PlaystyleType.NIT]:.1f})? "
        f"{measured_vpip[PlaystyleType.LAG] > measured_vpip[PlaystyleType.TAG] > measured_vpip[PlaystyleType.NIT]}"
    )


def main() -> None:
    check_chen_table_ordering()
    check_hand_strength_fixtures()
    check_noise_100_never_illegal()
    check_vpip_pfr_calibration()
    print("\nOK: RuleBasedPlayer verification complete.")


if __name__ == "__main__":
    main()
