"""プレイスタイル別の数値パラメータ。REQUIREMENTS.mdのVPIP/PFRアンカーを目安に設定した
v1デフォルト値(要調整、暫定値)。Chenパーセンタイルは169正準ハンドを等確率で並べた順位であり、
実際のコンボ頻度(ペア6コンボ/スーテッド4コンボ/オフスーツ12コンボ)による重み付けVPIP%とは
厳密には一致しない近似であることに注意(scripts/verify_rule_based_cpu.pyで実測VPIPを見て
チューニングする前提)。
"""

from dataclasses import dataclass

from poker_trainer.core.seats import PlaystyleType
from poker_trainer.cpu.hand_strength import HandTier


@dataclass(frozen=True)
class PlaystyleProfile:
    # --- プリフロップ(Chenパーセンタイル基準。値が小さいほど強いハンドのみ許容) ---
    open_percentile: float  # VPIP相当。未レイズ時、これ以下ならプレイ
    open_raise_percentile: float  # PFR相当。open_percentile以下の部分集合。
    # これ以下ならオープンレイズ、超過~open未満はリンプ/コール
    facing_raise_continue_percentile: float  # レイズに直面。これ以下ならプレイ続行(コール/3ベット)
    facing_raise_3bet_percentile: float  # continue以下の部分集合。これ以下なら3ベット

    # --- ポストフロップ(HandTier基準。相手レンジは見ない) ---
    equity_margin: float  # 必要エクイティへの安全マージン(+保守的、-緩い=オッズ度外視)
    value_bet_min_tier: HandTier  # 自分からベットする最低tier
    raise_min_tier: HandTier  # 相手のベットに対しレイズ(コールでなく)する最低tier
    bluff_frequency: float  # NOTHING/WEAK_PAIRでもベット/レイズを選ぶ確率(0.0-1.0)


PLAYSTYLE_PROFILES: dict[PlaystyleType, PlaystyleProfile] = {
    # VPIP~18-22%, PFR≈VPIP(openした大半をレイズ)
    PlaystyleType.TAG: PlaystyleProfile(
        open_percentile=0.20,
        open_raise_percentile=0.18,
        facing_raise_continue_percentile=0.10,
        facing_raise_3bet_percentile=0.04,
        equity_margin=0.03,
        value_bet_min_tier=HandTier.STRONG_PAIR,
        raise_min_tier=HandTier.TWO_PAIR_PLUS,
        bluff_frequency=0.12,
    ),
    # VPIP~28%, PFR~24%, 広いレンジをアグレッシブに
    PlaystyleType.LAG: PlaystyleProfile(
        open_percentile=0.32,
        open_raise_percentile=0.28,
        facing_raise_continue_percentile=0.22,
        facing_raise_3bet_percentile=0.12,
        equity_margin=-0.02,
        value_bet_min_tier=HandTier.WEAK_PAIR,
        raise_min_tier=HandTier.STRONG_PAIR,
        bluff_frequency=0.30,
    ),
    # VPIP~13%, PFR~5-8%(タイトなレンジをパッシブに、リンプ/コール多め)
    PlaystyleType.NIT: PlaystyleProfile(
        open_percentile=0.13,
        open_raise_percentile=0.06,
        facing_raise_continue_percentile=0.05,
        facing_raise_3bet_percentile=0.02,
        equity_margin=0.08,
        value_bet_min_tier=HandTier.TWO_PAIR_PLUS,
        raise_min_tier=HandTier.NUTTED,
        bluff_frequency=0.03,
    ),
    # VPIP~35%+, PFR~3-5%(ほぼ常にコール、レイズはほぼしない)
    PlaystyleType.CALLING_STATION: PlaystyleProfile(
        open_percentile=0.38,
        open_raise_percentile=0.05,
        facing_raise_continue_percentile=0.35,
        facing_raise_3bet_percentile=0.01,
        equity_margin=-0.10,
        value_bet_min_tier=HandTier.NUTTED,
        raise_min_tier=HandTier.NUTTED,
        bluff_frequency=0.01,
    ),
}


def multiway_tightening_factor(live_opponent_count: int) -> float:
    """REQUIREMENTS.md 検討事項2: 「対戦相手1人増加ごとに閾値を線形にタイト化」の簡易近似。
    ヘッズアップ(live_opponent_count=1)を係数1.0とし、相手1人増加ごとに8%割り引く。
    下限0.4でクランプ(8人卓で相手7人でも極端に潰れすぎないように)。"""
    extra_opponents = max(live_opponent_count - 1, 0)
    return max(1.0 - 0.08 * extra_opponents, 0.4)
