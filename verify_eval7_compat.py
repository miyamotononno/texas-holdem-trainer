"""
eval7 (と treys) の動作検証スクリプト。

要件定義書の検討事項「7. eval7ライブラリの保守状況」に対する検証(スパイク)。
eval7 の README は Python 3.5〜3.8 での動作確認のみを謳っており、
本プロジェクトで使う想定の Python バージョンで実際に

  1. インポートできるか(ビルド済みwheelがあるか)
  2. ハンド評価ができるか
  3. レンジ文字列のパースができるか
  4. モンテカルロ法によるエクイティ計算ができるか(2.2の分析機能の要)

を確認する。失敗した場合は treys へのフォールバックも合わせて確認する。

使い方:
    python -m venv .venv-spike
    ./.venv-spike/Scripts/pip install eval7 treys
    ./.venv-spike/Scripts/python verify_eval7_compat.py
"""

import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def check_python_version() -> None:
    print(f"Python version: {sys.version}")
    major, minor = sys.version_info[:2]
    if (major, minor) > (3, 8):
        print(
            f"  [NOTE] eval7 の README 記載の動作確認範囲は Python 3.5-3.8 です。"
            f" 実行中の {major}.{minor} は範囲外のため、below の実動作確認結果を優先してください。\n"
        )
    else:
        print("  [NOTE] README記載の動作確認範囲内です。\n")


def check_eval7() -> bool:
    print("=== eval7 ===")
    try:
        import eval7
    except ImportError as e:
        print(f"  [FAIL] import失敗: {e}")
        print("  → pip install eval7 でビルド済みwheelが提供されていないバージョンの可能性があります。")
        return False

    ok = True

    # 1. ハンド評価
    try:
        hand = [eval7.Card(c) for c in ["As", "Ks", "Qs", "Js", "Ts"]]
        score = eval7.evaluate(hand)
        print(f"  [OK] hand evaluation: royal flush -> score={score}, type={eval7.handtype(score)}")
    except Exception as e:
        print(f"  [FAIL] hand evaluation でエラー: {e}")
        ok = False

    # 2. レンジ文字列のパース(PokerStove形式)
    try:
        r = eval7.HandRange("22+, AKs, AKo")
        print(f"  [OK] range parsing: '22+, AKs, AKo' -> {len(r.hands)} combos")
    except Exception as e:
        print(f"  [FAIL] range parsing でエラー: {e}")
        ok = False

    # 3. モンテカルロ法によるハンド vs レンジ エクイティ計算(プリフロップ)
    try:
        hero_hand = [eval7.Card("Ah"), eval7.Card("Kh")]
        villain_range = eval7.HandRange("QQ+")
        equity = eval7.py_hand_vs_range_monte_carlo(hero_hand, villain_range, [], 20000)
        print(f"  [OK] preflop equity (AKs vs QQ+): {equity:.1%} (目安: 約33-35%であれば妥当)")
    except Exception as e:
        print(f"  [FAIL] preflop equity計算でエラー: {e}")
        ok = False

    # 4. モンテカルロ法によるハンド vs レンジ エクイティ計算(フロップ後)
    try:
        hero_hand = [eval7.Card("Ah"), eval7.Card("Kh")]
        villain_range = eval7.HandRange("QQ+")
        board = [eval7.Card("Kd"), eval7.Card("7c"), eval7.Card("2h")]
        equity = eval7.py_hand_vs_range_monte_carlo(hero_hand, villain_range, board, 20000)
        print(f"  [OK] flop equity (AK top pair vs QQ+ on K72r): {equity:.1%} (目安: 約55-65%であれば妥当)")
    except Exception as e:
        print(f"  [FAIL] flop equity計算でエラー: {e}")
        ok = False

    return ok


def check_treys_fallback() -> bool:
    print("\n=== treys (フォールバック候補) ===")
    try:
        from treys import Card, Evaluator
    except ImportError as e:
        print(f"  [FAIL] import失敗: {e}")
        return False

    try:
        evaluator = Evaluator()
        hand = [Card.new("Ah"), Card.new("Kh")]
        board = [Card.new("Qh"), Card.new("Jh"), Card.new("Th")]
        score = evaluator.evaluate(board, hand)
        rank_class = evaluator.get_rank_class(score)
        print(
            f"  [OK] hand evaluation: royal flush -> score={score} (低いほど強い), "
            f"type={evaluator.class_to_string(rank_class)}"
        )
        print("  [NOTE] treysはレンジパーサ・エクイティ計算を標準搭載していないため、")
        print("         採用する場合はレンジ展開とモンテカルロ計算を自前実装する必要がある。")
        return True
    except Exception as e:
        print(f"  [FAIL] hand evaluation でエラー: {e}")
        return False


def main() -> None:
    check_python_version()
    eval7_ok = check_eval7()
    treys_ok = check_treys_fallback()

    print("\n=== 結論 ===")
    if eval7_ok:
        print("[RECOMMEND] eval7 は現在の環境で問題なく動作しています。要件通りeval7を採用可能です。")
    elif treys_ok:
        print("[RECOMMEND] eval7 が動作しないため、treys をハンド評価に採用し、")
        print("            レンジパース・エクイティ計算(モンテカルロ)は自前実装するフォールバック方針を推奨します。")
    else:
        print("[WARNING] eval7 / treys のいずれも動作確認できませんでした。環境を確認してください。")


if __name__ == "__main__":
    main()
