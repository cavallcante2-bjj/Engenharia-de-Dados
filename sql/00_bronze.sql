create schema if not exists bronze;

create table if not exists bronze.livros (
    id bigserial primary key,
    fonte_url text not null,
    payload jsonb not null,
    _execucao_id text not null,
    _ingestao_em timestamptz not null default now()
);
