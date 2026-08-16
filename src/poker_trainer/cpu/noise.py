"""noiseパラメータの実装: 「戦略ロジック」と「合法手集合上の一様分布」の線形補間
(REQUIREMENTS.md 検討事項3)。

「合法手上の一様分布」は、まず合法なアクション*種別*(fold/check_or_call/bet_or_raise)を
一様に選び、bet_or_raiseが選ばれた場合のみ金額を[min,max]から一様に選ぶ、という
2段階サンプリングとして定義する。金額が連続量であるraiseを先に離散化してから一様に
選ぶような方式は取らない---種別→(必要なら)金額、という2段階にすることで、常に合法
(検討事項3)かつ「raiseの金額空間が広いからraiseが選ばれやすくなる」偏りを避ける。

bluff_frequency(戦略の一部、noise=0%でも発生する意図的なブラフ)とnoise(戦略を
放棄した完全ランダム)は別概念であり、rule_based.py側で明確に区別して扱う。
"""

import random

from poker_trainer.core.actions import Action
from poker_trainer.core.state import LegalActions


def uniform_legal_action(legal: LegalActions, rng: random.Random) -> Action:
    """legal_actionsの範囲内で一様ランダムな行動を1つ返す。常に合法(検討事項3)。"""
    choices: list[str] = []
    if legal.can_fold:
        choices.append("fold")
    if legal.can_check_or_call:
        choices.append("check_or_call")
    if legal.can_bet_or_raise:
        choices.append("bet_or_raise")
    if not choices:
        raise ValueError("no legal action available")  # 理論上起きないはず(pokerkit側の不変条件)

    choice = rng.choice(choices)
    if choice == "fold":
        return Action.fold()
    if choice == "check_or_call":
        return Action.check_or_call()

    assert legal.min_bet_or_raise_to is not None
    assert legal.max_bet_or_raise_to is not None
    amount = rng.randint(legal.min_bet_or_raise_to, legal.max_bet_or_raise_to)
    return Action.bet_or_raise_to(amount)
