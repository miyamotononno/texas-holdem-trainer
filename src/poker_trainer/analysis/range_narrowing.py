"""REQUIREMENTS.md 検討事項4の実装: ポストフロップのエクイティ計算で使う相手のレンジを、
「相手の実際の隠しハンド」でも「完全ランダム」でもなく、「プレイスタイル別レンジ表 ×
実際に取ったプリフロップアクション」で絞り込んで求める。

cpu/profiles.pyの各プレイスタイルの閾値(cpu/chen.pyのChenパーセンタイル基準)を再利用し、
該当パーセンタイル以下(または以上)の正準ハンドをeval7.HandRangeが解釈できる
カンマ区切り文字列として組み立てる。

v1はプリフロップのアクションのみでレンジを絞り込む。ポストフロップの各アクション
(ベット/チェック等)によるさらなる絞り込みは将来拡張とする(このモジュールの責務外)。
"""

from typing import Literal

from poker_trainer.core.seats import PlaystyleType
from poker_trainer.cpu.chen import CHEN_PERCENTILE
from poker_trainer.cpu.profiles import PLAYSTYLE_PROFILES

PreflopAction = Literal["raised", "called", "folded"]


def _hands_at_or_below(cutoff: float) -> list[str]:
    return [hand for hand, percentile in CHEN_PERCENTILE.items() if percentile <= cutoff]


def _hands_above(cutoff: float) -> list[str]:
    return [hand for hand, percentile in CHEN_PERCENTILE.items() if percentile > cutoff]


def narrow_range_by_actions(
    playstyle: PlaystyleType,
    preflop_action: PreflopAction,
    facing_raise: bool,
) -> str:
    """プレイスタイルと実際に取ったプリフロップアクションから、eval7.HandRangeが
    パースできるレンジ文字列("22+,AKs,..."形式)を返す。"""
    profile = PLAYSTYLE_PROFILES[playstyle]

    if preflop_action == "raised":
        cutoff = profile.facing_raise_3bet_percentile if facing_raise else profile.open_raise_percentile
        hands = _hands_at_or_below(cutoff)
    elif preflop_action == "called":
        cutoff = profile.facing_raise_continue_percentile if facing_raise else profile.open_percentile
        hands = _hands_at_or_below(cutoff)
    elif preflop_action == "folded":
        cutoff = profile.facing_raise_continue_percentile if facing_raise else profile.open_percentile
        hands = _hands_above(cutoff)
    else:
        raise ValueError(f"unknown preflop_action: {preflop_action}")

    return ",".join(hands)
