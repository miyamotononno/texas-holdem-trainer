"""analysis/orchestrator.pyをANTHROPIC_API_KEY(またはant auth loginのプロファイル)を
使って実際に検証するスクリプト。anthropicパッケージのインストールとAPI資格情報が必要。

GameSessionのシミュレーション(人間役を自動でチェック/コールさせる、既存の検証手法と
同じ流儀)で実際に1ハンドを完了させてHandRecordを作り、analyze_hand()に渡す。

実行:
    ./.venv/Scripts/python scripts/verify_analysis.py
"""

import random
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from poker_trainer.core.actions import Action
from poker_trainer.core.engine import get_legal_actions
from poker_trainer.core.seats import PlaystyleType
from poker_trainer.cpu.rule_based import RuleBasedPlayer
from poker_trainer.ui.game_session import GameSession, Participant


def build_sample_hand_record():
    """人間役を自動操作して1ハンド完了させ、HandRecordを1件作って返す。"""
    participants = (
        Participant("あなた", True, None, None),
        Participant("CPU-tag", False, PlaystyleType.TAG, 15.0),
        Participant("CPU-lag", False, PlaystyleType.LAG, 15.0),
    )
    session = GameSession.new(
        participants=participants,
        small_blind=1,
        big_blind=2,
        starting_stack=200,
        cpu_policy=RuleBasedPlayer(rng=random.Random(7)),
    )
    session.start_new_hand()

    guard = 0
    while session.last_hand_result is None:
        assert session.is_awaiting_human_action(), "想定外: 人間の手番でないのにハンドが未完了"
        legal = get_legal_actions(session.hand_state)
        action = Action.check_or_call() if legal.can_check_or_call else Action.fold()
        session.submit_human_action(action)
        session.finalize_hand_if_complete()
        guard += 1
        if guard > 20:
            raise RuntimeError("人間の手番待ちがループしている")

    assert session.session_record.hands, "HandRecordが記録されていない"
    return session.session_record.hands[-1]


def main() -> None:
    print("=== サンプルハンドを生成中 ===")
    hand_record = build_sample_hand_record()
    print(f"ハンドID: {hand_record.hand_id}, アクション数: {len(hand_record.action_log)}")
    for result in hand_record.results:
        print(f"  {result.display_name}: 損益={result.net_result:+d}")

    print("\n=== analyze_hand()を呼び出し中(Claude APIへリクエスト) ===")
    from poker_trainer.analysis.orchestrator import analyze_hand, build_hand_narrative

    print("--- 送信するハンド記録(narrative) ---")
    print(build_hand_narrative(hand_record, human_seat_index=0))

    analysis_text = analyze_hand(hand_record, human_seat_index=0)
    print("\n=== Claudeによる分析結果 ===")
    print(analysis_text)
    print("\nOK: analyze_hand()が自然言語のテキストを返した")


if __name__ == "__main__":
    main()
