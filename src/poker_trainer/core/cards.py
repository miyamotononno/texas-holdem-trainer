"""pokerkit Cardのコンパクト文字列表現への変換。pokerkit標準のstr(card)は冗長な
英語表記("JACK OF SPADES (Js)")を返すため、rank/suitのvalueから直接組み立てる。
core.engine(記録用)とcpu.hand_strength(eval7連携用)の両方が参照する共有ヘルパー。

rank.value/suit.valueの文字集合(A,K,Q,J,T,9-2 × c,d,h,s)はeval7.Card()が受け付ける
コンパクト表記と同一(verify_eval7_compat.pyで実機確認済み)なので、変換なしで
eval7.Card(card_to_str(card))にそのまま渡せる。
"""

from pokerkit import Card


def card_to_str(card: Card) -> str:
    """例: Jack of spades -> 'Js'。"""
    return f"{card.rank.value}{card.suit.value}"
