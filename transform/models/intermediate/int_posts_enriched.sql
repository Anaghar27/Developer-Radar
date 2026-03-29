with raw as (
    select * from {{ ref('stg_raw_posts') }}
),

processed as (
    select * from {{ ref('stg_processed_posts') }}
),

enriched as (
    select
        -- Identity
        raw.post_id,
        raw.source,
        raw.title,
        raw.body,
        raw.url,
        raw.score,
        raw.post_date,
        raw.created_at_utc,
        raw.ingested_at,
        raw.body_length,
        raw.is_reddit,
        raw.ingest_batch_id,

        -- Classification fields (null if not yet classified)
        processed.sentiment,
        processed.emotion,
        processed.topic,
        processed.tool_mentioned,
        processed.controversy_score,
        processed.reasoning,
        processed.processed_at,

        -- Derived fields
        case
            when processed.sentiment = 'positive' then 1
            when processed.sentiment = 'negative' then -1
            else 0
        end                                         as sentiment_score,

        case
            when processed.post_id is not null then true
            else false
        end                                         as is_classified,

        length(raw.title) + raw.body_length         as total_content_length,

        current_date - raw.post_date::date          as days_ago

    from raw
    left join processed
        on raw.post_id = processed.post_id
)

select * from enriched
