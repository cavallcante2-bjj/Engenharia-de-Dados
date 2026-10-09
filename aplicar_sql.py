"""Aplica um arquivo .sql no banco ou executa uma query ad-hoc e imprime o resultado."""
import argparse
import os

import psycopg
from dotenv import load_dotenv


def conectar():
    load_dotenv()
    return psycopg.connect(os.environ["DATABASE_URL"])


def aplicar_arquivo(caminho: str) -> None:
    with open(caminho, "r", encoding="utf-8") as f:
        sql = f.read()
    with conectar() as conn:
        conn.execute(sql)
        conn.commit()
    print(f"OK: {caminho} aplicado.")


def executar_query(query: str) -> None:
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            if cur.description is None:
                print(f"OK: {cur.rowcount} linha(s) afetada(s).")
                conn.commit()
                return
            colunas = [c.name for c in cur.description]
            linhas = cur.fetchall()
    print("\t".join(colunas))
    for linha in linhas:
        print("\t".join(str(v) for v in linha))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arquivo", nargs="?", help="caminho de um arquivo .sql para aplicar")
    parser.add_argument("--query", help="executa uma query ad-hoc e imprime o resultado")
    args = parser.parse_args()

    if args.query:
        executar_query(args.query)
    elif args.arquivo:
        aplicar_arquivo(args.arquivo)
    else:
        parser.error("informe um arquivo .sql ou use --query")


if __name__ == "__main__":
    main()
