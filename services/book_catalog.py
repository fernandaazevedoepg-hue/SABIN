import os
import re

import json
import html as html_lib
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
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
GOOGLE_BOOKS_VOLUMES_URL = "https://www.googleapis.com/books/v1/volumes"
PRESENCA_SEARCH_URL = "https://www.presenca.pt/search"
PRESENCA_SUGGEST_URL = "https://www.presenca.pt/search/suggest.json"
PRESENCA_BASE_URL = "https://www.presenca.pt"


def normalizar_isbn(isbn):
    return re.sub(
        r"[^0-9Xx]",
        "",
        str(isbn or ""),
    ).upper()


def isbn13_para_isbn10(isbn):
    isbn_limpo = normalizar_isbn(isbn)

    if (
        len(isbn_limpo) != 13
        or not isbn_limpo.startswith("978")
        or not isbn_limpo.isdigit()
    ):
        return None

    corpo = isbn_limpo[3:12]
    soma = 0

    for indice, digito in enumerate(corpo):
        peso = 10 - indice
        soma += int(digito) * peso

    resto = 11 - (soma % 11)

    if resto == 10:
        digito_controle = "X"
    elif resto == 11:
        digito_controle = "0"
    else:
        digito_controle = str(resto)

    return corpo + digito_controle


def variantes_isbn(isbn):
    isbn_limpo = normalizar_isbn(isbn)
    variantes = []

    if len(isbn_limpo) in (10, 13):
        variantes.append(isbn_limpo)

    isbn10 = isbn13_para_isbn10(isbn_limpo)

    if isbn10 and isbn10 not in variantes:
        variantes.append(isbn10)

    return variantes


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


def _obter_texto(url, parametros=None):
    if parametros:
        endereco = f"{url}?{urlencode(parametros)}"
    else:
        endereco = url

    pedido = Request(
        endereco,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/120 Safari/537.36"
            ),
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
        },
    )

    with urlopen(pedido, timeout=10) as resposta:
        return resposta.read().decode(
            "utf-8",
            errors="ignore",
        )


def _limpar_html(valor):
    if not valor:
        return ""

    texto = re.sub(
        r"<[^>]+>",
        " ",
        str(valor),
    )
    texto = html_lib.unescape(texto)
    texto = re.sub(
        r"\s+",
        " ",
        texto,
    ).strip()

    return texto


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
    consultas = [
        {
            "isbn": isbn,
            "limit": 1,
            "fields": (
                "title,author_name,publisher,first_publish_year,subject"
            ),
        },
        {
            "q": isbn,
            "limit": 1,
            "fields": (
                "title,author_name,publisher,first_publish_year,subject,isbn"
            ),
        },
    ]

    for parametros in consultas:
        dados = _obter_json(
            OPEN_LIBRARY_SEARCH_URL,
            parametros,
        )

        documentos = dados.get("docs") or []

        if documentos:
            return documentos[0]

    return None


def procurar_livro_open_library(isbn):
    isbn_limpo = normalizar_isbn(isbn)

    if len(isbn_limpo) not in (10, 13):
        return {
            "sucesso": False,
            "erro": "O ISBN deve ter 10 ou 13 caracteres válidos.",
        }

    dados_livro = None
    dados_pesquisa = None

    for variante in variantes_isbn(isbn_limpo):
        if not dados_livro:
            try:
                dados_livro = _consultar_books_api(
                    variante
                )
            except (
                HTTPError,
                URLError,
                TimeoutError,
                ValueError,
            ):
                dados_livro = None

        if not dados_pesquisa:
            try:
                dados_pesquisa = _consultar_search_api(
                    variante
                )
            except (
                HTTPError,
                URLError,
                TimeoutError,
                ValueError,
            ):
                dados_pesquisa = None

        if dados_livro or dados_pesquisa:
            break

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
            primeira = editoras[0]
            if isinstance(primeira, dict):
                editora = primeira.get("name")
            else:
                editora = str(primeira)

        data_publicacao = dados_livro.get("publish_date")

        generos = [
            assunto.get("name")
            for assunto in dados_livro.get("subjects", [])
            if isinstance(assunto, dict) and assunto.get("name")
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



def procurar_livro_google_books(isbn):
    isbn_limpo = normalizar_isbn(isbn)

    if len(isbn_limpo) not in (10, 13):
        return {
            "sucesso": False,
            "erro": "O ISBN deve ter 10 ou 13 caracteres válidos.",
        }

    variantes = variantes_isbn(isbn_limpo)
    consultas = []

    for variante in variantes:
        consultas.append(f"isbn:{variante}")

    for variante in variantes:
        consultas.append(variante)

    info_escolhida = None

    for consulta in consultas:
        try:
            dados = _obter_json(
                GOOGLE_BOOKS_VOLUMES_URL,
                {
                    "q": consulta,
                    "maxResults": 5,
                    "printType": "books",
                },
            )
        except (
            HTTPError,
            URLError,
            TimeoutError,
            ValueError,
        ):
            continue

        itens = dados.get("items") or []

        if not itens:
            continue

        for item in itens:
            info = item.get("volumeInfo") or {}
            identificadores = info.get("industryIdentifiers") or []

            valores = {
                normalizar_isbn(
                    identificador.get("identifier")
                )
                for identificador in identificadores
                if identificador.get("identifier")
            }

            if any(
                variante in valores
                for variante in variantes
            ):
                info_escolhida = info
                break

        if info_escolhida:
            break

        if itens:
            info_escolhida = (
                itens[0].get("volumeInfo") or {}
            )
            break

    if not info_escolhida:
        return {
            "sucesso": False,
            "erro": "ISBN não encontrado na Google Books.",
        }

    info = info_escolhida
    identificadores = info.get("industryIdentifiers") or []
    isbn_resultado = isbn_limpo

    for identificador in identificadores:
        valor = normalizar_isbn(
            identificador.get("identifier")
        )

        if len(valor) == 13:
            isbn_resultado = valor
            break

        if len(valor) == 10:
            isbn_resultado = valor

    return {
        "sucesso": True,
        "origem": "Google Books API",
        "titulo": info.get("title") or "Sem título",
        "isbn": isbn_resultado,
        "autores": info.get("authors") or [],
        "editora": info.get("publisher"),
        "data_publicacao": info.get("publishedDate"),
        "generos": info.get("categories") or [],
    }



def procurar_livro_presenca(isbn):
    isbn_limpo = normalizar_isbn(isbn)

    if len(isbn_limpo) not in (10, 13):
        return {
            "sucesso": False,
            "erro": "O ISBN deve ter 10 ou 13 caracteres válidos.",
        }

    links_produto = []

    try:
        sugestoes = _obter_json(
            PRESENCA_SUGGEST_URL,
            {
                "q": isbn_limpo,
                "resources[type]": "product",
                "resources[limit]": 10,
            },
        )

        produtos = (
            sugestoes
            .get("resources", {})
            .get("results", {})
            .get("products", [])
        )

        for produto in produtos:
            url_produto = produto.get("url")

            if url_produto:
                links_produto.append(
                    urljoin(
                        PRESENCA_BASE_URL,
                        url_produto,
                    )
                )

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
    ):
        pass

    if not links_produto:
        try:
            html_busca = _obter_texto(
                PRESENCA_SEARCH_URL,
                {
                    "q": isbn_limpo,
                    "type": "product",
                },
            )

            encontrados = re.findall(
                r'href=["\']([^"\']*/products/[^"\'?#]+)["\']',
                html_busca,
                flags=re.I,
            )

            for link in encontrados:
                url_produto = urljoin(
                    PRESENCA_BASE_URL,
                    link,
                )

                if url_produto not in links_produto:
                    links_produto.append(
                        url_produto
                    )

        except (
            HTTPError,
            URLError,
            TimeoutError,
            ValueError,
        ):
            pass

    for url_produto in links_produto[:10]:
        try:
            pagina = _obter_texto(
                url_produto
            )
        except (
            HTTPError,
            URLError,
            TimeoutError,
            ValueError,
        ):
            continue

        pagina_normalizada = normalizar_isbn(
            pagina
        )

        if isbn_limpo not in pagina_normalizada:
            continue

        h1 = re.search(
            r"<h1[^>]*>(.*?)</h1>",
            pagina,
            flags=re.I | re.S,
        )

        titulo = (
            _limpar_html(h1.group(1))
            if h1
            else None
        )

        segmento_inicio = (
            h1.start()
            if h1
            else 0
        )

        segmento = pagina[
            segmento_inicio:
            segmento_inicio + 12000
        ]

        autor_match = re.search(
            r'href=["\'][^"\']*/blogs/autores/[^"\']+["\'][^>]*>(.*?)</a>',
            segmento,
            flags=re.I | re.S,
        )

        autores = []

        if autor_match:
            autor = _limpar_html(
                autor_match.group(1)
            )

            if autor:
                autores.append(
                    autor
                )

        vendor_match = re.search(
            r'"vendor"\s*:\s*"([^"]+)"',
            pagina,
            flags=re.I,
        )

        editora = (
            html_lib.unescape(
                vendor_match.group(1)
            ).strip()
            if vendor_match
            else None
        )

        texto_produto = _limpar_html(
            segmento
        )

        data_match = re.search(
            (
                r"Data\s+de\s+Lançamento\s+"
                r"([0-9]{1,2}/[0-9]{4}|"
                r"[A-Za-zÀ-ÿ]+\s+[0-9]{4}|"
                r"[0-9]{4})"
            ),
            texto_produto,
            flags=re.I,
        )

        data_publicacao = (
            data_match.group(1)
            if data_match
            else None
        )

        generos = []

        categoria_match = re.search(
            r"Categoria\s+(.+?)\s+Sub-categoria",
            texto_produto,
            flags=re.I,
        )

        if categoria_match:
            categoria = (
                categoria_match
                .group(1)
                .strip(" -")
            )

            if categoria:
                generos.append(
                    categoria
                )

        subcategoria_match = re.search(
            r"Sub-categoria\s+(.+?)\s+Série",
            texto_produto,
            flags=re.I,
        )

        if subcategoria_match:
            subcategoria = (
                subcategoria_match
                .group(1)
                .strip(" -")
            )

            if subcategoria:
                generos.append(
                    subcategoria
                )

        if not titulo:
            continue

        return {
            "sucesso": True,
            "origem": "Catálogo Editorial Presença",
            "titulo": titulo,
            "isbn": isbn_limpo,
            "autores": autores,
            "editora": editora,
            "data_publicacao": data_publicacao,
            "generos": generos,
        }

    return {
        "sucesso": False,
        "erro": (
            "ISBN não encontrado no catálogo editorial adicional."
        ),
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

    externo = procurar_livro_open_library(
        isbn_limpo
    )

    if externo.get("sucesso"):
        return externo

    google = procurar_livro_google_books(
        isbn_limpo
    )

    if google.get("sucesso"):
        return google

    presenca = procurar_livro_presenca(
        isbn_limpo
    )

    if presenca.get("sucesso"):
        return presenca

    return {
        "sucesso": False,
        "erro": (
            "ISBN não encontrado nas fontes externas consultadas."
        ),
    }
