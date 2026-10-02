import os
import re

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL não encontrada no ficheiro .env"
    )


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


OPEN_LIBRARY_BOOKS_URL = "https://openlibrary.org/api/books"
OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"


def normalizar_isbn(isbn):
    return re.sub(
        r"[^0-9Xx]",
        "",
        str(isbn or ""),
    ).upper()


def procurar_livro_local(isbn):
    isbn_limpo = normalizar_isbn(isbn)

    if len(isbn_limpo) not in (10, 13):
        return None

    query = text("""
        SELECT
            l.id,
            l.titulo,
            l.isbn,
            l.editora,
            l.data_publicacao,
            l.preco_venda,
            l.estoque_atual,
            l.qtd_reservada,
            GREATEST(
                l.estoque_atual - l.qtd_reservada,
                0
            ) AS stock_disponivel,
            COALESCE(
                (
                    SELECT STRING_AGG(
                        a.nome,
                        ', '
                        ORDER BY a.nome
                    )
                    FROM public.livro_autores la
                    JOIN public.autores a
                        ON a.id = la.autor_id
                    WHERE la.livro_id = l.id
                ),
                ''
            ) AS autores,
            COALESCE(
                (
                    SELECT ARRAY_AGG(
                        g.nome
                        ORDER BY g.nome
                    )
                    FROM public.livro_generos lg
                    JOIN public.generos g
                        ON g.id = lg.genero_id
                    WHERE lg.livro_id = l.id
                ),
                ARRAY[]::varchar[]
            ) AS generos
        FROM public.livros l
        WHERE REGEXP_REPLACE(
            UPPER(l.isbn),
            '[^0-9X]',
            '',
            'g'
        ) = :isbn
        LIMIT 1;
    """)

    with engine.connect() as connection:
        resultado = (
            connection.execute(
                query,
                {
                    "isbn": isbn_limpo,
                },
            )
            .mappings()
            .first()
        )

    if not resultado:
        return None

    autores = [
        nome.strip()
        for nome in str(resultado["autores"] or "").split(",")
        if nome.strip()
    ]

    return {
        "sucesso": True,
        "origem": "Base de Dados Local",
        "id": int(resultado["id"]),
        "titulo": resultado["titulo"],
        "isbn": resultado["isbn"],
        "autores": autores,
        "editora": resultado["editora"],
        "data_publicacao": (
            resultado["data_publicacao"].isoformat()
            if resultado["data_publicacao"]
            else None
        ),
        "preco_venda": float(resultado["preco_venda"]),
        "estoque_atual": int(resultado["estoque_atual"]),
        "qtd_reservada": int(resultado["qtd_reservada"]),
        "stock_disponivel": int(resultado["stock_disponivel"]),
        "generos": list(resultado["generos"] or []),
    }


def _obter_json(url, parametros):
    endereco = f"{url}?{urlencode(parametros)}"
    pedido = Request(
        endereco,
        headers={
            "User-Agent": "SABIN-PAP/1.0",
        },
    )

    with urlopen(pedido, timeout=8) as resposta:
        return json.loads(
            resposta.read().decode("utf-8")
        )


def _consultar_books_api(isbn):
    chave = f"ISBN:{isbn}"

    dados = _obter_json(
        OPEN_LIBRARY_BOOKS_URL,
        {
            "bibkeys": chave,
            "jscmd": "data",
            "format": "json",
        },
    )

    return dados.get(chave)


def _consultar_search_api(isbn):
    dados = _obter_json(
        OPEN_LIBRARY_SEARCH_URL,
        {
            "isbn": isbn,
            "limit": 1,
            "fields": (
                "title,author_name,publisher,first_publish_year,subject"
            ),
        },
    )

    documentos = dados.get("docs") or []

    if not documentos:
        return None

    return documentos[0]


def procurar_livro_open_library(isbn):
    isbn_limpo = normalizar_isbn(isbn)

    if len(isbn_limpo) not in (10, 13):
        return {
            "sucesso": False,
            "erro": "O ISBN deve ter 10 ou 13 caracteres válidos.",
        }

    dados_livro = None
    dados_pesquisa = None

    try:
        dados_livro = _consultar_books_api(
            isbn_limpo
        )
    except (HTTPError, URLError, TimeoutError, ValueError):
        dados_livro = None

    try:
        dados_pesquisa = _consultar_search_api(
            isbn_limpo
        )
    except (HTTPError, URLError, TimeoutError, ValueError):
        dados_pesquisa = None

    if not dados_livro and not dados_pesquisa:
        return {
            "sucesso": False,
            "erro": "ISBN não encontrado na Open Library.",
        }

    titulo = None
    autores = []
    editora = None
    data_publicacao = None
    generos = []

    if dados_livro:
        titulo = dados_livro.get("title")

        autores = [
            autor.get("name")
            for autor in dados_livro.get("authors", [])
            if autor.get("name")
        ]

        editoras = dados_livro.get("publishers") or []
        if editoras:
            editora = editoras[0].get("name")

        data_publicacao = dados_livro.get("publish_date")

        generos = [
            assunto.get("name")
            for assunto in dados_livro.get("subjects", [])
            if assunto.get("name")
        ]

    if dados_pesquisa:
        if not titulo:
            titulo = dados_pesquisa.get("title")

        if not autores:
            autores = dados_pesquisa.get("author_name") or []

        if not editora:
            editoras = dados_pesquisa.get("publisher") or []
            if editoras:
                editora = editoras[0]

        if not data_publicacao:
            ano = dados_pesquisa.get("first_publish_year")
            if ano:
                data_publicacao = str(ano)

        assuntos_pesquisa = dados_pesquisa.get("subject") or []

        nomes_existentes = {
            str(genero).strip().lower()
            for genero in generos
        }

        for assunto in assuntos_pesquisa:
            assunto_texto = str(assunto or "").strip()

            if (
                assunto_texto
                and assunto_texto.lower() not in nomes_existentes
            ):
                generos.append(assunto_texto)
                nomes_existentes.add(
                    assunto_texto.lower()
                )

    return {
        "sucesso": True,
        "origem": "Open Library API",
        "titulo": titulo or "Sem título",
        "isbn": isbn_limpo,
        "autores": autores,
        "editora": editora,
        "data_publicacao": data_publicacao,
        "generos": generos,
    }


def procurar_livro(isbn):
    isbn_limpo = normalizar_isbn(isbn)

    if len(isbn_limpo) not in (10, 13):
        return {
            "sucesso": False,
            "erro": "O ISBN deve ter 10 ou 13 caracteres válidos.",
        }

    local = procurar_livro_local(
        isbn_limpo
    )

    if local:
        return local

    return procurar_livro_open_library(
        isbn_limpo
    )
