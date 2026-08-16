"""席のメタデータ。プレイスタイル(TAG/LAG/nit/calling station)とnoiseは、
どのCPUDecisionMaker実装がその席を操作するかによって解釈のされ方が変わる
(cpu.policy参照): RuleBasedPlayerにとっては計算ロジックの分岐条件、将来の
AgentPlayerにとってはシステムプロンプト/ツール呼び出し方針の指示になる。
どの席にどのCPUDecisionMaker実装を割り当てるかはテーブル構築側(将来のオーケストレーション層)
の責務であり、SeatConfigはその割り当て情報を持たない(core はcpuパッケージに依存しない)。
"""

from dataclasses import dataclass
from enum import Enum


class PlaystyleType(str, Enum):
    """初期実装の4タイプ(tight/loose × aggressive/passive)。各タイプが持つレンジ表・
    サイジング傾向・ブラフ頻度といった実際のパラメータ値の設計は本レイヤーのスコープ外。"""

    TAG = "tag"
    LAG = "lag"
    NIT = "nit"
    CALLING_STATION = "calling_station"


@dataclass(frozen=True)
class SeatConfig:
    seat_index: int
    display_name: str
    is_human: bool
    playstyle: PlaystyleType | None  # 人間席はNone
    noise: float | None  # 0.0-100.0。人間席はNone
