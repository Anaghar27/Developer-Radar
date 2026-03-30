with source as (
    select * from {{ source('postgres', 'processed_posts') }}
),

cleaned as (
    select
        post_id,

        -- Validate sentiment enum, default to 'neutral' if invalid
        case
            when sentiment in ('positive', 'negative', 'neutral')
                then sentiment
            else 'neutral'
        end                                         as sentiment,

        -- Validate emotion enum, default to 'neutral' if invalid
        case
            when emotion in (
                'excited', 'frustrated', 'skeptical',
                'curious', 'hopeful', 'neutral'
            ) then emotion
            else 'neutral'
        end                                         as emotion,

        -- Validate topic enum, default to 'Other' if invalid
        case
            when topic in (
                'LLM', 'Agents', 'RAG', 'MLOps', 'Python',
                'WebDev', 'DevTools', 'Cloud', 'Hardware',
                'Security', 'Career', 'OpenSource', 'Other'
            ) then topic
            else 'Other'
        end                                         as topic,

        -- tool_mentioned can be null — coerce to 'none'
        coalesce(lower(trim(tool_mentioned)), 'none') as tool_mentioned,

        -- controversy_score: clamp between 0 and 1
        case
            when controversy_score < 0 then 0.0
            when controversy_score > 1 then 1.0
            else coalesce(controversy_score, 0.0)
        end                                         as controversy_score,

        coalesce(reasoning, '')                     as reasoning,
        processed_at

    from source
    where post_id is not null
)

select * from cleaned
