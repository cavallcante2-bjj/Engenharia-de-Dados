create schema if not exists ouro;

create or replace view ouro.livros as
select
    upc,
    titulo,
    categoria,
    preco_gbp,
    rating,
    estoque_qtd,
    n_reviews,
    url,
    _ingestao_em,
    preco_gbp * estoque_qtd as valor_estoque_gbp,          -- M1
    case
        when preco_gbp < 20 then 'até £20'                 -- M3
        when preco_gbp < 40 then '£20–40'                   -- M3
        else 'acima de £40'                                 -- M3
    end as faixa_preco,
    rating >= 4 as bem_avaliado                            -- M2
from prata.livros;

create or replace view ouro.categorias as
select
    categoria,
    count(*) as qtd_titulos,
    round(avg(preco_gbp), 2) as preco_medio_gbp,
    round(avg(rating), 2) as rating_medio,
    sum(estoque_qtd) as estoque_unidades,
    sum(valor_estoque_gbp) as valor_estoque_gbp,           -- M1
    round(
        100.0 * sum(case when bem_avaliado then 1 else 0 end) / count(*),  -- M2
        2
    ) as pct_bem_avaliados
from ouro.livros
group by categoria;
