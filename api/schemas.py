from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, date


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

class UserRegisterResponse(BaseModel):
    user_id: int
    email: str
    api_key: str

class TokenRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Posts ─────────────────────────────────────────────────────────────────────

class PostResponse(BaseModel):
    post_id: str
    source: str
    subreddit: Optional[str]
    title: str
    url: str
    score: int
    sentiment: Optional[str]
    emotion: Optional[str]
    topic: Optional[str]
    tool_mentioned: Optional[str]
    controversy_score: Optional[float]
    post_date: date
    created_at_utc: datetime

class PostsListResponse(BaseModel):
    posts: List[PostResponse]
    total: int
    limit: int


# ── Trends ────────────────────────────────────────────────────────────────────

class DailySentimentResponse(BaseModel):
    post_date: date
    topic: str
    tool_mentioned: str
    source: str
    post_count: int
    avg_sentiment: float
    positive_count: int
    negative_count: int
    neutral_count: int
    dominant_emotion: Optional[str]
    avg_controversy: float

class TrendsListResponse(BaseModel):
    data: List[DailySentimentResponse]
    total: int


# ── Tools ─────────────────────────────────────────────────────────────────────

class ToolComparisonResponse(BaseModel):
    post_date: date
    tool: str
    source: str
    post_count: int
    avg_sentiment: float
    positive_count: int
    negative_count: int
    neutral_count: int
    avg_controversy: float

class ToolsListResponse(BaseModel):
    data: List[ToolComparisonResponse]
    tools: List[str]


# ── Community ─────────────────────────────────────────────────────────────────

class CommunityDivergenceResponse(BaseModel):
    post_date: date
    topic: str
    reddit_sentiment: float
    hn_sentiment: float
    reddit_count: int
    hn_count: int
    sentiment_delta: float

class CommunityListResponse(BaseModel):
    data: List[CommunityDivergenceResponse]


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    id: int
    topic: str
    today_count: int
    rolling_avg: float
    pct_increase: float
    triggered_at: datetime

class AlertsListResponse(BaseModel):
    alerts: List[AlertResponse]
    total: int


# ── RAG ───────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(min_length=5, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)

class QueryResponse(BaseModel):
    query: str
    report: str
    sources_used: List[str]
    generated_at: datetime
    cached: bool = False


# ── Health ────────────────────────────────────────────────────────────────────

class PipelineRunResponse(BaseModel):
    run_id: str
    dag_id: str
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: Optional[float]
    posts_ingested: int
    posts_classified: int
    posts_failed: int
    error_rate: float

class HealthResponse(BaseModel):
    status: str
    latest_run: Optional[PipelineRunResponse]


# ── Cache ─────────────────────────────────────────────────────────────────────

class CacheInvalidateResponse(BaseModel):
    status: str
    keys_deleted: int
