from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

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
    subreddit: str | None
    title: str
    url: str
    score: int
    sentiment: str | None
    emotion: str | None
    topic: str | None
    tool_mentioned: str | None
    controversy_score: float | None
    post_date: date
    created_at_utc: datetime

class PostsListResponse(BaseModel):
    posts: list[PostResponse]
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
    dominant_emotion: str | None
    avg_controversy: float

class TrendsListResponse(BaseModel):
    data: list[DailySentimentResponse]
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
    data: list[ToolComparisonResponse]
    tools: list[str]


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
    data: list[CommunityDivergenceResponse]


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    id: int
    topic: str
    today_count: int
    rolling_avg: float
    pct_increase: float
    triggered_at: datetime

class AlertsListResponse(BaseModel):
    alerts: list[AlertResponse]
    total: int


# ── RAG ───────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(min_length=5, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)

class QueryResponse(BaseModel):
    query: str
    report: str
    sources_used: list[str]
    generated_at: datetime
    cached: bool = False


# ── Health ────────────────────────────────────────────────────────────────────

class PipelineRunResponse(BaseModel):
    run_id: str
    dag_id: str
    start_time: datetime
    end_time: datetime | None
    duration_seconds: float | None
    posts_ingested: int
    posts_classified: int
    posts_failed: int
    error_rate: float

class HealthResponse(BaseModel):
    status: str
    latest_run: PipelineRunResponse | None


# ── Cache ─────────────────────────────────────────────────────────────────────

class CacheInvalidateResponse(BaseModel):
    status: str
    keys_deleted: int
