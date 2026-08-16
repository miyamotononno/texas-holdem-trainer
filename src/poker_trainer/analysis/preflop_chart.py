"""REQUIREMENTS.md 2.2の「公開されているGTOチャート等を参考データとして保持」に対応する、
簡易的なRFI%(Raise First In)の参考値。cpu/chen.pyのChenパーセンタイル(CPUの意思決定ロジック用)
とは別物で、人間向けの解説専用の粗い目安値(CFR等の厳密なソルバーはスコープ外、REQUIREMENTS.md §3)。
数値は一般に公開されているポジション別オープンレンジの目安であり、正確なGTO解ではない。
"""

RFI_PERCENT_BY_POSITION: dict[str, float] = {
    "UTG": 15.0,
    "UTG+1": 17.0,
    "MP": 18.0,
    "HJ": 20.0,
    "CO": 25.0,
    "BTN": 40.0,
    "SB": 35.0,
}


def recommended_preflop_action(position: str, chen_percentile: float) -> str:
    """position_label()の出力とcpu.chen.chen_percentile_from_cardsの結果(0.0=最強〜1.0=最弱)
    から、「このポジションなら上位X%以内なのでオープン推奨/非推奨」という参考コメントを返す。
    BBはRFIの対象外(オープンではなく応答側)のため専用メッセージを返す。
    """
    if position == "BB":
        return "BBはオープンレイズの対象外の席です(相手のアクションに応じて判断します)。"

    rfi_percent = RFI_PERCENT_BY_POSITION.get(position)
    if rfi_percent is None:
        return f"「{position}」に対応する参考データがありません。"

    hand_percentile_percent = chen_percentile * 100.0
    if hand_percentile_percent <= rfi_percent:
        return (
            f"{position}の一般的なオープンレンジ(上位約{rfi_percent:.0f}%)の目安内に入っています"
            f"(このハンドは上位約{hand_percentile_percent:.0f}%相当)。"
        )
    return (
        f"{position}の一般的なオープンレンジ(上位約{rfi_percent:.0f}%)の目安からは外れています"
        f"(このハンドは上位約{hand_percentile_percent:.0f}%相当)。"
    )
