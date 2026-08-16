"""REQUIREMENTS.md 検討事項1: ストリート×ハンド強度カテゴリ×プレイスタイルの
離散ポット%テーブル。noiseはこのテーブルからの逸脱として別レイヤー(cpu.noise)で扱う。
"""

from enum import Enum

from poker_trainer.core.history import Street
from poker_trainer.core.seats import PlaystyleType
from poker_trainer.core.state import HandState, LegalActions


class StreetCategory(Enum):
    FLOP = "flop"
    TURN_RIVER = "turn_river"


class BetIntent(Enum):
    BLOCK = "block"  # 弱いハンドでのブロッキングベット
    VALUE_THIN = "value_thin"  # 薄い価値ベット(STRONG_PAIR相当)
    VALUE_STRONG = "value_strong"  # 厚い価値ベット/ポラライズド(TWO_PAIR_PLUS以上)
    BLUFF = "bluff"  # 完全なブラフ(NOTHING、bluff_frequencyで選ばれた場合)


MAX_POT_PERCENT_POSTFLOP = 2.0  # 検討事項1の上限(200%pot)。テーブル値の暴走に対する保険

POT_PERCENT_TABLE: dict[StreetCategory, dict[BetIntent, dict[PlaystyleType, float]]] = {
    StreetCategory.FLOP: {
        BetIntent.BLOCK: {
            PlaystyleType.TAG: 0.30,
            PlaystyleType.LAG: 0.35,
            PlaystyleType.NIT: 0.25,
            PlaystyleType.CALLING_STATION: 0.30,
        },
        BetIntent.VALUE_THIN: {
            PlaystyleType.TAG: 0.33,
            PlaystyleType.LAG: 0.40,
            PlaystyleType.NIT: 0.33,
            PlaystyleType.CALLING_STATION: 0.33,
        },
        BetIntent.VALUE_STRONG: {
            PlaystyleType.TAG: 0.50,
            PlaystyleType.LAG: 0.65,
            PlaystyleType.NIT: 0.45,
            PlaystyleType.CALLING_STATION: 0.50,
        },
        BetIntent.BLUFF: {
            PlaystyleType.TAG: 0.33,
            PlaystyleType.LAG: 0.45,
            PlaystyleType.NIT: 0.30,
            PlaystyleType.CALLING_STATION: 0.30,
        },
    },
    StreetCategory.TURN_RIVER: {
        BetIntent.BLOCK: {
            PlaystyleType.TAG: 0.25,
            PlaystyleType.LAG: 0.30,
            PlaystyleType.NIT: 0.20,
            PlaystyleType.CALLING_STATION: 0.25,
        },
        BetIntent.VALUE_THIN: {
            PlaystyleType.TAG: 0.55,
            PlaystyleType.LAG: 0.65,
            PlaystyleType.NIT: 0.50,
            PlaystyleType.CALLING_STATION: 0.55,
        },
        BetIntent.VALUE_STRONG: {
            PlaystyleType.TAG: 0.85,
            PlaystyleType.LAG: 1.10,
            PlaystyleType.NIT: 0.75,
            PlaystyleType.CALLING_STATION: 0.85,
        },
        BetIntent.BLUFF: {
            PlaystyleType.TAG: 0.75,
            PlaystyleType.LAG: 1.00,
            PlaystyleType.NIT: 0.60,
            PlaystyleType.CALLING_STATION: 0.60,
        },
    },
}

# プリフロップはpot%ではなくBB倍率(ポットが小さすぎてpot%が機能しないため)
PREFLOP_OPEN_BB_MULTIPLIER: dict[PlaystyleType, float] = {
    PlaystyleType.TAG: 2.5,
    PlaystyleType.LAG: 2.75,
    PlaystyleType.NIT: 2.2,
    PlaystyleType.CALLING_STATION: 2.5,
}
PREFLOP_3BET_MULTIPLIER: dict[PlaystyleType, float] = {  # コール必要額に対する倍率(簡易近似)
    PlaystyleType.TAG: 3.0,
    PlaystyleType.LAG: 3.5,
    PlaystyleType.NIT: 3.0,
    PlaystyleType.CALLING_STATION: 3.0,
}


def street_category(hand_state: HandState) -> StreetCategory:
    street = Street(hand_state.pokerkit_state.street_index)
    return StreetCategory.FLOP if street is Street.FLOP else StreetCategory.TURN_RIVER


def _clamp(amount: int, legal: LegalActions) -> int:
    assert legal.min_bet_or_raise_to is not None
    assert legal.max_bet_or_raise_to is not None
    return max(legal.min_bet_or_raise_to, min(amount, legal.max_bet_or_raise_to))


def pot_percent_to_amount(pot_percent: float, hand_state: HandState, legal: LegalActions) -> int:
    """pot%(「コール後のポット」に対する追加ベット額の割合、という一般的な定義)を
    実際のbet_or_raise_to絶対額へ変換し、[min,max]へクランプする。合法範囲外を
    絶対に返さない(REQUIREMENTS.md 検討事項3)。

    既知の単純化: 同一ストリート内で複数回レイズが応酬される場面(4ベット等)では、
    この式は自分がそのストリートで既に投入済みの額を考慮しないためpot%としての精度は
    落ちるが、後段のクランプにより非合法額になることはない(v1では許容する)。
    """
    if not legal.can_bet_or_raise:
        raise ValueError("no legal bet/raise available")

    pot_after_call = hand_state.pokerkit_state.total_pot_amount + legal.check_or_call_amount
    pot_percent = min(pot_percent, MAX_POT_PERCENT_POSTFLOP)
    target_to = legal.check_or_call_amount + round(pot_percent * pot_after_call)
    return _clamp(target_to, legal)


def preflop_open_amount(hand_state: HandState, legal: LegalActions, playstyle: PlaystyleType) -> int:
    target_to = round(PREFLOP_OPEN_BB_MULTIPLIER[playstyle] * hand_state.big_blind)
    return _clamp(target_to, legal)


def preflop_3bet_amount(hand_state: HandState, legal: LegalActions, playstyle: PlaystyleType) -> int:
    target_to = round(legal.check_or_call_amount * PREFLOP_3BET_MULTIPLIER[playstyle])
    return _clamp(target_to, legal)
