with enriched as (
    select * from {{ ref('int_posts_enriched') }}
    where is_classified = true
),

by_source as (
    select
        post_date,
        topic,
        source,
        round(avg(sentiment_score), 4)              as avg_sentiment,
        count(*)                                    as post_count
    from enriched
    group by post_date, topic, source
),

reddit as (
    select post_date, topic, avg_sentiment as reddit_sentiment, post_count as reddit_count
    from by_source
    where source = 'reddit'
),

hackernews as (
    select post_date, topic, avg_sentiment as hn_sentiment, post_count as hn_count
    from by_source
    where source = 'hackernews'
),

divergence as (
    select
        coalesce(r.post_date, h.post_date)          as post_date,
        coalesce(r.topic, h.topic)                  as topic,
        coalesce(r.reddit_sentiment, 0)             as reddit_sentiment,
        coalesce(h.hn_sentiment, 0)                 as hn_sentiment,
        coalesce(r.reddit_count, 0)                 as reddit_count,
        coalesce(h.hn_count, 0)                     as hn_count,

        -- Delta: positive means Reddit more positive than HN
        round(
            coalesce(r.reddit_sentiment, 0) - coalesce(h.hn_sentiment, 0),
            4
        )                                           as sentiment_delta,

        current_timestamp                           as updated_at

    from reddit r
    full outer join hackernews h
        on r.post_date = h.post_date
        and r.topic = h.topic
)

select * from divergence
