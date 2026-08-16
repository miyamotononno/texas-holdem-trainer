"""Streamlitエントリーポイント。実行: streamlit run src/poker_trainer/ui/app.py

ゲーム進行ロジック(GameSession)はStreamlitに依存しないui/game_session.pyに、
表示用フォーマットはui/render.pyに分離してあり、このファイルはst.*呼び出しと
それらの配線に専念する(REQUIREMENTS.md 4.3 検討事項6の方針)。
"""

import streamlit as st

from poker_trainer.core.actions import Action
from poker_trainer.core.cards import card_to_str
from poker_trainer.core.engine import get_legal_actions, is_hand_complete
from poker_trainer.core.seats import PlaystyleType
from poker_trainer.cpu.rule_based import RuleBasedPlayer
from poker_trainer.ui.game_session import GameSession, Participant
from poker_trainer.ui.render import (
    format_action_record,
    format_card,
    format_cards,
    format_chips,
    split_hole_cards,
)

STYLE_ROTATION = [
    PlaystyleType.TAG,
    PlaystyleType.LAG,
    PlaystyleType.NIT,
    PlaystyleType.CALLING_STATION,
]

st.set_page_config(page_title="Texas Hold'em Trainer", layout="wide")
st.title("🃏 Texas Hold'em Trainer")


def render_setup_form() -> None:
    st.sidebar.header("卓の設定")
    num_opponents = st.sidebar.slider("CPU人数", min_value=1, max_value=7, value=3)
    small_blind = st.sidebar.number_input("スモールブラインド", min_value=1, value=1, step=1)
    big_blind = st.sidebar.number_input(
        "ビッグブラインド", min_value=small_blind + 1, value=max(2, small_blind + 1), step=1
    )
    starting_stack = st.sidebar.number_input(
        "開始スタック", min_value=big_blind * 10, value=big_blind * 100, step=big_blind
    )
    noise = st.sidebar.slider("CPUのnoise(一貫性の低さ, %)", min_value=0, max_value=100, value=15)

    if st.sidebar.button("卓を開始", type="primary"):
        participants = [Participant("あなた", True, None, None)]
        for i in range(num_opponents):
            style = STYLE_ROTATION[i % len(STYLE_ROTATION)]
            participants.append(
                Participant(f"CPU-{style.value}-{i + 1}", False, style, float(noise))
            )
        session = GameSession.new(
            participants=tuple(participants),
            small_blind=int(small_blind),
            big_blind=int(big_blind),
            starting_stack=int(starting_stack),
            cpu_policy=RuleBasedPlayer(),
        )
        session.start_new_hand()
        st.session_state.session = session
        st.rerun()

    st.info("左のサイドバーで卓を設定し、「卓を開始」を押してください。")


def render_seats(session: GameSession) -> None:
    hand_state = session.hand_state
    assert hand_state is not None
    state = hand_state.pokerkit_state
    hand_complete = is_hand_complete(hand_state)

    cols = st.columns(len(hand_state.seats))
    for seat in hand_state.seats:
        with cols[seat.seat_index]:
            is_actor = (not hand_complete) and state.actor_index == seat.seat_index
            folded = not state.statuses[seat.seat_index]
            marker = "👉 " if is_actor else ("❌ " if folded else "🟢 ")
            label = seat.display_name + ("(あなた)" if seat.is_human else "")
            st.markdown(f"{marker}**{label}**")
            st.caption(f"スタック: {format_chips(state.stacks[seat.seat_index])}")
            if seat.playstyle is not None:
                st.caption(f"スタイル: {seat.playstyle.value} (noise={seat.noise:.0f}%)")


def render_human_actions(session: GameSession) -> None:
    hand_state = session.hand_state
    assert hand_state is not None
    legal = get_legal_actions(hand_state)
    turn_key = len(hand_state.action_log)

    st.markdown("### あなたの番です")
    cols = st.columns(3)

    if cols[0].button("フォールド", disabled=not legal.can_fold, key=f"fold_{turn_key}"):
        session.submit_human_action(Action.fold())
        session.finalize_hand_if_complete()
        st.rerun()

    call_label = "チェック" if legal.check_or_call_amount == 0 else f"コール ({legal.check_or_call_amount})"
    if cols[1].button(call_label, disabled=not legal.can_check_or_call, key=f"call_{turn_key}"):
        session.submit_human_action(Action.check_or_call())
        session.finalize_hand_if_complete()
        st.rerun()

    with cols[2]:
        if legal.can_bet_or_raise:
            amount = st.number_input(
                "ベット/レイズ額",
                min_value=legal.min_bet_or_raise_to,
                max_value=legal.max_bet_or_raise_to,
                value=legal.min_bet_or_raise_to,
                step=1,
                key=f"amt_{turn_key}",
            )
            if st.button("ベット/レイズ", key=f"raise_{turn_key}"):
                session.submit_human_action(Action.bet_or_raise_to(int(amount)))
                session.finalize_hand_if_complete()
                st.rerun()
        else:
            st.caption("ベット/レイズ不可(オールイン等)")


def render_hand_result(session: GameSession) -> None:
    result = session.last_hand_result
    hand_state = session.hand_state
    assert result is not None and hand_state is not None

    st.markdown("### ハンド結果")
    for outcome in result.seat_outcomes:
        seat = next(s for s in hand_state.seats if s.seat_index == outcome.seat_index)
        cards_html = format_cards(split_hole_cards(outcome.hole_cards))
        sign = "+" if outcome.net_result >= 0 else ""
        st.markdown(
            f"**{seat.display_name}**: {cards_html} &nbsp; {sign}{outcome.net_result}チップ"
            + ("(ショーダウン)" if outcome.showed_down else ""),
            unsafe_allow_html=True,
        )

    if session.active_participant_count() < 2:
        st.warning("参加者が2人未満になったため、セッションを終了します。")
        if st.button("新しいセッションを開始"):
            del st.session_state["session"]
            st.rerun()
    else:
        if st.button("次のハンドへ", type="primary"):
            session.start_new_hand()
            st.rerun()


def render_table(session: GameSession) -> None:
    hand_state = session.hand_state
    assert hand_state is not None
    state = hand_state.pokerkit_state

    st.subheader(f"ハンド #{session.hand_number}")
    board_cards = tuple(card_to_str(c) for group in state.board_cards for c in group)
    st.markdown(
        f"**ボード**: {format_cards(board_cards)} &nbsp;&nbsp; "
        f"**ポット**: {format_chips(state.total_pot_amount)}",
        unsafe_allow_html=True,
    )

    render_seats(session)

    with st.expander("アクションログ", expanded=True):
        if not hand_state.action_log:
            st.caption("(まだアクションがありません)")
        for record in hand_state.action_log:
            seat_name = next(
                s.display_name for s in hand_state.seats if s.seat_index == record.seat_index
            )
            st.text(format_action_record(record, seat_name))

    st.divider()
    if session.last_hand_result is not None:
        render_hand_result(session)
    elif session.is_awaiting_human_action():
        render_human_actions(session)


def main() -> None:
    if "session" not in st.session_state:
        render_setup_form()
        return

    session: GameSession = st.session_state.session
    st.sidebar.button(
        "セッションをリセット", on_click=lambda: st.session_state.pop("session", None)
    )
    render_table(session)


main()
