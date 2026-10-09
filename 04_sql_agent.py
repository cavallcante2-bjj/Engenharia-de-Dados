"""Agente de linha de comando que responde perguntas de negócio em português consultando prata/ouro via SQL."""
import argparse
import os
import re

import psycopg
from dotenv import load_dotenv

CAMINHO_CONTEXTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CONTEXTO.md")

INSTRUCOES_AGENTE = """\
Você é o agente de dados da Livraria Inteligente. Responda, em português, perguntas de negócio da \
diretoria consultando o banco Postgres descrito abaixo (contexto do negócio + schema real).

Regras:
- Você só pode consultar os schemas `prata` e `ouro`. Nunca gere SQL contra `bronze`.
- A cada resposta sua, gere exatamente um comando SQL, apenas SELECT ou WITH, dentro de um bloco:
```sql
...
```
- Se a pergunta for ambígua ou faltar informação para responder com precisão, não gere SQL: peça \
esclarecimento em português.
- Depois que o resultado da consulta for devolvido a você, responda a pergunta original em \
português, de forma direta, com o número certo.
- Se alguém perguntar algo fora do contexto dos livros e da livraria, NÃO responda e NÃO gere SQL: \
apenas direcione para o tipo de pergunta que você pode responder."""

INSTRUCOES_MINIMAS = """\
Você converte perguntas em SQL para um banco Postgres.

Regras:
- A cada resposta sua, gere exatamente um comando SQL, apenas SELECT ou WITH, dentro de um bloco:
```sql
...
```
- Depois que o resultado da consulta for devolvido a você, responda a pergunta original em \
português, de forma direta."""

PALAVRAS_PROIBIDAS = (
    "insert", "update", "delete", "drop", "alter", "truncate", "grant",
    "revoke", "create", "copy", "call", "vacuum", "analyze", "execute",
    "merge", "into", "do",
)


class AgenteLLM:
    def __init__(self, provider: str, model: str, api_key: str):
        self.provider = provider
        self.model = model
        if provider == "anthropic":
            from anthropic import Anthropic
            self._cliente = Anthropic(api_key=api_key)
        elif provider == "openai":
            from openai import OpenAI
            self._cliente = OpenAI(api_key=api_key)
        else:
            raise ValueError(f"LLM_PROVIDER inválido: {provider!r} (use 'openai' ou 'anthropic')")

    def perguntar(self, system_prompt: str, mensagens: list[dict]) -> str:
        if self.provider == "anthropic":
            resposta = self._cliente.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=mensagens,
            )
            return resposta.content[0].text
        resposta = self._cliente.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}] + mensagens,
        )
        return resposta.choices[0].message.content


def carregar_contexto_md() -> str:
    with open(CAMINHO_CONTEXTO, "r", encoding="utf-8") as f:
        return f.read()


def carregar_esquema(dsn: str, todos: bool) -> str:
    filtro = (
        "table_schema not in ('pg_catalog', 'information_schema')"
        if todos
        else "table_schema in ('prata', 'ouro')"
    )
    query = f"""
        select table_schema, table_name, column_name, data_type
        from information_schema.columns
        where {filtro}
        order by table_schema, table_name, ordinal_position
    """
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            linhas = cur.fetchall()

    tabelas: dict[str, list[str]] = {}
    for schema, tabela, coluna, tipo in linhas:
        tabelas.setdefault(f"{schema}.{tabela}", []).append(f"{coluna} {tipo}")
    return "\n".join(f"{tabela}: {', '.join(colunas)}" for tabela, colunas in tabelas.items())


def montar_prompt_sistema(dsn: str, sem_contexto: bool) -> str:
    if sem_contexto:
        esquema = carregar_esquema(dsn, todos=True)
        return f"{INSTRUCOES_MINIMAS}\n\n## Schema do banco (todas as tabelas)\n{esquema}"
    contexto = carregar_contexto_md()
    esquema = carregar_esquema(dsn, todos=False)
    return f"{INSTRUCOES_AGENTE}\n\n## CONTEXTO.md\n{contexto}\n\n## Schema real (prata e ouro)\n{esquema}"


def extrair_sql(texto: str) -> str | None:
    m = re.search(r"```sql\s*(.*?)```", texto, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else None


def validar_sql(sql: str) -> None:
    corpo = sql.strip().rstrip(";").strip()
    if ";" in corpo:
        raise ValueError("apenas um comando SQL por vez é permitido.")
    if not re.match(r"(?is)^\s*(select|with)\b", corpo):
        raise ValueError("só são permitidos comandos SELECT ou WITH.")
    for palavra in PALAVRAS_PROIBIDAS:
        if re.search(rf"(?i)\b{palavra}\b", corpo):
            raise ValueError(f"comando contém palavra não permitida: {palavra}")


def executar_sql_seguro(sql: str, dsn: str) -> tuple[list[str], list[tuple]]:
    validar_sql(sql)
    with psycopg.connect(dsn) as conn:
        conn.read_only = True
        conn.execute("set statement_timeout = '10s'")
        with conn.cursor() as cur:
            cur.execute(sql)
            colunas = [c.name for c in cur.description]
            linhas = cur.fetchmany(50)
        conn.rollback()
    return colunas, linhas


def formatar_resultado(colunas: list[str], linhas: list[tuple]) -> str:
    if not linhas:
        return "(nenhuma linha)"
    cabecalho = "\t".join(colunas)
    corpo = "\n".join("\t".join(str(v) for v in linha) for linha in linhas)
    return f"{cabecalho}\n{corpo}"


def responder_pergunta(agente: AgenteLLM, system_prompt: str, dsn: str, pergunta: str) -> dict:
    """Roda o loop pergunta → SQL → execução → resposta. Não imprime nada.

    Retorna {"tentativas": [...], "resposta": str}. Cada tentativa tem
    "numero", "sql" e, dependendo do resultado, "colunas"/"linhas" ou "erro".
    """
    tentativas: list[dict] = []
    mensagens = [{"role": "user", "content": pergunta}]
    for numero in range(1, 4):
        resposta_llm = agente.perguntar(system_prompt, mensagens)
        sql = extrair_sql(resposta_llm)
        if sql is None:
            return {"tentativas": tentativas, "resposta": resposta_llm}

        passo = {"numero": numero, "sql": sql}
        mensagens.append({"role": "assistant", "content": resposta_llm})

        try:
            colunas, linhas = executar_sql_seguro(sql, dsn)
        except Exception as erro:
            passo["erro"] = str(erro)
            tentativas.append(passo)
            mensagens.append({
                "role": "user",
                "content": f"Erro ao executar o SQL: {erro}\nGere um novo SQL corrigido, no mesmo formato.",
            })
            continue

        passo["colunas"] = colunas
        passo["linhas"] = linhas
        tentativas.append(passo)

        resultado_texto = formatar_resultado(colunas, linhas)
        mensagens.append({
            "role": "user",
            "content": f"Resultado da consulta:\n{resultado_texto}\n\nResponda a pergunta original em português, de forma direta.",
        })
        resposta_final = agente.perguntar(system_prompt, mensagens)
        return {"tentativas": tentativas, "resposta": resposta_final}

    return {"tentativas": tentativas, "resposta": "Não consegui gerar um SQL válido após 3 tentativas."}


def imprimir_resultado(resultado: dict) -> None:
    for passo in resultado["tentativas"]:
        print(f"\nSQL gerado (tentativa {passo['numero']}):\n{passo['sql']}")
        if "erro" in passo:
            print(f"Erro: {passo['erro']}")
        else:
            print(f"\nResultado:\n{formatar_resultado(passo['colunas'], passo['linhas'])}")
    print(f"\nResposta: {resultado['resposta']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sem-contexto", action="store_true",
        help="usa só a instrução mínima + schema de todas as tabelas (para comparar em aula)",
    )
    args = parser.parse_args()

    load_dotenv()
    dsn = os.environ["DATABASE_URL"]
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    model = os.environ["LLM_MODEL"]
    api_key = (
        os.environ["ANTHROPIC_API_KEY"] if provider == "anthropic" else os.environ["OPENAI_API_KEY"]
    )

    agente = AgenteLLM(provider, model, api_key)
    system_prompt = montar_prompt_sistema(dsn, args.sem_contexto)

    print("Agente SQL da Livraria Inteligente. Digite 'sair' para encerrar.")
    while True:
        try:
            pergunta = input("\nPergunta: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not pergunta or pergunta.lower() in {"sair", "exit", "quit"}:
            break
        resultado = responder_pergunta(agente, system_prompt, dsn, pergunta)
        imprimir_resultado(resultado)


if __name__ == "__main__":
    main()
