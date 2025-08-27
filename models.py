import pandas as pd
from sqlalchemy import Column, DateTime, Integer, String, create_engine, insert
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Player(Base):
    __tablename__ = "players"
    uid = Column(String, primary_key=True)
    full_name = Column(String, nullable=False)


class Match(Base):
    __tablename__ = "matches"
    id = Column(String, primary_key=True)
    player1_uid = Column(String, nullable=False)
    player2_uid = Column(String, nullable=False)
    player1_score = Column(Integer, default=0)
    player2_score = Column(Integer, default=0)
    status = Column(String)
    start = Column(String)
    end = Column(String)


# SQLite engine
engine = create_engine("sqlite:///data/tournament.db", echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)

    # Insert dummy initial data
    with SessionLocal() as session:
        players = [
            Player(**entry)
            for entry in pd.read_csv("data/players.csv").to_dict(orient="records")
        ]
        session.add_all(players)
        players = [
            Match(**entry)
            for entry in pd.read_csv("data/matches.csv").to_dict(orient="records")
        ]
        session.add_all(players)
        session.commit()


if __name__ == "__main__":
    init_db()
