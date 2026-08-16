"""Claude tool-use分析機能に公開するツール関数群(REQUIREMENTS.md 4.2)。

@beta_tool(anthropic SDK)デコレータの適用はorchestrator.py側で行い、ここでは
プレーンな関数として実装する。anthropicに依存しないため、scripts/verify_analysis_tools.py
でanthropicのインストールを待たずに検証できる。

固定的な計算パイプラインではなく、Claude自身がハンドの分析に必要な計算をこれらのツールの
中から選んで呼び出す(エージェント的構成)。
"""

import eval7

from poker_trainer.analysis.preflop_chart import recommended_preflop_action
from poker_trainer.analysis.range_narrowing import narrow_range_by_actions
from poker_trainer.core.seats import PlaystyleType
from poker_trainer.cpu.chen import CHEN_PERCENTILE, canonical_hand_key


def _split_cards(card_str: str) -> list[str]:
    """例: "AhKs" -> ["Ah", "Ks"]。card_strは2文字(rank+suit)の連結を想定。"""
    return [card_str[i : i + 2] for i in range(0, len(card_str), 2)]


def calculate_equity(hero_hand: str, villain_range: str, board: str = "") -> dict:
    """heroのハンド(例: "AhKs")が、villainのレンジ(例: "22+,AKs,AQo+")に対して持つ
    エクイティをモンテカルロ法で計算する。boardは省略可(例: "Kd7c2h")。"""
    hero_cards = [eval7.Card(c) for c in _split_cards(hero_hand)]
    villain = eval7.HandRange(villain_range)
    board_cards = [eval7.Card(c) for c in _split_cards(board)] if board else []
    equity = eval7.py_hand_vs_range_monte_carlo(hero_cards, villain, board_cards, 20000)
    return {"equity": round(equity, 4)}


def classify_made_hand(hole_cards: str, board_cards: str) -> dict:
    """hole_cards(例: "AhKs")とboard_cards(例: "Kd7c2h")から、現在完成している
    役の種類("High Card","Pair","Two Pair","Trips","Straight","Flush","Full House",
    "Quads","Straight Flush"のいずれか)を返す。"""
    cards = [eval7.Card(c) for c in _split_cards(hole_cards + board_cards)]
    score = eval7.evaluate(cards)
    return {"hand_type": eval7.handtype(score)}


def calculate_pot_odds(pot: int, call_amount: int) -> dict:
    """コールに必要な額(call_amount)とコール前のポットサイズ(pot)から、
    コールが損益分岐する必要勝率(ポットオッズ)を返す。call_amountが0ならチェック可能
    (必要勝率0)を意味する。"""
    if call_amount <= 0:
        return {"required_equity": 0.0}
    required_equity = call_amount / (pot + call_amount)
    return {"required_equity": round(required_equity, 4)}


def calculate_hand_percentile(hole_cards: str) -> dict:
    """プリフロップのハンド(例: "AhKs")について、Chen Formulaによる強さの順位を返す。
    0.0が最強(AA)、1.0が最弱(72o)。"""
    card1, card2 = _split_cards(hole_cards)
    rank1, suit1 = card1[0], card1[1]
    rank2, suit2 = card2[0], card2[1]
    key = canonical_hand_key(rank1, rank2, suit1 == suit2)
    return {"percentile": CHEN_PERCENTILE[key]}


def lookup_preflop_reference(position: str, chen_percentile: float) -> dict:
    """ポジション名(例: "UTG","CO","BTN","SB","BB")とハンドのChenパーセンタイル
    (calculate_hand_percentileの結果、0.0=最強〜1.0=最弱)から、公開されている
    一般的なオープンレンジの目安と比較したコメントを返す。"""
    return {"comment": recommended_preflop_action(position, chen_percentile)}


def narrow_opponent_range(playstyle: str, preflop_action: str, facing_raise: bool) -> dict:
    """相手のプレイスタイル("tag"/"lag"/"nit"/"calling_station")と実際に取った
    プリフロップアクション("raised"/"called"/"folded")、レイズに直面していたか
    (facing_raise)から、相手の推定レンジをeval7が解釈できる文字列で返す
    (REQUIREMENTS.md 検討事項4: 相手の実際の隠しハンドでも完全ランダムでもなく、
    プレイスタイル別レンジ表×実際のアクションで絞り込む)。返り値のrangeは
    calculate_equityのvillain_rangeにそのまま渡せる。"""
    style = PlaystyleType(playstyle)
    range_str = narrow_range_by_actions(style, preflop_action, facing_raise)  # type: ignore[arg-type]
    return {"range": range_str}
