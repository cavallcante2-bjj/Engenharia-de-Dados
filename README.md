# 📚 Livraria Inteligente

Pipeline de dados completo que raspa o catálogo público [books.toscrape.com](https://books.toscrape.com), organiza os dados em camadas **bronze → prata → ouro** no Postgres (Supabase) e expõe um **agente de IA** que responde perguntas de negócio em português, gerando SQL sob demanda.

> Projeto de estudo da pós-graduação em Engenharia de Dados e IA (Pós Tech) — módulo de Engenharia de Contexto Aplicada a Dados.

## O problema

A diretoria de uma livraria (fictícia, usando o catálogo do books.toscrape.com) quer saber coisas como *"qual categoria tem mais valor em estoque?"* ou *"quantos livros bem avaliados custam menos de £20?"* sem depender do time de dados para escrever uma consulta a cada pergunta.

A solução: um pipeline que deixa os dados limpos e organizados, e um agente que converte a pergunta em português direto em SQL, executa com segurança e responde com o número certo.

## Como funciona (visão geral)

```
books.toscrape.com ──► bronze.livros ──► prata.livros ──► ouro.livros / ouro.categorias ──► agente SQL
     (scraping)           (dado cru)      (dado limpo)         (métricas de negócio)         (pergunta → SQL → resposta)
```

1. **Bronze** — o scraper (`01_scraper_bronze.py`) visita cada página de detalhe do catálogo e grava o texto exatamente como veio (sem limpeza), numa tabela que só recebe inserções (append-only).
2. **Prata** — uma *view* SQL (`sql/01_prata.sql`) aplica regras de limpeza: extrai preço, nota, estoque, remove duplicatas etc.
3. **Ouro** — outras *views* (`sql/02_ouro.sql`) calculam métricas de negócio: valor em estoque, faixa de preço, se o livro é bem avaliado, agregados por categoria.
4. **Agente SQL** — um script (`04_sql_agent.py`) e uma interface web (`streamlit_app.py`) que recebem a pergunta em português, pedem ao LLM (Claude ou GPT) para gerar **um único `SELECT`**, executam numa transação somente leitura e devolvem a resposta em português.

O agente só tem permissão de consultar os schemas `prata` e `ouro` — nunca a `bronze`, que pode ter dados crus e duplicados.

## Por que camadas bronze/prata/ouro?

- **Bronze** preserva exatamente o que foi coletado, até com os defeitos (ex.: `£` chega como `Â£` por causa de encoding). Serve como fonte da verdade caso algo precise ser reprocessado.
- **Prata** padroniza os tipos e remove duplicidade (mantendo apenas a coleta mais recente de cada livro).
- **Ouro** calcula métricas prontas para responder perguntas de negócio, sem repetir lógica em cada consulta.

Essa separação deixa claro onde cada regra é aplicada e facilita depurar: se um número está errado, basta olhar a camada onde a regra foi definida.

## Estrutura do repositório

```
.
├── 01_scraper_bronze.py     # Raspa o catálogo e grava na tabela bronze.livros
├── aplicar_sql.py           # Utilitário para rodar arquivos .sql ou queries ad-hoc no banco
├── 04_sql_agent.py          # Agente de linha de comando: pergunta em português → SQL → resposta
├── streamlit_app.py         # Interface web do agente SQL (usa o mesmo motor do 04_sql_agent.py)
├── sql/
│   ├── 00_bronze.sql        # Cria a tabela bronze.livros
│   ├── 01_prata.sql         # View prata.livros (dados limpos)
│   └── 02_ouro.sql          # Views ouro.livros e ouro.categorias (métricas)
├── requirements.txt         # Dependências Python
├── .env.exemplo             # Modelo das variáveis de ambiente (copie para .env)
├── PRD.md                   # Problema, objetivo e perguntas que o produto precisa responder
├── SPEC.md                  # Especificação técnica, etapa por etapa
└── CONTEXTO.md              # Memória viva do projeto: regras de negócio, dicionário de dados, decisões
```

## Pré-requisitos

- Python 3.11+
- Uma conta [Supabase](https://supabase.com) (ou qualquer Postgres acessível) com a `DATABASE_URL` de conexão
- Uma chave de API da [Anthropic](https://console.anthropic.com) (padrão deste projeto) ou da [OpenAI](https://platform.openai.com)

## Como rodar

### 1. Clonar e instalar dependências

```bash
git clone https://github.com/cavallcante2-bjj/Engenharia-de-Dados.git
cd Engenharia-de-Dados
pip install -r requirements.txt
```

### 2. Configurar as variáveis de ambiente

Copie o arquivo de exemplo e preencha com seus dados reais:

```bash
cp .env.exemplo .env
```

Edite o `.env` com:

```env
DATABASE_URL=postgresql://postgres:sua_senha@db.seu-projeto.supabase.co:5432/postgres
LLM_PROVIDER=anthropic          # ou "openai"
LLM_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_API_KEY=sua_chave     # se usar provider=anthropic
OPENAI_API_KEY=sua_chave        # se usar provider=openai
```

> ⚠️ Se a senha do banco tiver caracteres especiais (como `@`), eles precisam ser codificados na URL — por exemplo, `@` vira `%40`.
>
> 🔒 O `.env` nunca deve ser commitado — ele já está no `.gitignore`.

### 3. Criar as tabelas e views no banco

```bash
python aplicar_sql.py sql/00_bronze.sql
python aplicar_sql.py sql/01_prata.sql
python aplicar_sql.py sql/02_ouro.sql
```

### 4. Rodar o scraper (popular a camada bronze)

```bash
python 01_scraper_bronze.py --paginas 2
```

Cada página tem 20 livros. Rode com mais páginas (até 50) para trazer o catálogo completo (1.000 livros). O scraper pode ser executado várias vezes — a deduplicação acontece na camada prata, não na bronze.

### 5. Conversar com o agente SQL

Via terminal:

```bash
python 04_sql_agent.py
```

Via navegador (interface Streamlit):

```bash
streamlit run streamlit_app.py
```

Exemplos de perguntas que o agente responde:
- "Qual categoria tem o maior valor em estoque, em reais?"
- "Quantos livros bem avaliados custam menos de £20?"
- "Quantos livros únicos temos na base?"
- "Qual o preço médio por faixa de preço?"

## Como o agente SQL funciona por dentro

A cada pergunta, o agente monta um prompt de sistema com três camadas de contexto:

1. **Instruções fixas** — papel do agente, regra de só gerar `SELECT`/`WITH`, pedir esclarecimento se a pergunta for ambígua.
2. **O arquivo `CONTEXTO.md` inteiro** — regras de negócio, dicionário de dados e decisões do projeto, lidas do disco a cada execução.
3. **O schema real do banco** — colunas e tipos das tabelas `prata` e `ouro`, consultados em tempo real no `information_schema`.

Isso é o que chamamos de **engenharia de contexto**: em vez de depender só do conhecimento geral do LLM, a cada pergunta ele recebe o contexto de negócio e a estrutura real dos dados, o que reduz alucinação e erros de SQL.

Existe também uma flag `--sem-contexto` que roda o agente só com instruções mínimas e o schema de *todas* as tabelas (incluindo a bronze) — usada para comparar e demonstrar, na prática, a diferença que o contexto faz.

### Guardrails de segurança

- Só aceita comandos `SELECT` ou `WITH`, um por vez.
- Bloqueia palavras-chave de escrita/DDL (`insert`, `update`, `delete`, `drop`, `alter`, etc.).
- Executa em transação **somente leitura**, com `statement_timeout` de 10 segundos.
- Limita o resultado a 50 linhas.
- Se o SQL falhar, devolve o erro ao LLM e tenta de novo (até 3 vezes).

## Regras de negócio (resumo)

| Regra | O que faz |
|---|---|
| R1 | Chave única por `upc`; mantém só a coleta mais recente |
| R2 | Extrai o valor numérico do preço (moeda: GBP) |
| R3 | Converte `star-rating One..Five` em nota `1..5` |
| R4 | Extrai a quantidade em estoque do texto (`In stock (22 available)` → `22`) |
| R5 | Extrai o número de avaliações |
| R6 | Categorias inválidas (`Default`, `Add a comment`) tornam-se `Sem categoria` |
| M1 | Valor em estoque = preço × quantidade |
| M2 | "Bem avaliado" = nota ≥ 4 |
| M3 | Faixa de preço: até £20 · £20–40 · acima de £40 |

A lista completa, com motivação de cada decisão, está em [`CONTEXTO.md`](CONTEXTO.md).

## Stack

- **Python** — `requests` + `beautifulsoup4` (scraping), `psycopg` (conexão com Postgres), `python-dotenv` (variáveis de ambiente)
- **Postgres / Supabase** — armazenamento e transformação via SQL puro (sem ORM)
- **Anthropic Claude / OpenAI GPT** — geração do SQL e das respostas em português
- **Streamlit** — interface web do agente

## Documentação do projeto

- [`PRD.md`](PRD.md) — problema, objetivo e critérios de sucesso
- [`SPEC.md`](SPEC.md) — especificação técnica, etapa por etapa, com critérios de aceite
- [`CONTEXTO.md`](CONTEXTO.md) — memória viva do projeto: estado atual, regras de negócio, dicionário de dados e decisões tomadas
- [`AGENTS.md`](AGENTS.md) — regras para qualquer agente de IA que for trabalhar neste repositório
