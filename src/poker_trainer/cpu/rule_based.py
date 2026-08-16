"""フェーズ1のCPUDecisionMaker実装。playstyle/noiseを計算ロジックの分岐条件として
直接解釈する(cpu/policy.pyのドキュメントどおり)。相手のレンジは一切モデル化せず、
自分のハンド(プリフロップ: Chenパーセンタイル、ポストフロップ: HandTier)とポットオッズ
だけで意思決定する、意図的に単純化されたルールベースボット(REQUIREMENTS.md §3、
CFR等の本格的なGTO算出はスコープ外)。
"""

import random

from poker_trainer.core.actions import Action, ActionType
from poker_trainer.core.history import Street
from poker_trainer.core.seats import SeatConfig
from poker_trainer.core.state import HandState, LegalActions
from poker_trainer.cpu.chen import chen_percentile_from_cards
from poker_trainer.cpu.hand_strength import TIER_ASSUMED_EQUITY, HandTier, classify_hand_strength
from poker_trainer.cpu.noise import uniform_legal_action
from poker_trainer.cpu.profiles import PLAYSTYLE_PROFILES, PlaystyleProfile, multiway_tightening_factor
from poker_trainer.cpu.sizing import (
    BetIntent,
    POT_PERCENT_TABLE,
    pot_percent_to_amount,
    preflop_3bet_amount,
    preflop_open_amount,
    street_category,
)


MAX_RAISES_PER_STREET = 4
"""1ストリートあたりの最大レイズ応酬回数。ノーリミットでは理論上無制限にレイズし合える
が、両者のtier/パーセンタイル閾値が偶然噛み合うと最小レイズの応酬が延々と続く実例を
実機テストで確認した(check_or_call_amountは直前の増分でしかなく、大きく育ったベット
総額を反映しないため、閾値ベースの判定だけでは収束しない)。伝統的なリミットポーカーの
「ベット、レイズ、リレイズ、キャップ」という4段階の慣習を借用し、上限に達したら
レイズではなくコール/フォールドにフォールバックさせることで収束を保証する。"""


class RuleBasedPlayer:
    """CPUDecisionMakerを構造的に満たす(decide(hand_state, seat_index, legal_actions) -> Action)。"""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng if rng is not None else random.Random()

    def decide(self, hand_state: HandState, seat_index: int, legal_actions: LegalActions) -> Action:
        seat = _seat_config(hand_state, seat_index)
        assert seat.playstyle is not None, "RuleBasedPlayer requires a CPU seat with a playstyle"
        profile = PLAYSTYLE_PROFILES[seat.playstyle]
        noise = seat.noise or 0.0

        if self._rng.random() < noise / 100.0:
            return uniform_legal_action(legal_actions, self._rng)

        tighten = multiway_tightening_factor(_count_live_opponents(hand_state, seat_index))
        street = Street(hand_state.pokerkit_state.street_index)

        if street is Street.PREFLOP:
            return self._decide_preflop(hand_state, seat_index, legal_actions, seat, profile, tighten)
        return self._decide_postflop(hand_state, seat_index, legal_actions, seat, profile, tighten)

    def _decide_preflop(
        self,
        hand_state: HandState,
        seat_index: int,
        legal: LegalActions,
        seat: SeatConfig,
        profile: PlaystyleProfile,
        tighten: float,
    ) -> Action:
        hole = hand_state.pokerkit_state.hole_cards[seat_index]
        percentile = chen_percentile_from_cards(hole[0], hole[1])
        # legal.check_or_call_amountは「直前のレイズからの増分」であり、両者が
        # 最小レイズを繰り返すレイズ合戦では常に小さい値のままになるため、
        # big_blindとの比較では検出できない(実機テストで無限レイズ合戦を確認済み)。
        # 「このストリートで既にレイズが発生したか」をaction_logから判定する。
        raise_count = _raise_count_on_street(hand_state, Street.PREFLOP)
        facing_raise = raise_count > 0

        if facing_raise:
            continue_cut = profile.facing_raise_continue_percentile * tighten
            threebet_cut = profile.facing_raise_3bet_percentile * tighten
            if percentile > continue_cut:
                return Action.fold() if legal.can_fold else Action.check_or_call()
            if (
                percentile <= threebet_cut
                and legal.can_bet_or_raise
                and raise_count < MAX_RAISES_PER_STREET
            ):
                amount = preflop_3bet_amount(hand_state, legal, seat.playstyle)
                return Action.bet_or_raise_to(amount)
            return Action.check_or_call()

        open_cut = profile.open_percentile * tighten
        raise_cut = profile.open_raise_percentile * tighten
        if percentile > open_cut:
            if legal.can_check_or_call and legal.check_or_call_amount == 0:
                return Action.check_or_call()  # 無料でチェックできるなら降りる必要はない(例: BBオプション)
            return Action.fold() if legal.can_fold else Action.check_or_call()
        if percentile <= raise_cut and legal.can_bet_or_raise:
            amount = preflop_open_amount(hand_state, legal, seat.playstyle)
            return Action.bet_or_raise_to(amount)
        return Action.check_or_call()  # リンプ/コール

    def _decide_postflop(
        self,
        hand_state: HandState,
        seat_index: int,
        legal: LegalActions,
        seat: SeatConfig,
        profile: PlaystyleProfile,
        tighten: float,
    ) -> Action:
        state = hand_state.pokerkit_state
        hole = tuple(state.hole_cards[seat_index])
        board = tuple(c for group in state.board_cards for c in group)
        tier = classify_hand_strength(hole, board)
        effective_bluff_freq = profile.bluff_frequency * tighten
        category = street_category(hand_state)
        street = Street(state.street_index)
        raise_count = _raise_count_on_street(hand_state, street)
        can_raise = legal.can_bet_or_raise and raise_count < MAX_RAISES_PER_STREET

        if legal.check_or_call_amount > 0:  # 相手のベットに直面
            required_equity = legal.check_or_call_amount / (
                state.total_pot_amount + legal.check_or_call_amount
            )
            if TIER_ASSUMED_EQUITY[tier] + profile.equity_margin >= required_equity:
                if tier >= profile.raise_min_tier and can_raise:
                    intent = (
                        BetIntent.VALUE_STRONG if tier >= HandTier.TWO_PAIR_PLUS else BetIntent.VALUE_THIN
                    )
                    pot_pct = POT_PERCENT_TABLE[category][intent][seat.playstyle]
                    return Action.bet_or_raise_to(pot_percent_to_amount(pot_pct, hand_state, legal))
                return Action.check_or_call()
            if self._rng.random() < effective_bluff_freq and can_raise:
                pot_pct = POT_PERCENT_TABLE[category][BetIntent.BLUFF][seat.playstyle]
                return Action.bet_or_raise_to(pot_percent_to_amount(pot_pct, hand_state, legal))
            return Action.fold() if legal.can_fold else Action.check_or_call()

        # 自分がベットかチェックかを選べる
        if tier >= profile.value_bet_min_tier and legal.can_bet_or_raise:
            intent = BetIntent.VALUE_STRONG if tier >= HandTier.TWO_PAIR_PLUS else BetIntent.VALUE_THIN
            pot_pct = POT_PERCENT_TABLE[category][intent][seat.playstyle]
            return Action.bet_or_raise_to(pot_percent_to_amount(pot_pct, hand_state, legal))
        if self._rng.random() < effective_bluff_freq and legal.can_bet_or_raise:
            intent = BetIntent.BLOCK if tier is HandTier.WEAK_PAIR else BetIntent.BLUFF
            pot_pct = POT_PERCENT_TABLE[category][intent][seat.playstyle]
            return Action.bet_or_raise_to(pot_percent_to_amount(pot_pct, hand_state, legal))
        return Action.check_or_call()


def _seat_config(hand_state: HandState, seat_index: int) -> SeatConfig:
    return next(s for s in hand_state.seats if s.seat_index == seat_index)


def _count_live_opponents(hand_state: HandState, seat_index: int) -> int:
    statuses = hand_state.pokerkit_state.statuses
    return sum(1 for i, alive in enumerate(statuses) if alive and i != seat_index)


def _raise_count_on_street(hand_state: HandState, street: Street) -> int:
    return sum(
        1
        for record in hand_state.action_log
        if record.street is street and record.action_type is ActionType.BET_OR_RAISE_TO
    )
