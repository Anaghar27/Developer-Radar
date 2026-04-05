{{
    config(
        materialized='incremental',
        unique_key='post_date || \'_\' || topic',
        on_schema_change='sync_all_columns'
    )
}}

with enriched as (
    select * from {{ ref('int_posts_enriched') }}
    {% if is_incremental() %}
        -- Process last 8 days to ensure rolling avg recalculates correctly
        -- (7-day window needs 7 prior days + today)
        where post_date >= (
            select coalesce(max(post_date), '1970-01-01'::date) - interval '8 days'
            from {{ this }}
        )
    {% endif %}
),

daily_counts as (
    select
        post_date,
        topic,
        count(*)                                    as today_count
    from enriched
    where topic is not null
    group by post_date, topic
),

with_rolling as (
    select
        post_date,
        topic,
        today_count,

        -- 7-day rolling average (excluding today)
        round(
            avg(today_count) over (
                partition by topic
                order by post_date
                rows between 7 preceding and 1 preceding
            ),
            2
        )                                           as rolling_avg_7d,

        -- Percentage change vs rolling average
        case
            when avg(today_count) over (
                partition by topic
                order by post_date
                rows between 7 preceding and 1 preceding
            ) > 0
            then round(
                (today_count - avg(today_count) over (
                    partition by topic
                    order by post_date
                    rows between 7 preceding and 1 preceding
                )) / avg(today_count) over (
                    partition by topic
                    order by post_date
                    rows between 7 preceding and 1 preceding
                ) * 100,
                2
            )
            else 0
        end                                         as pct_change

    from daily_counts
),

final as (
    select
        post_date,
        topic,
        today_count,
        coalesce(rolling_avg_7d, 0)                 as rolling_avg_7d,
        coalesce(pct_change, 0)                     as pct_change,

        -- Spike flag: today > rolling avg * 1.30
        case
            when rolling_avg_7d > 0
             and today_count > rolling_avg_7d * 1.30
            then true
            else false
        end                                         as spike_flag,

        current_timestamp                           as updated_at

    from with_rolling
)

select * from final
