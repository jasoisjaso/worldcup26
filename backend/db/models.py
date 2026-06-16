from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"
    code = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    fifa_code = Column(String)
    elo = Column(Float, default=1500.0)
    fifa_ranking = Column(Integer)
    primary_color = Column(String, default="#ffffff")
    flag_url = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Match(Base):
    __tablename__ = "matches"
    id = Column(String, primary_key=True)
    group = Column(String)
    matchday = Column(Integer)
    kickoff = Column(DateTime)
    venue = Column(String)
    home_code = Column(String)
    away_code = Column(String)
    status = Column(String, default="upcoming")
    home_score = Column(Integer)
    away_score = Column(Integer)


class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False)
    market = Column(String, nullable=False)
    our_probability = Column(Float, nullable=False)
    bookmaker_odds = Column(Float)
    ev = Column(Float)
    logged_at = Column(DateTime, default=datetime.utcnow)
    # Closing Line Value: the de-vigged closing line captured near kickoff, and this pick's
    # EV measured against it (clv = p_close_fair * bet_odds - 1). Both nullable — filled in
    # by the CLV job once a match nears kickoff. See backend/data/clv.py.
    closing_odds = Column(Float)
    clv = Column(Float)


class PredictionSnapshot(Base):
    """Full pre-kickoff model distribution for EVERY upcoming match (not just +EV picks),
    so live calibration (RPS/Brier/log-loss) can be scored without the EV-selection bias
    of the Prediction table. Outcome is derived lazily by joining to the completed Match."""
    __tablename__ = "prediction_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False, unique=True)
    model_version = Column(String)
    p_home = Column(Float)
    p_draw = Column(Float)
    p_away = Column(Float)
    p_over_2_5 = Column(Float)
    p_btts = Column(Float)
    lambda_home = Column(Float)
    lambda_away = Column(Float)
    logged_at = Column(DateTime, default=datetime.utcnow)


class OddsCache(Base):
    __tablename__ = "odds_cache"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False)
    market = Column(String, nullable=False)
    bookmaker = Column(String)
    odds = Column(Float)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class NewsCache(Base):
    __tablename__ = "news_cache"
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_code = Column(String, nullable=False)
    headline = Column(Text)
    source = Column(String)
    url = Column(String)
    published_at = Column(DateTime)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class HistoricalResult(Base):
    __tablename__ = "historical_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime)
    home_team = Column(String)
    away_team = Column(String)
    home_score = Column(Integer)
    away_score = Column(Integer)
    tournament = Column(String)
    neutral = Column(Boolean, default=False)
