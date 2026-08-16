"""座席indexからポジション名への変換。pokerkitの固定座席規約(実機確認済み、
core/engine.pyのcreate_hand参照): 2人卓ではseat0=BB/seat1=SB兼ボタン、
3人以上ではseat0=SB/seat1=BB/seat2以降=UTG,...,ボタンは最終座席。
"""

# 座席index -> ポジション名。人数(2-8)ごとに固定リストとして持つ
# (座席0から順に並べたもの。座席index i の位置名は _POSITIONS_BY_SIZE[num_players][i])。
_POSITIONS_BY_SIZE: dict[int, tuple[str, ...]] = {
    2: ("BB", "BTN"),
    3: ("SB", "BB", "BTN"),
    4: ("SB", "BB", "UTG", "BTN"),
    5: ("SB", "BB", "UTG", "CO", "BTN"),
    6: ("SB", "BB", "UTG", "MP", "CO", "BTN"),
    7: ("SB", "BB", "UTG", "UTG+1", "MP", "CO", "BTN"),
    8: ("SB", "BB", "UTG", "UTG+1", "MP", "HJ", "CO", "BTN"),
}


def position_label(seat_index: int, num_players: int) -> str:
    """座席indexとテーブル人数からポジション名("UTG"/"CO"/"BTN"/"SB"/"BB"等)を返す。"""
    if num_players not in _POSITIONS_BY_SIZE:
        raise ValueError(f"num_players must be between 2 and 8, got {num_players}")
    return _POSITIONS_BY_SIZE[num_players][seat_index]
