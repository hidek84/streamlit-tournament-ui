import datetime
import hashlib
import json
from operator import and_
from typing import Dict, List

import pandas as pd
from sqlalchemy import or_

from models import Match, Player, SessionLocal


def get_login_user_uid(cookies):
    return "lucy"


def get_user_image_url(user_uid):
    return f"https://www.dummyimage.com/40x40/000/fff&text={user_uid}"


def get_rankings(df):
    def get_result(row):
        if pd.isna(row["player1_score"]) or pd.isna(row["player2_score"]):
            return pd.Series([None, None])
        if row["player1_score"] > row["player2_score"]:
            return pd.Series(
                [
                    row["player1_uid"],
                    row["player2_uid"],
                    (row["player1_score"] - row["player2_score"]),
                ]
            )
        elif row["player2_score"] > row["player1_score"]:
            return pd.Series(
                [
                    row["player2_uid"],
                    row["player1_uid"],
                    (row["player2_score"] - row["player1_score"]),
                ]
            )
        else:
            return pd.Series([None, None, 0])  # tie

    # Apply function to get winner and loser columns
    df[["winner", "loser", "wins_diff"]] = df.apply(get_result, axis=1)

    # Remove ties (no winner/loser)
    df = df[df["winner"].notna()]

    # Count wins and losses
    win_counts = (
        df["winner"].value_counts().rename_axis("player").reset_index(name="wins")
    )
    loss_counts = (
        df["loser"].value_counts().rename_axis("player").reset_index(name="losses")
    )

    # Merge wins and losses
    results = (
        pd.merge(win_counts, loss_counts, on="player", how="outer")
        .fillna(0)
        .merge(
            df[["winner", "wins_diff"]].groupby("winner").sum().reset_index().fillna(0),
            left_on="player",
            right_on="winner",
            how="left",
        )
        .fillna({"wins_diff": 0})
    )

    # Convert to int
    results[["wins", "losses"]] = results[["wins", "losses"]].astype(int)
    results["user_image_url"] = results["player"].apply(get_user_image_url)
    results["rank"] = (
        results[["wins", "wins_diff"]]
        .apply(tuple, axis=1)
        .rank(
            ascending=False,
            method="dense",
        )
    )

    # Sort by wins descending
    return results.sort_values(by="wins", ascending=False)


def convert_from_alchemy_to_dict(model):
    """Convert SQLAlchemy object to dict format"""
    return {k: v for k, v in model.__dict__.items() if not k.startswith("_")}


"""
* SQL Alchemy
* DF uid <=> events

* all matches
* my matches

* original
* player1 as me (columns swapped)

* full user info supplied

1. Your Opponent section
    my matches with player1 as me
2. Calendar events
    all matches with original data
"""


def convert_sqlalchemy_objects_to_df(sqlalchemy_objects) -> pd.DataFrame:
    d = [convert_from_alchemy_to_dict(a) for a in sqlalchemy_objects]
    return pd.DataFrame.from_records(d)


def get_my_matches_df(all_matches_df, my_user_uid):
    my_matches_df = all_matches_df[
        (all_matches_df.player1_uid == my_user_uid)
        | (all_matches_df.player2_uid == my_user_uid)
    ]
    if len(my_matches_df) > 0:
        for col in ["start", "end"]:
            my_matches_df[col] = pd.to_datetime(my_matches_df[col], format="ISO8601")
    return my_matches_df


def get_my_matches_df_player1_as_me(all_matches_df, my_user_uid):
    my_matches_df = get_my_matches_df(all_matches_df, my_user_uid)
    concatenated_df = pd.concat(
        [
            my_matches_df,
            my_matches_df.rename(
                columns={
                    "player1_uid": "player2_uid",
                    "player2_uid": "player1_uid",
                    "player1_score": "player2_score",
                    "player2_score": "player1_score",
                }
            ),
        ]
    )
    return concatenated_df[concatenated_df["player1_uid"] == my_user_uid]


def supply_full_user_info_to_match_df(player_df, match_df):
    full_info_df = match_df.merge(
        player_df, left_on="player1_uid", right_on="uid", how="left"
    ).merge(
        player_df,
        left_on="player2_uid",
        right_on="uid",
        how="left",
        suffixes=["_player1", "_player2"],
    )
    for p in ["player1", "player2"]:
        full_info_df[f"{p}_image_url"] = full_info_df[f"{p}_uid"].apply(
            get_user_image_url
        )
    return full_info_df


def get_matches_as_cal_events(all_matches_df, player_df, my_user_id):
    events = convert_matches_df_to_events(player_df, all_matches_df)
    return set_special_property_if_mine(events, my_user_id)


def check_if_my_event(event, my_user_id):
    return (
        event["extendedProps"]["source"]["player1_uid"] == my_user_id
        or event["extendedProps"]["source"]["player2_uid"] == my_user_id
    )


def set_special_property_if_mine(events, my_user_id):
    updated_events = events
    for e in updated_events:
        e["backgroundColor"] = (
            ("#ff0000" if check_if_my_event(e, my_user_id) else "#0000ff"),
        )
        e["editable"] = True if check_if_my_event(e, my_user_id) else False
        e["title"] = e["title"] if check_if_my_event(e, my_user_id) else "Other Game"
    return updated_events


def convert_matches_df_to_events(player_df, matches_df) -> List[Dict]:
    return [
        {
            "id": m["id"],
            "title": f"{m['full_name_player1']} vs {m['full_name_player2']}",
            "start": m["start"],
            "end": m["end"],
            "extendedProps": {"source": m},
        }
        for m in supply_full_user_info_to_match_df(player_df, matches_df)
        .fillna(value="None")
        .to_dict(orient="records")
    ]


def generate_time_options(start_time, end_time, step_minutes):
    time_options = []
    current_time = datetime.datetime.combine(datetime.date.today(), start_time)
    end_datetime = datetime.datetime.combine(datetime.date.today(), end_time)

    while current_time <= end_datetime:
        time_options.append(current_time.time())
        current_time += datetime.timedelta(minutes=step_minutes)

    return time_options


def generate_hash_from_uid(uid):
    salt = "JrOz5Irlgf5Lh6CIHLsUQO4CJk14yuQJXRmGd7Wc3LE="
    iter_num = 100
    hash_object = hashlib.pbkdf2_hmac("sha256", uid.encode(), salt.encode(), iter_num)
    return hash_object.hex()
