"""Claude tool-use分析機能のオーケストレーター本体(anthropicに依存)。

analysis/tools.pyのプレーンな関数を@beta_tool化してclient.beta.messages.tool_runnerに
渡す。固定的な計算パイプラインにはせず、Claude自身がハンドの分析に必要な計算
(エクイティ・ポットオッズ・レンジ絞り込み等)をどの順で呼ぶか判断する
(REQUIREMENTS.md 4.2のエージェント的構成の方針)。
"""

import anthropic
from anthropic import beta_tool

from poker_trainer.analysis import tools as _tools
from poker_trainer.core.actions import ActionType
from poker_trainer.core.history import ActionRecord
from poker_trainer.records.schema import HandRecord

DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = """あなたはテキサスホールデムの分析コーチです。与えられた1ハンドの
記録(あなたのホールカード・全プレイヤーのアクション履歴・ボード・結果)を読み、
「あなた」の各ストリートでの判断が妥当だったかを分析してください。

判断根拠は必ずツール呼び出しによる数値計算に基づかせてください(勘や一般論だけで
判定しないこと)。どのツールをどの順で使うかはあなた自身で判断してください
- 例えばプリフロップならハンドの強さとポジション別の目安を、ポストフロップなら
相手の推定レンジに対するエクイティとポットオッズを比較する、といった具合です。
相手の推定レンジが必要な場合は、実際の隠しハンドを覗くのではなく
narrow_opponent_rangeツールでプレイスタイルと実際のアクションから推定してください。

分析結果は、各ストリートごとに「妥当だったか」「その根拠となった数値」を示しながら、
日本語で簡潔に解説してください。"""


@beta_tool
def calculate_equity(hero_hand: str, villain_range: str, board: str = "") -> dict:
    """Calculate a hero hand's Monte Carlo equity against a villain's range.

    Args:
        hero_hand: Hero's two hole cards as a 4-character string, e.g. "AhKs".
        villain_range: An eval7-style range string, e.g. "22+,AKs,AQo+". Use
            narrow_opponent_range to derive a realistic range for a specific
            opponent rather than guessing one.
        board: Community cards dealt so far, e.g. "Kd7c2h". Leave empty ("")
            for a preflop-only calculation.
    """
    return _tools.calculate_equity(hero_hand, villain_range, board)


@beta_tool
def classify_made_hand(hole_cards: str, board_cards: str) -> dict:
    """Classify the poker hand type currently made by hole cards + board cards
    (e.g. "Pair", "Two Pair", "Straight").

    Args:
        hole_cards: Two hole cards, e.g. "AhKs".
        board_cards: All board cards dealt so far, e.g. "Kd7c2h".
    """
    return _tools.classify_made_hand(hole_cards, board_cards)


@beta_tool
def calculate_pot_odds(pot: int, call_amount: int) -> dict:
    """Calculate the equity required to profitably call a bet (pot odds).

    Args:
        pot: Total pot size before the call.
        call_amount: Chips required to call. 0 means checking is free (no
            equity required).
    """
    return _tools.calculate_pot_odds(pot, call_amount)


@beta_tool
def calculate_hand_percentile(hole_cards: str) -> dict:
    """Rank a preflop starting hand's strength using the Chen Formula, where
    0.0 is the strongest possible hand (AA) and 1.0 is the weakest (72o).

    Args:
        hole_cards: Two hole cards, e.g. "AhKs".
    """
    return _tools.calculate_hand_percentile(hole_cards)


@beta_tool
def lookup_preflop_reference(position: str, chen_percentile: float) -> dict:
    """Compare a hand's Chen-formula percentile against a published,
    approximate opening-range guideline for a given table position.

    Args:
        position: One of "UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB", "BB".
        chen_percentile: The hand's percentile, from calculate_hand_percentile.
    """
    return _tools.lookup_preflop_reference(position, chen_percentile)


@beta_tool
def narrow_opponent_range(playstyle: str, preflop_action: str, facing_raise: bool) -> dict:
    """Estimate an opponent's hand range from their playstyle and the actual
    preflop action they took, WITHOUT looking at their real hidden cards.
    The returned range string can be passed directly as calculate_equity's
    villain_range argument.

    Args:
        playstyle: One of "tag", "lag", "nit", "calling_station".
        preflop_action: One of "raised", "called", "folded" - the action this
            opponent actually took preflop.
        facing_raise: Whether the opponent was responding to a raise (True) or
            opening the pot themselves (False).
    """
    return _tools.narrow_opponent_range(playstyle, preflop_action, facing_raise)


ANALYSIS_TOOLS = [
    calculate_equity,
    classify_made_hand,
    calculate_pot_odds,
    calculate_hand_percentile,
    lookup_preflop_reference,
    narrow_opponent_range,
]


def _describe_action(record: ActionRecord) -> str:
    if record.action_type is ActionType.FOLD:
        return "フォールド"
    if record.action_type is ActionType.CHECK_OR_CALL:
        return "チェック" if record.amount is None else f"コール({record.amount})"
    return f"ベット/レイズ→{record.amount}"


def build_hand_narrative(hand_record: HandRecord, human_seat_index: int) -> str:
    """HandRecordから、人間のプレイヤーが取った各ストリートでの判断を時系列で記述した
    テキスト(Claudeへの最初のユーザーメッセージ)を組み立てる。"""
    human_result = next(r for r in hand_record.results if r.seat_index == human_seat_index)

    lines = [
        f"{hand_record.num_players}人テーブルでのテキサスホールデムのハンド記録です。",
        f"ブラインド: {hand_record.small_blind}/{hand_record.big_blind}"
        + (f"(アンテ{hand_record.ante})" if hand_record.ante else ""),
        f"あなたは座席{human_seat_index}です。開始スタック: {human_result.starting_stack}",
    ]
    if human_result.hole_cards:
        lines.append(f"あなたのホールカード: {human_result.hole_cards}")

    lines.append("\n=== アクション履歴 ===")
    for record in hand_record.action_log:
        seat = next(s for s in hand_record.seats if s.seat_index == record.seat_index)
        if record.seat_index == human_seat_index:
            who = "あなた"
        else:
            style = seat.playstyle.value if seat.playstyle is not None else "?"
            who = f"{seat.display_name}({style})"
        lines.append(
            f"[{record.street.name}] {who}: {_describe_action(record)} "
            f"(行動前ポット={record.pot_before}, 行動前スタック={record.stacks_before})"
        )

    lines.append(f"\n=== ボード ===\n{' '.join(hand_record.board_cards) or '(プリフロップ終了)'}")

    lines.append("\n=== 結果 ===")
    for result in hand_record.results:
        who = "あなた" if result.seat_index == human_seat_index else result.display_name
        showdown = "あり" if result.showed_down else "なし"
        lines.append(f"{who}: 損益={result.net_result:+d}, ショーダウン={showdown}")

    lines.append(
        "\nあなたが各ストリートで取った判断について、必要な計算をツールで行いながら、"
        "妥当だったかを分析してください。"
    )
    return "\n".join(lines)


def analyze_hand(
    hand_record: HandRecord, human_seat_index: int, model: str = DEFAULT_MODEL
) -> str:
    """client.beta.messages.tool_runnerでハンドを分析させ、最終的な自然言語の
    テキスト応答を返す。ANTHROPIC_API_KEY等の資格情報はanthropic.Anthropic()が
    環境から自動解決する。"""
    client = anthropic.Anthropic()
    narrative = build_hand_narrative(hand_record, human_seat_index)

    runner = client.beta.messages.tool_runner(
        model=model,
        max_tokens=2048,
        tools=ANALYSIS_TOOLS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": narrative}],
    )

    final_text = ""
    for message in runner:
        for block in message.content:
            if block.type == "text":
                final_text = block.text
    return final_text
