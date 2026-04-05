{{
    config(
        materialized='incremental',
        unique_key='post_date || \'_\' || topic || \'_\' || tool_mentioned || \'_\' || source',
        on_schema_change='sync_all_columns'
    )
}}

with enriched as (
    select * from {{ ref('int_posts_enriched') }}
    where is_classified = true
    {% if is_incremental() %}
        -- Only process posts from dates not yet in this mart
        -- On first run (full refresh): processes all data
        -- On subsequent runs: only processes new dates
        and post_date > (
            select coalesce(max(post_date), '1970-01-01'::date)
            from {{ this }}
        )
    {% endif %}
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
