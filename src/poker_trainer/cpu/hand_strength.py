"""eval7による7枚評価(hole+board)を、5段階のHandTierへ単純分類する。
相手レンジは一切見ない、「自分は何を作ったか」+ボード上位カードとの比較のみ
(REQUIREMENTS.md 検討事項4のレンジナローイングは、人間向けの分析機能側の課題であり、
このCPUボットの意思決定ロジックとは無関係)。
"""

from enum import IntEnum

import eval7
from pokerkit import Card

from poker_trainer.core.cards import card_to_str
from poker_trainer.cpu.chen import RANK_ORDER


class HandTier(IntEnum):
    NOTHING = 0  # High Card
    WEAK_PAIR = 1  # Pair(ボード最上位ランク未満、またはholeがペア形成に無関与)
    STRONG_PAIR = 2  # Pair(ボード最上位ランク以上 = トップペア相当/オーバーペア)
    TWO_PAIR_PLUS = 3  # Two Pair, Trips
    NUTTED = 4  # Straight, Flush, Full House, Quads, Straight Flush


# eval7.handtype()の戻り値(実機確認済み: "High Card","Pair","Two Pair","Trips",
# "Straight","Flush","Full House","Quads","Straight Flush")のうち、"Pair"だけは
# _pair_strength_tier()で個別分岐するためここには含めない。
_CATEGORY_TIER: dict[str, HandTier] = {
    "Two Pair": HandTier.TWO_PAIR_PLUS,
    "Trips": HandTier.TWO_PAIR_PLUS,
    "Straight": HandTier.NUTTED,
    "Flush": HandTier.NUTTED,
    "Full House": HandTier.NUTTED,
    "Quads": HandTier.NUTTED,
    "Straight Flush": HandTier.NUTTED,
}

# tierごとの「想定エクイティ」。相手レンジを計算しない代わりに、ポットオッズ判定用の
# 固定アンカー値として使う(fold/call/raiseの閾値計算)。v1暫定値、要調整。
TIER_ASSUMED_EQUITY: dict[HandTier, float] = {
    HandTier.NOTHING: 0.15,
    HandTier.WEAK_PAIR: 0.40,
    HandTier.STRONG_PAIR: 0.65,
    HandTier.TWO_PAIR_PLUS: 0.85,
    HandTier.NUTTED: 0.95,
}


def classify_hand_strength(
    hole_cards: tuple[Card, Card], board_cards: tuple[Card, ...]
) -> HandTier:
    """フロップ以降(board_cardsが3枚以上)専用。プリフロップはcpu.chenを使うこと。"""
    if not board_cards:
        raise ValueError("classify_hand_strength requires board cards; use cpu.chen for preflop")

    cards = [eval7.Card(card_to_str(c)) for c in (*hole_cards, *board_cards)]
    score = eval7.evaluate(cards)
    category = eval7.handtype(score)

    if category == "Pair":
        return _pair_strength_tier(hole_cards, board_cards)
    if category == "High Card":
        return HandTier.NOTHING
    return _CATEGORY_TIER[category]


def _pair_strength_tier(hole_cards: tuple[Card, Card], board_cards: tuple[Card, ...]) -> HandTier:
    hole_ranks = [c.rank.value for c in hole_cards]
    board_ranks = [c.rank.value for c in board_cards]

    if hole_ranks[0] == hole_ranks[1]:
        pair_rank = hole_ranks[0]  # ポケットペア
    else:
        pair_rank = next((r for r in hole_ranks if r in board_ranks), None)

    if pair_rank is None:
        # holeがペア形成に無関与(ボード自体のペアに乗っているだけの稀なケース)は弱扱い
        return HandTier.WEAK_PAIR

    top_board_rank = max(board_ranks, key=RANK_ORDER.index)
    if RANK_ORDER.index(pair_rank) >= RANK_ORDER.index(top_board_rank):
        return HandTier.STRONG_PAIR
    return HandTier.WEAK_PAIR
