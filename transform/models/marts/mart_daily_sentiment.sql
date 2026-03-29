with enriched as (
    select * from {{ ref('int_posts_enriched') }}
    where is_classified = true
),

daily as (
    select
        post_date,
        topic,
        tool_mentioned,
        source,

        -- Volume
        count(*)                                    as post_count,

        -- Sentiment
        round(avg(sentiment_score), 4)              as avg_sentiment,
        sum(case when sentiment = 'positive' then 1 else 0 end) as positive_count,
        sum(case when sentiment = 'negative' then 1 else 0 end) as negative_count,
        sum(case when sentiment = 'neutral'  then 1 else 0 end) as neutral_count,

        -- Dominant emotion (most frequent)
        mode() within group (order by emotion)      as dominant_emotion,

        -- Controversy
        round(avg(controversy_score), 4)            as avg_controversy,

        current_timestamp                           as updated_at

    from enriched
    group by
        post_date,
        topic,
        tool_mentioned,
        source
)

select * from daily
