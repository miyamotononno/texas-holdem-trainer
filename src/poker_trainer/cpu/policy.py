"""CPU席の意思決定を「入力=ゲーム状態、出力=Action」という共通インターフェースの
背後に隠す層。フェーズ1ではRuleBasedPlayer(レンジ表・ポットオッズによる決定的ロジック)
のみを実装し、フェーズ2でAgentPlayer(eval7/pokerkitをツールとして呼び出すLLMエージェント)
を追加する計画。両者ともこのCPUDecisionMakerを実装するだけでengine.apply_actionに
接続できるため、呼び出し側(将来のテーブル進行オーケストレーション)は実装の中身を
意識しなくてよい。

同じcore.seats.SeatConfigのplaystyle/noiseパラメータを、実装ごとに異なる形で
解釈する設計とする:
  - RuleBasedPlayer: playstyle/noiseを計算ロジックの分岐条件として直接使う
    (レンジ表の選択、ベットサイジング傾向、ブラフ頻度、noiseによる一様分布との
    ブレンド率など)。
  - AgentPlayer(将来): playstyle/noiseをシステムプロンプトやツール呼び出し方針の
    指示として渡す(例:「あなたはタイトアグレッシブな中級者です」)。

コスト・レイテンシの観点から、AgentPlayerは全CPU席に一律適用するのではなく、
テーブル内の一部の席だけに割り当てる「特別モード」として使う想定
(2〜8人卓の全席をエージェント化すると1ハンド・複数ストリートあたりのAPI呼び出し数が
無視できなくなるため)。どの席にどのCPUDecisionMaker実装を割り当てるかはテーブル
構築側(将来のオーケストレーション層)の責務であり、coreパッケージは関知しない。

本モジュールでは実装本体(RuleBasedPlayer/AgentPlayer)は持たず、インターフェース
(Protocol)のみを定義する。レンジ表・ベットサイジング数値・ツール定義は
REQUIREMENTS.md 5章の持ち越し事項として別フェーズで設計する。
"""

from typing import Protocol, runtime_checkable

from poker_trainer.core.actions import Action
from poker_trainer.core.state import HandState, LegalActions


@runtime_checkable
class CPUDecisionMaker(Protocol):
    """CPU席の意思決定エンジンの共通インターフェース。ルールベースだろうがツール付き
    AIエージェントだろうが、呼び出し側からは区別なく扱える。"""

    def decide(
        self,
        hand_state: HandState,
        seat_index: int,
        legal_actions: LegalActions,
    ) -> Action:
        """seat_index席がこの手番で取るActionを返す。

        engine.apply_actionは呼び出し元の実装を問わず常にget_legal_actionsで
        合法性を再検証するため(REQUIREMENTS.md 検討事項3)、この実装は
        「ゲームとして正しい範囲で何を選ぶか」という判断の質にだけ集中してよく、
        合法性を自前で完全に保証する責任までは負わない(二重の安全網)。
        """
        ...
