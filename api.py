from datetime import datetime
from typing import List

import pandas as pd
import pytz
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from models import Match, Player, SessionLocal
from utils import (
    convert_sqlalchemy_objects_to_df,
    generate_hash_from_uid,
    get_my_matches_df_player1_as_me,
    supply_full_user_info_to_match_df,
)

app = FastAPI()

with SessionLocal() as session:
    players_df = convert_sqlalchemy_objects_to_df(session.query(Player).all())


def find_user_from_hash(hash):
    players_df["hash"] = players_df["uid"].apply(generate_hash_from_uid)
    found = players_df[players_df["hash"] == hash]
    if len(found) == 1:
        return found["uid"].to_list()[0]
    else:
        return False


# Helper function to format the datetime to iCal format
def to_ical_datetime(dt: str) -> str:
    dt_obj = datetime.fromisoformat(dt)
    dt_obj = dt_obj.astimezone(pytz.utc)  # Convert to UTC
    return dt_obj.strftime("%Y%m%dT%H%M%SZ")


# API endpoint to return matches in iCal format
@app.get("/api/matches/ical")
async def get_matches_ical(hash):
    # Fetch the data (replace with real DB query)

    uid = find_user_from_hash(hash)
    if not uid:
        return PlainTextResponse(content="link is invalid")
    with SessionLocal() as session:
        db_data = supply_full_user_info_to_match_df(
            session, get_my_matches_df_player1_as_me(session, uid)
        )
        ical_content = "BEGIN:VCALENDAR\nVERSION:2.0\nCALSCALE:GREGORIAN\n\n"

    for match in db_data.to_dict(orient="records"):
        ical_content += f"""BEGIN:VEVENT
SUMMARY:{match['full_name_player1']} vs {match['full_name_player2']}
DTSTART:{to_ical_datetime(match['start'].tz_convert('UTC').strftime("%Y%m%dT%H%M%SZ"))}
DTEND:{to_ical_datetime(match['end'].tz_convert('UTC').strftime("%Y%m%dT%H%M%SZ"))}
DESCRIPTION:Match {match['full_name_player1']} vs {match['full_name_player2']}
UID:{match['id']}
END:VEVENT

"""

    ical_content += "END:VCALENDAR"
    return PlainTextResponse(content=ical_content)
