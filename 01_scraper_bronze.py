"""Raspa books.toscrape.com e grava o payload cru em bronze.livros."""
import argparse
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import psycopg
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

BASE_URL = "https://books.toscrape.com/catalogue/"
HEADERS = {"User-Agent": "livraria-inteligente-scraper/1.0 (+postech-etl)"}
MAX_WORKERS = 8

DDL = """
create schema if not exists bronze;

create table if not exists bronze.livros (
    id bigserial primary key,
    fonte_url text not null,
    payload jsonb not null,
    _execucao_id text not null,
    _ingestao_em timestamptz not null default now()
);
"""


def listar_urls_dos_livros(sessao: requests.Session, paginas: int) -> list[str]:
    urls = []
    for n in range(1, paginas + 1):
        pagina_url = urljoin(BASE_URL, f"page-{n}.html")
        resp = sessao.get(pagina_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.select("article.product_pod h3 a"):
            urls.append(urljoin(pagina_url, link["href"]))
    return urls


def raspar_detalhe(sessao: requests.Session, url: str) -> dict:
    resp = sessao.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    main = soup.find("div", class_="product_main")
    titulo = main.find("h1").get_text()
    preco_raw = main.find("p", class_="price_color").get_text()
    rating_raw = main.find("p", class_="star-rating")["class"][1]

    tabela = {
        linha.find("th").get_text(): linha.find("td").get_text()
        for linha in soup.select("table.table tr")
    }

    breadcrumb = soup.select("ul.breadcrumb li a")
    categoria_raw = breadcrumb[2].get_text() if len(breadcrumb) > 2 else ""

    descricao_tag = soup.find("div", id="product_description")
    descricao = descricao_tag.find_next("p").get_text() if descricao_tag else ""

    return {
        "url": url,
        "titulo": titulo,
        "preco_raw": preco_raw,
        "rating_raw": rating_raw,
        "estoque_raw": tabela.get("Availability", ""),
        "upc": tabela.get("UPC", ""),
        "n_reviews_raw": tabela.get("Number of reviews", ""),
        "categoria_raw": categoria_raw,
        "descricao": descricao,
    }


def gravar_bronze(payloads: list[dict], execucao_id: str, dsn: str) -> None:
    with psycopg.connect(dsn) as conn:
        conn.execute(DDL)
        with conn.cursor() as cur:
            cur.executemany(
                """
                insert into bronze.livros (fonte_url, payload, _execucao_id)
                values (%s, %s, %s)
                """,
                [
                    (p["url"], psycopg.types.json.Json(p), execucao_id)
                    for p in payloads
                ],
            )
        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paginas", type=int, default=1, help="quantidade de páginas de listagem (20 livros cada)")
    args = parser.parse_args()

    load_dotenv()
    dsn = os.environ["DATABASE_URL"]
    execucao_id = uuid.uuid4().hex

    with requests.Session() as sessao:
        urls = listar_urls_dos_livros(sessao, args.paginas)
        print(f"{len(urls)} livro(s) encontrado(s) em {args.paginas} página(s).")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            payloads = list(pool.map(lambda u: raspar_detalhe(sessao, u), urls))

    gravar_bronze(payloads, execucao_id, dsn)
    print(f"OK: {len(payloads)} linha(s) gravada(s) em bronze.livros (execucao_id={execucao_id}).")


if __name__ == "__main__":
    main()
