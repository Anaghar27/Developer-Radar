{{
    config(
        materialized='incremental',
        unique_key='post_date || \'_\' || tool || \'_\' || source',
        on_schema_change='sync_all_columns'
    )
}}

with enriched as (
    select * from {{ ref('int_posts_enriched') }}
    where is_classified = true
    and tool_mentioned != 'none'
    {% if is_incremental() %}
        and post_date > (
            select coalesce(max(post_date), '1970-01-01'::date)
            from {{ this }}
        )
    {% endif %}
),

tool_daily as (
    select
        post_date,
        tool_mentioned                              as tool,
        source,

        count(*)                                    as post_count,
        round(avg(sentiment_score), 4)              as avg_sentiment,
        round(avg(controversy_score), 4)            as avg_controversy,
        sum(case when sentiment = 'positive' then 1 else 0 end) as positive_count,
        sum(case when sentiment = 'negative' then 1 else 0 end) as negative_count,
        sum(case when sentiment = 'neutral'  then 1 else 0 end) as neutral_count,

        current_timestamp                           as updated_at

    from enriched
    group by
        post_date,
        tool_mentioned,
        source
)

select * from tool_daily
