"""表示用の純粋関数群。Streamlit依存はなく、HTML文字列やプレーンな文字列を返すだけ。
app.py側で st.markdown(..., unsafe_allow_html=True) 等から呼び出す。
"""

from poker_trainer.core.actions import ActionType
from poker_trainer.core.history import ActionRecord

_SUIT_SYMBOL = {"c": "♣", "d": "♦", "h": "♥", "s": "♠"}
_SUIT_COLOR = {"c": "#1a1a1a", "d": "#c0392b", "h": "#c0392b", "s": "#1a1a1a"}
_RANK_DISPLAY = {"T": "10"}


def format_card(card_str: str) -> str:
    """例: "Kh" -> 赤いハートの'K♥'を表すHTML。card_strはcore.cards.card_to_strの出力形式
    (rank1文字+suit1文字、例: "Kh","Ts","2c")を想定。"""
    rank, suit = card_str[:-1], card_str[-1]
    rank_display = _RANK_DISPLAY.get(rank, rank)
    symbol = _SUIT_SYMBOL.get(suit, suit)
    color = _SUIT_COLOR.get(suit, "#1a1a1a")
    return (
        f'<span style="display:inline-block;padding:2px 8px;margin:2px;'
        f'border:1px solid #999;border-radius:6px;background:#fff;'
        f'font-weight:700;font-size:1.1em;color:{color};">{rank_display}{symbol}</span>'
    )


def format_cards(card_strs: tuple[str, ...] | list[str]) -> str:
    """複数枚のカードを横並びのHTMLにする。0枚なら「まだ配られていない」ことを示す。"""
    if not card_strs:
        return '<span style="color:#999;">-</span>'
    return "".join(format_card(c) for c in card_strs)


def format_chips(amount: int) -> str:
    return f"{amount:,}"


def split_hole_cards(hole_cards: str | None) -> tuple[str, ...]:
    """"AhKs" -> ("Ah", "Ks")。Noneまたは空文字なら空タプル(非公開)。"""
    if not hole_cards:
        return ()
    return tuple(hole_cards[i : i + 2] for i in range(0, len(hole_cards), 2))


_ACTION_LABEL = {
    ActionType.FOLD: "フォールド",
    ActionType.CHECK_OR_CALL: "チェック/コール",
    ActionType.BET_OR_RAISE_TO: "ベット/レイズ",
}


def format_action_record(record: ActionRecord, seat_display_name: str) -> str:
    label = _ACTION_LABEL[record.action_type]
    if record.action_type is ActionType.CHECK_OR_CALL:
        label = "チェック" if record.amount is None else f"コール({format_chips(record.amount)})"
    elif record.action_type is ActionType.BET_OR_RAISE_TO:
        label = f"ベット/レイズ → {format_chips(record.amount)}"
    return f"[{record.street.name}] {seat_display_name}: {label}"
