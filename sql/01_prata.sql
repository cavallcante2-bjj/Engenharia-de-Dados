create schema if not exists prata;

create or replace view prata.livros as
with ranked as (
    select
        payload,
        _ingestao_em,
        row_number() over (
            partition by payload->>'upc'          -- R1
            order by _ingestao_em desc            -- R1
        ) as linha_mais_recente
    from bronze.livros
)
select
    trim(payload->>'upc') as upc,                                                          -- R7
    trim(payload->>'titulo') as titulo,                                                    -- R7
    case
        when trim(payload->>'categoria_raw') in ('Default', 'Add a comment')                -- R6
            then 'Sem categoria'                                                            -- R6
        else trim(payload->>'categoria_raw')                                                 -- R6, R7
    end as categoria,
    regexp_replace(payload->>'preco_raw', '[^0-9.]', '', 'g')::numeric(10,2) as preco_gbp,   -- R2
    case trim(payload->>'rating_raw')                                                       -- R3
        when 'One' then 1
        when 'Two' then 2
        when 'Three' then 3
        when 'Four' then 4
        when 'Five' then 5
    end as rating,                                                                           -- R3
    coalesce((regexp_match(payload->>'estoque_raw', '(\d+)'))[1]::int, 0) as estoque_qtd,    -- R4
    trim(payload->>'n_reviews_raw')::int as n_reviews,                                       -- R5
    trim(payload->>'url') as url,                                                            -- R7
    _ingestao_em
from ranked
where linha_mais_recente = 1;  -- R1
