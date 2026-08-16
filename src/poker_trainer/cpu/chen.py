"""プリフロップのハンド強度を、eval7のMonte Carlo/レンジ文字列(「任意の2枚」を表す
構文が未検証)に頼らず、Chen Formula(決定的・外部ライブラリ不要のクローズドフォーム)で
169通りに順位付けする。169ハンド全通りは軽量なため、モジュールロード時に一度だけ計算し
モジュール定数として保持する(キャッシュ機構は不要)。

注意: ここで使うギャップ調整の数値は、Wikipedia等でよく見る古典的なChen Formula
(0:0, 1:-1, 2:-1, 3:-2, 4+:-4)とは異なる変種。本プロジェクトではこの変種で実装し、
「AAが最強」「ペアは同ランクの非ペアより強い」等の順序妥当性のみを検証する
(絶対値の正確さは問わない、scripts/verify_rule_based_cpu.py参照)。
"""

from itertools import combinations

from pokerkit import Card

RANK_ORDER = "23456789TJQKA"  # index 0=2 ... 12=A

_HIGH_CARD_VALUE: dict[str, float] = {
    "A": 10.0,
    "K": 8.0,
    "Q": 7.0,
    "J": 6.0,
    "T": 5.0,
    "9": 4.5,
    "8": 4.0,
    "7": 3.5,
    "6": 3.0,
    "5": 2.5,
    "4": 2.0,
    "3": 1.5,
    "2": 1.0,
}

_GAP_ADJUSTMENT = {0: 1.0, 1: 1.0, 2: 0.0, 3: -1.0}
_GAP_ADJUSTMENT_DEFAULT = -2.0  # gap >= 4


def chen_score(rank1: str, rank2: str, suited: bool) -> float:
    """rank1/rank2はpokerkit Rank.value相当の1文字("2".."9","T","J","Q","K","A")。"""
    if rank1 == rank2:
        base = _HIGH_CARD_VALUE[rank1] * 2.0
        return max(base, 5.0)

    hi, lo = sorted((rank1, rank2), key=lambda r: RANK_ORDER.index(r), reverse=True)
    score = _HIGH_CARD_VALUE[hi]
    if suited:
        score += 2.0

    gap = RANK_ORDER.index(hi) - RANK_ORDER.index(lo) - 1
    score += _GAP_ADJUSTMENT.get(gap, _GAP_ADJUSTMENT_DEFAULT)

    both_le_queen = RANK_ORDER.index(hi) <= RANK_ORDER.index("Q")
    if both_le_queen and (suited or gap <= 1):
        score += 1.0

    return score


def chen_score_from_cards(card1: Card, card2: Card) -> float:
    return chen_score(card1.rank.value, card2.rank.value, card1.suit == card2.suit)


def canonical_hand_key(rank1: str, rank2: str, suited: bool) -> str:
    """169通りの正準表記("AKs","72o","77")。"""
    if rank1 == rank2:
        return rank1 + rank2
    hi, lo = sorted((rank1, rank2), key=lambda r: RANK_ORDER.index(r), reverse=True)
    return f"{hi}{lo}{'s' if suited else 'o'}"


def _build_percentile_table() -> dict[str, float]:
    scored: dict[str, float] = {}
    for r1, r2 in combinations(RANK_ORDER, 2):
        for suited in (True, False):
            key = canonical_hand_key(r1, r2, suited)
            scored[key] = chen_score(r1, r2, suited)
    for r in RANK_ORDER:
        scored[canonical_hand_key(r, r, False)] = chen_score(r, r, False)

    # 高スコア(強い)から順に並べ、0.0(最強)〜1.0(最弱)のパーセンタイルを付与。
    ordered = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    n = len(ordered) - 1  # 168
    return {key: idx / n for idx, (key, _score) in enumerate(ordered)}


CHEN_PERCENTILE: dict[str, float] = _build_percentile_table()  # 169エントリ


def chen_percentile_from_cards(card1: Card, card2: Card) -> float:
    """0.0=最強(AA)、1.0=最弱。閾値との比較に使う(percentile <= cutoffならプレイ)。"""
    key = canonical_hand_key(card1.rank.value, card2.rank.value, card1.suit == card2.suit)
    return CHEN_PERCENTILE[key]
