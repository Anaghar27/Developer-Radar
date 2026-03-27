with src as (
    select * from {{ source('postgres', 'raw_posts') }}
),

cleaned as (
    select
        src.id                                          as post_id,
        src.source                                      as source,
        trim(src.title)                                 as title,
        coalesce(trim(src.body), '')                    as body,
        src.url                                         as url,
        coalesce(src.score, 0)                          as score,
        src.created_at                                  as created_at_utc,
        date_trunc('day', src.created_at)               as post_date,
        src.ingest_batch_id,
        src.created_at                                  as ingested_at,
        length(coalesce(src.body, ''))                  as body_length,
        case
            when src.source = 'reddit' then true
            else false
        end                                             as is_reddit
    from src
    where
        src.title is not null
        and trim(src.title) != ''
        and src.id is not null
)

select * from cleaned
