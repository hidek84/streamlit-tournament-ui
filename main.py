import threading
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st
from streamlit_calendar import calendar

from models import Match, Player, SessionLocal
from utils import (
    check_if_my_event,
    convert_sqlalchemy_objects_to_df,
    generate_hash_from_uid,
    generate_time_options,
    get_login_user_uid,
    get_matches_as_cal_events,
    get_my_matches_df,
    get_my_matches_df_player1_as_me,
    get_rankings,
    get_user_image_url,
    supply_full_user_info_to_match_df,
)

if "lock" not in st.session_state:
    st.session_state["lock"] = threading.Lock()

st.set_page_config(page_title="Table Tennis Tournament", layout="wide")
st.title("🏓 Table Tennis Tournament")

# User bar - typically this would come from a login system
user_name = get_login_user_uid(st.context.cookies)
if not user_name:
    st.warning("You're not logged in.")
    st.stop()

with st.container(border=True):
    st.write(f"👤 Logged in as: {user_name}")

# Main content
target_date = date(2025, 10, 3)
days_left = target_date - date.today()
st.header(f"Group League until {target_date} ({days_left.days} Days Left)")

with st.expander("Guide"):
    st.write("Guidance here")

col_left, col_right = st.columns([0.65, 0.35])

with col_left:
    # Your opponents table
    container_your_opponents = st.container(gap="small")

    # Match scheduling calendar
    st.subheader("Match Schedule")

    if "events" not in st.session_state:
        with SessionLocal() as session:
            st.session_state["events"] = get_matches_as_cal_events(session, user_name)

    calendar_options = {
        "headerToolbar": {
            "left": "prev,next",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,listMonth",
        },
        "selectable": True,
        "editable": True,
        "initialView": "dayGridMonth",
        "slotMinTime": "09:00:00",
        "slotMaxTime": "21:00:00",
    }
    custom_css = """
        .fc-event {
            text-wrap: wrap;
        }
        .fc-event-main {
            text-wrap: wrap;
        }
    """
    with SessionLocal() as session:
        events = get_matches_as_cal_events(session, user_name)
    state = calendar(
        events=events,
        options=calendar_options,
        custom_css=custom_css,
        key="calendar",
    )

    @st.dialog("Add Event")
    def add_event(selected_date):
        selected_datetime = (
            datetime.strptime(selected_date, "%Y-%m-%dT%H:%M:%S.000Z")
            + timedelta(hours=9)
        ).isoformat()

        with SessionLocal() as session:
            my_matches_df = supply_full_user_info_to_match_df(
                session, get_my_matches_df_player1_as_me(session, user_name)
            )
            not_scheduled_matches_aligned_for_me_df = my_matches_df[
                my_matches_df["start"].isna()
            ]

        match = st.selectbox(
            "Select Opponent",
            not_scheduled_matches_aligned_for_me_df.to_dict(orient="records"),
            format_func=lambda x: x["full_name_player2"],
        )

        new_date = st.date_input("Match Date", value=pd.to_datetime(selected_datetime))
        # new_time = st.time_input(
        #     "Edit Event Time",
        #     value=pd.to_datetime(selected_datetime),
        #     step=timedelta(minutes=30),
        # )
        time_options = generate_time_options(time(9, 0), time(21, 0), 30)
        try:
            option_index = time_options.index(pd.to_datetime(selected_datetime).time())
        except ValueError:
            option_index = 0

        new_time = st.selectbox(
            "Match Time",
            index=option_index,
            options=time_options,
        )
        new_start_time = datetime.combine(new_date, new_time)
        new_end_time = new_start_time + timedelta(minutes=30)
        if st.button("Make Match"):
            new_match = {
                **match,
                **{
                    "title": f"vs {match['full_name_player2']}",
                    "start": new_start_time.isoformat(),
                    "end": new_end_time.isoformat(),
                },
            }
            with SessionLocal() as session:
                db_event = (
                    session.query(Match).filter(Match.id == new_match["id"]).first()
                )
                if not db_event:
                    st.error(f"Event with ID {new_match['id']} not found.")
                    return

                # Update the event details
                db_event.start = new_match["start"]
                db_event.end = new_match["end"]

                # Commit the changes
                session.commit()

            st.session_state["events"].append(
                {
                    "id": new_match["id"],
                    "title": new_match["title"],
                    "start": new_start_time.isoformat(),
                    "end": new_end_time.isoformat(),
                    "backgroundColor": (
                        "#ff0000"
                        if new_match["player1_uid"] == user_name
                        or new_match["player2_uid"] == user_name
                        else "#0000ff"
                    ),
                }
            )
            st.success(f"New Match added successfully")
            st.rerun()

    @st.dialog("Update Match")
    def update_event(event):
        st.write(f"Editing Match: {event['title']} on {event['start']}")
        # new_date = st.date_input(
        #     "Edit Event Date", value=pd.to_datetime(event["start"])
        # )
        time_options = generate_time_options(time(9, 0), time(21, 0), 30)
        try:
            option_index = time_options.index(pd.to_datetime(event["start"]).time())
        except ValueError:
            option_index = 0

        new_time = st.selectbox(
            "Match Time",
            index=option_index,
            options=time_options,
        )
        new_start_time = datetime.combine(pd.to_datetime(event["start"]), new_time)
        new_end_time = new_start_time + timedelta(minutes=30)

        if st.button("Save Changes"):
            # Fetch the event from the database using event ID
            event_id = event["id"]
            with SessionLocal() as session:
                db_event = session.query(Match).filter(Match.id == event_id).first()
                if not db_event:
                    st.error(f"Event with ID {event_id} not found.")
                    return

                # Update the event details
                db_event.start = new_start_time.isoformat()
                db_event.end = new_end_time.isoformat()

                # Commit the changes
                session.commit()

            # Update the event in session state (in case it's displayed again in the app)
            event_list_indices = [
                idx
                for idx, event in enumerate(st.session_state["events"])
                if event["id"] == event_id
            ]
            if not event_list_indices:
                st.error("Error: Match not found in session state.")
                return
            event_index = event_list_indices[0]
            st.session_state["events"][event_index][
                "start"
            ] = new_start_time.isoformat()
            st.session_state["events"][event_index]["end"] = new_end_time.isoformat()

            st.success("Match updated successfully!")
            st.rerun()

    if state.get("dateClick"):
        selected_date = state["dateClick"]["date"]
        with SessionLocal() as session:
            my_matches_df = get_my_matches_df_player1_as_me(session, user_name)
            not_scheduled_matches_df = my_matches_df[my_matches_df["start"].isna()]
        if len(not_scheduled_matches_df) > 0:
            add_event(selected_date)

    if state.get("eventClick"):
        event_id = state["eventClick"]["event"]["id"]
        event_list_indices = [
            idx
            for idx, event in enumerate(st.session_state["events"])
            if event["id"] == event_id
        ]
        if not event_list_indices:
            raise Exception("Error")
        event_index = event_list_indices[0]

        event = st.session_state["events"][event_index]
        if check_if_my_event(event, user_name):
            update_event(event)

    if state.get("eventChange"):
        print("event change")
        event_id = state["eventChange"]["oldEvent"]["id"]
        event_list_indices = [
            idx
            for idx, event in enumerate(st.session_state["events"])
            if event["id"] == event_id
        ]
        if not event_list_indices:
            raise Exception("Error")

        with SessionLocal() as session:
            db_event = session.query(Match).filter(Match.id == event_id).first()
            if not db_event:
                st.error(f"Event with ID {event_id} not found.")

            # Update the event details
            db_event.title = state["eventChange"]["event"]["title"]
            db_event.start = state["eventChange"]["event"]["start"]
            db_event.end = state["eventChange"]["event"]["end"]

            # Commit the changes
            session.commit()

        original_events = st.session_state["events"]
        original_events[event_list_indices[0]] = state["eventChange"]["event"]
        st.session_state["events"] = original_events
        print(st.session_state["events"][event_list_indices[0]])
        # st.rerun()

    with container_your_opponents:
        st.subheader("Your Games")
        if (
            "matches_df" not in st.session_state
        ):  # or any(x!=y for x,y in zip(st.session_state["matches_df"], st.session_state["previous_matches_df"]):
            with SessionLocal() as session:
                my_matches_df = get_my_matches_df(session, user_name)
                opponent_matches_df = supply_full_user_info_to_match_df(
                    session, my_matches_df
                )
                st.session_state["matches_df"] = opponent_matches_df.to_dict()

        # https://github.com/streamlit/streamlit/issues/11679
        def db_on_change(df):
            with st.session_state["lock"]:
                # Get a copy of all edited rows in this session
                all_edits = st.session_state["your_matches_editor"]["edited_rows"]
                for idx, changes in all_edits.items():
                    for col, col_value in changes.items():
                        with SessionLocal() as session:
                            db_event = (
                                session.query(Match)
                                .filter(Match.id == df.iloc[idx, :]["id"])
                                .first()
                            )
                            db_event.__setattr__(col, col_value)
                            session.commit()
                            df.iloc[idx, :][col] = col_value
                            st.session_state["matches_df"] = df.to_dict()

        st.data_editor(
            pd.DataFrame.from_dict(st.session_state["matches_df"]),
            hide_index=True,
            on_change=db_on_change,
            args=[pd.DataFrame.from_dict(st.session_state["matches_df"])],
            key="your_matches_editor",
            column_order=[
                "player1_image_url",
                "full_name_player1",
                "player1_score",
                "player2_score",
                "player2_image_url",
                "full_name_player2",
                "start",
            ],
            column_config={
                "full_name_player1": st.column_config.TextColumn(
                    "Player1",
                    disabled=True,
                ),
                "player1_image_url": st.column_config.ImageColumn("", width=1),
                "player1_score": st.column_config.SelectboxColumn(
                    "# of Player1 Games",
                    options=list(range(0, 4)),
                    width=1,
                ),
                "player2_score": st.column_config.SelectboxColumn(
                    "# of Player2 Games",
                    options=list(range(0, 4)),
                    width=1,
                ),
                "player2_image_url": st.column_config.ImageColumn("", width=1),
                "full_name_player2": st.column_config.TextColumn(
                    "Player2",
                    disabled=True,
                ),
                "start": st.column_config.DatetimeColumn(
                    "Match Date/Time",
                    format="MMM D (ddd) h:mm a",
                    step=60 * 30,
                    disabled=True,
                ),
            },
        )

with col_right:
    # Rankings table
    st.subheader("Ranking")

    with SessionLocal() as session:
        matches_df = convert_sqlalchemy_objects_to_df(session.query(Match).all())

    ranking_df = get_rankings(matches_df)
    PLAYERS_DF = convert_sqlalchemy_objects_to_df(session.query(Player).all())

    full_ranking_df = ranking_df.merge(
        PLAYERS_DF, left_on="player", right_on="uid", how="right"
    )
    full_ranking_df["user_image_url"] = full_ranking_df["uid"].apply(get_user_image_url)
    st.dataframe(
        full_ranking_df[
            ["rank", "user_image_url", "full_name", "wins", "losses", "wins_diff"]
        ].sort_values(["rank", "wins_diff"], ascending=[True, False]),
        hide_index=True,
        column_config={
            "rank": st.column_config.NumberColumn("Rank"),
            "full_name": st.column_config.TextColumn("Name"),
            "user_image_url": st.column_config.ImageColumn(""),
            "wins": st.column_config.NumberColumn("Wins"),
            "losses": st.column_config.NumberColumn("Losses"),
            "wins_diff": st.column_config.NumberColumn("Points"),
        },
        height=800,
    )
