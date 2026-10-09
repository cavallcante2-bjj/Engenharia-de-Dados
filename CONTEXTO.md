# CONTEXTO.md · Memória viva do projeto

> **Leia este arquivo antes de qualquer tarefa.** Ele vence o SPEC e o PRD em caso de conflito. **Atualize ao final de cada etapa** (§1 e §5). O agente SQL também lê este arquivo inteiro.

## 1\. Estado do projeto

| etapa | status | observação |
| :---- | :---- | :---- |
| 1 · Scraping → bronze | ✅ feito | critérios de aceite validados (80/40 após 2 execuções de `--paginas 2`) |
| 2 · Prata | ✅ feito | view `prata.livros`, critérios de aceite validados |
| 3 · Ouro | ✅ feito | views `ouro.livros` e `ouro.categorias`, critérios de aceite validados |
| 4 · Agente SQL | ✅ feito | `04_sql_agent.py`; acertou as 4 perguntas do PRD, nunca consultou bronze |

&nbsp;

**Próximo passo:** nenhum — pipeline completo (etapas 1 a 4 concluídas).

## 2\. Fonte de dados: books.toscrape.com

- Site público feito para treinar scraping. 50 páginas × 20 livros \= 1.000 livros.  
- Listagem: `https://books.toscrape.com/catalogue/page-{n}.html` → links em `article.product_pod h3 a`.  
- Detalhe do livro: título em `div.product_main h1`; preço em `div.product_main p.price_color`; avaliação na classe de `p.star-rating` (ex.: `star-rating Three`); tabela `table.table` com `UPC`, `Availability`, `Number of reviews`; categoria no 3º link de `ul.breadcrumb`.  
- **Encoding:** o site não declara charset. Com `requests`, o `£` costuma chegar como `Â£`. Na bronze isso fica como veio; R2 resolve na prata.  
- Campos do `payload` na bronze: `url`, `titulo`, `preco_raw`, `rating_raw`, `estoque_raw`, `upc`, `n_reviews_raw`, `categoria_raw`, `descricao`.

## 3\. Regras de negócio

**Bronze → prata**

- **R1 · Chave e duplicidade:** chave \= `upc`. Manter só a linha com o `_ingestao_em` mais recente.  
- **R2 · Preço:** extrair só o número de `preco_raw` → `preco_gbp numeric(10,2)`. Moeda \= libra (GBP).  
- **R3 · Avaliação:** `star-rating One..Five` → `rating` 1..5.  
- **R4 · Estoque:** de `In stock (22 available)` extrair `22` → `estoque_qtd int`. Sem número \= 0\.  
- **R5 · Reviews:** `n_reviews_raw` → `n_reviews int`.  
- **R6 · Categoria:** `Default` e `Add a comment` não são categorias → `Sem categoria`.  
- **R7 · Texto:** remover espaços nas pontas.

**Métricas (ouro)**

- **M1 · Valor em estoque** \= `preco_gbp × estoque_qtd`.  
- **M2 · Bem avaliado** \= `rating >= 4`.  
- **M3 · Faixa de preço:** `até £20` (\< 20\) · `£20–40` (20 a \< 40\) · `acima de £40` (≥ 40).  
- **M4 · Moeda das respostas:** GBP. Se pedirem reais, usar o câmbio de §5. Rankings de categoria **excluem** `Sem categoria`, salvo pedido explícito.

## 4\. Dicionário de dados

**prata.livros** (1 linha \= 1 livro): `upc` · `titulo` · `categoria` · `preco_gbp` · `rating` · `estoque_qtd` · `n_reviews` · `url` · `_ingestao_em`

**ouro.livros:** prata \+ `valor_estoque_gbp` (M1) · `faixa_preco` (M3) · `bem_avaliado` (M2, bool)

**ouro.categorias** (1 linha \= 1 categoria): `categoria` · `qtd_titulos` · `preco_medio_gbp` · `rating_medio` · `estoque_unidades` · `valor_estoque_gbp` · `pct_bem_avaliados`

## 5\. Decisões

| data | decisão | motivo | quem |
| :---- | :---- | :---- | :---- |
| 08/10 | Bronze append-only; dedup só na prata | preservar o que veio de cada execução | Eng. Dados |
| 08/10 | Prata e ouro como views | base pequena, sempre atualizada | Eng. Dados |
| 08/10 | Câmbio fixo **£1 \= R\$ 7,20** | relatório da diretoria em reais (valor fictício da aula) | Financeiro |
| 08/10 | Agente SQL só lê `prata` e `ouro` | bronze tem lixo e duplicidade | Eng. Dados |
| 08/10 | `.env` corrigido: senha com `@` precisa de `%40` na `DATABASE_URL` | `@` solto quebra o parse do host da conexão | Eng. Dados |
| 08/10 | LLM do agente SQL: Anthropic, modelo `claude-haiku-4-5-20251001` | escolha do usuário; mais barato e suficiente para os SELECTs do PRD | Eng. Dados |

&nbsp;

## 6\. Pendências

- Guardar histórico de preço (SCD2)? → fora do escopo de hoje.