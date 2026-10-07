import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from html import unescape
from urllib.parse import urlparse

import requests
from ddgs import DDGS
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from sqlalchemy import create_engine, text
from urllib3.util.retry import Retry


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL não encontrada no ficheiro .env")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_BOOKS_URL = "https://openlibrary.org/api/books"
OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"

TIMEOUT_API = 4
TIMEOUT_WEB = 4
TIMEOUT_SEARCH = 5

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)

session = requests.Session()
session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
    }
)

retry = Retry(
    total=1,
    connect=1,
    read=1,
    backoff_factor=0.2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET"]),
)

adapter = HTTPAdapter(max_retries=retry)
session.mount("https://", adapter)
session.mount("http://", adapter)

MESES = {
    "janeiro": 1,
    "jan": 1,
    "january": 1,
    "fevereiro": 2,
    "fev": 2,
    "feb": 2,
    "february": 2,
    "marco": 3,
    "mar": 3,
    "march": 3,
    "abril": 4,
    "abr": 4,
    "apr": 4,
    "april": 4,
    "maio": 5,
    "mai": 5,
    "may": 5,
    "junho": 6,
    "jun": 6,
    "june": 6,
    "julho": 7,
    "jul": 7,
    "july": 7,
    "agosto": 8,
    "ago": 8,
    "aug": 8,
    "august": 8,
    "setembro": 9,
    "set": 9,
    "sep": 9,
    "september": 9,
    "outubro": 10,
    "out": 10,
    "oct": 10,
    "october": 10,
    "novembro": 11,
    "nov": 11,
    "november": 11,
    "dezembro": 12,
    "dez": 12,
    "dec": 12,
    "december": 12,
}

GENERO_ALIASES = [
    ("Realismo Mágico", ("realismo magico", "magical realism")),
    ("Ficção Científica", ("ficcao cientifica", "science fiction", "sci fi")),
    ("Autoajuda", ("autoajuda", "self help", "personal development")),
    ("Distopia", ("distopia", "dystopia", "dystopian")),
    ("Policial", ("policial", "detective fiction", "crime fiction", "mystery fiction")),
    ("Poesia", ("poesia", "poetry", "poems")),
    ("Fantasia", ("fantasia", "fantasy")),
    ("Terror", ("terror", "horror")),
    ("Suspense", ("suspense", "thriller")),
    ("Biografia", ("biografia", "biography", "autobiography", "memoir")),
    ("Infantil", ("infantil", "juvenil", "juvenile", "children", "kids", "young adult")),
    ("Aventura", ("aventura", "adventure")),
    ("Romance", ("romance", "romantic fiction", "love stories")),
    ("Ficção", ("ficcao", "fiction", "novel")),
]


def normalizar_isbn(isbn):
    return re.sub(
        r"[^0-9Xx]",
        "",
        str(isbn or ""),
    ).upper()


def isbn13_para_isbn10(isbn):
    isbn = normalizar_isbn(isbn)

    if len(isbn) != 13 or not isbn.startswith("978") or not isbn.isdigit():
        return None

    corpo = isbn[3:12]
    soma = sum(
        int(digito) * (10 - indice)
        for indice, digito in enumerate(corpo)
    )

    resto = 11 - (soma % 11)

    if resto == 10:
        controlo = "X"
    elif resto == 11:
        controlo = "0"
    else:
        controlo = str(resto)

    return corpo + controlo


def variantes_isbn(isbn):
    isbn = normalizar_isbn(isbn)
    variantes = []

    if len(isbn) in (10, 13):
        variantes.append(isbn)

    isbn10 = isbn13_para_isbn10(isbn)

    if isbn10 and isbn10 not in variantes:
        variantes.append(isbn10)

    return variantes


def isbn_valido(isbn):
    isbn = normalizar_isbn(isbn)

    if len(isbn) == 10:
        if not re.fullmatch(r"\d{9}[\dX]", isbn):
            return False

        soma = 0

        for indice, caractere in enumerate(isbn):
            valor = 10 if caractere == "X" else int(caractere)
            soma += valor * (10 - indice)

        return soma % 11 == 0

    if len(isbn) == 13:
        if not isbn.isdigit():
            return False

        soma = sum(
            int(digito) * (1 if indice % 2 == 0 else 3)
            for indice, digito in enumerate(isbn[:12])
        )

        controlo = (10 - soma % 10) % 10
        return controlo == int(isbn[-1])

    return False


def sem_acentos(valor):
    texto = unicodedata.normalize(
        "NFKD",
        str(valor or ""),
    )

    return "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )


def limpar_texto(valor):
    texto = unescape(str(valor or ""))

    texto = re.sub(
        r"<[^>]+>",
        " ",
        texto,
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip(" \t\r\n|,:;")


def normalizar_texto(valor):
    return re.sub(
        r"\s+",
        " ",
        sem_acentos(
            limpar_texto(valor)
        ).lower(),
    ).strip()


def limpar_autor(nome):
    nome = limpar_texto(nome)

    if not nome:
        return None

    nome = re.sub(
        r"\s*\((?:autor|autora|author|writer)\)\s*",
        " ",
        nome,
        flags=re.I,
    )

    nome = re.split(
        r"\s+(?:Formato|Format|Encaderna[cç][aã]o|Binding|Editora|Publisher|ISBN|EAN|Data|Date)\s*:",
        nome,
        maxsplit=1,
        flags=re.I,
    )[0].strip()

    nome = re.sub(
        r"\s+(?:Editorial|Editora|Publisher|Author|Autor)\s*$",
        "",
        nome,
        flags=re.I,
    ).strip()

    if "," in nome:
        partes = [
            parte.strip()
            for parte in nome.split(",")
            if parte.strip()
        ]

        if (
            len(partes) == 2
            and all(len(parte.split()) <= 3 for parte in partes)
        ):
            nome = f"{partes[1]} {partes[0]}"

    nome = re.sub(r"\s+", " ", nome).strip(" .,:;|-_")
    normalizado = normalizar_texto(nome)

    proibidos = (
        "using the web site",
        "using this website",
        "storygraph",
        "goodreads",
        "formato",
        "capa comum",
        "terms and conditions",
        "privacy policy",
        "cookie",
    )

    if any(item in normalizado for item in proibidos):
        return None

    if re.search(r"https?://|[$€£]|\d", nome, flags=re.I):
        return None

    if len(nome) < 2 or len(nome) > 90:
        return None

    return nome


def limpar_autores(autores):
    resultado = []
    vistos = set()

    for autor in autores or []:
        autor = limpar_autor(autor)

        if not autor:
            continue

        chave = normalizar_texto(autor)

        if chave not in vistos:
            vistos.add(chave)
            resultado.append(autor)

    return resultado[:4]


def limpar_editora(editora):
    editora = limpar_texto(editora)

    if not editora:
        return None

    editora = re.sub(
        r"^\s*(?:editorial|editora|editor|publisher)\s*:?\s*",
        "",
        editora,
        flags=re.I,
    )

    editora = re.sub(
        r"\s*[,;|-]?\s*\b(?:19|20)\d{2}\b\s*$",
        "",
        editora,
    ).strip(" [](){}.,;|-")

    compacto = re.sub(
        r"[^a-z0-9]",
        "",
        sem_acentos(editora).lower(),
    )

    conhecidos = {
        "casadasletras": "Casa das Letras",
        "companhiadasletras": "Companhia das Letras",
        "editorialpresenca": "Editorial Presença",
        "editorapresenca": "Editorial Presença",
        "presenca": "Editorial Presença",
        "astralcultural": "Astral Cultural",
        "booksmile": "Booksmile",
        "portoeditora": "Porto Editora",
        "penguinrandomhouse": "Penguin Random House",
        "harpercollins": "HarperCollins",
        "intrinseca": "Intrínseca",
        "rocco": "Rocco",
        "record": "Record",
        "leya": "Leya",
        "manuscrito": "Manuscrito Editora",
        "manuscritoeditora": "Manuscrito Editora",
        "vintagebooks": "Vintage Books",
    }

    if compacto in conhecidos:
        return conhecidos[compacto]

    if len(editora) > 90:
        return None

    return editora


def limpar_titulo(titulo, isbn=None, autores=None):
    titulo = limpar_texto(titulo)

    if not titulo:
        return None

    isbn_limpo = normalizar_isbn(isbn)

    if isbn_limpo:
        titulo = re.sub(
            rf"\s*\(\s*{re.escape(isbn_limpo)}\s*\)\s*$",
            "",
            titulo,
            flags=re.I,
        )

        titulo = re.sub(
            rf"\s*[-|–—:]\s*{re.escape(isbn_limpo)}\s*$",
            "",
            titulo,
            flags=re.I,
        )

    titulo = re.sub(
        r"\s*\([^)]*(?:edi[cç][aã]o|edition|hardcover|paperback|capa dura|brochura|kindle|ebook)[^)]*\)\s*",
        " ",
        titulo,
        flags=re.I,
    )

    titulo = re.sub(
        r"\s+(?:um|uma)\s+(?:romance|livro|hist[oó]ria)\s+(?:com|de)\s+.+$",
        "",
        titulo,
        flags=re.I,
    )

    titulo = re.sub(
        r"\s*[-|–—:]\s*(?:hardcover|paperback|capa dura|brochura|ebook|kindle edition)\s*$",
        "",
        titulo,
        flags=re.I,
    )

    titulo = re.sub(
        r"\s*[-|–—:]\s*(?:amazon(?:\.[a-z.]+)?|wook|bertrand|fnac|skoob|storygraph|the storygraph|goodreads|bookroo)(?:\s*[:|-]\s*books?)?.*$",
        "",
        titulo,
        flags=re.I,
    )

    for autor in autores or []:
        autor = limpar_texto(autor)

        if autor:
            titulo = re.sub(
                rf"\s*[-|–—]\s*{re.escape(autor)}\s*$",
                "",
                titulo,
                flags=re.I,
            )

    titulo = re.sub(r"\s+", " ", titulo).strip(" .|:-–—")

    if len(titulo) < 2 or len(titulo) > 180:
        return None

    normalizado = normalizar_texto(titulo)

    if normalizado.startswith(
        (
            "editions for ",
            "editions of ",
            "reviews for ",
        )
    ):
        return None

    return titulo


def normalizar_data(valor):
    if not valor:
        return None

    original = limpar_texto(valor)
    normalizado = normalizar_texto(original)

    encontrado = re.search(
        r"\b(19\d{2}|20\d{2})[-/.](0?[1-9]|1[0-2])(?:[-/.](0?[1-9]|[12]\d|3[01]))?\b",
        normalizado,
    )

    if encontrado:
        ano = int(encontrado.group(1))
        mes = int(encontrado.group(2))
        dia = int(encontrado.group(3) or 1)
        return f"{ano:04d}-{mes:02d}-{dia:02d}"

    encontrado = re.search(
        r"\b(0?[1-9]|[12]\d|3[01])[-/.](0?[1-9]|1[0-2])[-/.](19\d{2}|20\d{2})\b",
        normalizado,
    )

    if encontrado:
        dia = int(encontrado.group(1))
        mes = int(encontrado.group(2))
        ano = int(encontrado.group(3))
        return f"{ano:04d}-{mes:02d}-{dia:02d}"

    encontrado = re.search(
        r"\b(0?[1-9]|1[0-2])[-/.](19\d{2}|20\d{2})\b",
        normalizado,
    )

    if encontrado:
        mes = int(encontrado.group(1))
        ano = int(encontrado.group(2))
        return f"{ano:04d}-{mes:02d}-01"

    for nome_mes, numero_mes in MESES.items():
        encontrado = re.search(
            rf"\b{re.escape(nome_mes)}\b(?:\s+(?:de|of))?\s+(19\d{{2}}|20\d{{2}})\b",
            normalizado,
        )

        if encontrado:
            ano = int(encontrado.group(1))
            return f"{ano:04d}-{numero_mes:02d}-01"

    encontrado = re.search(
        r"\b(19\d{2}|20\d{2})\b",
        normalizado,
    )

    if encontrado:
        return f"{int(encontrado.group(1)):04d}-01-01"

    return None


def mapear_generos(valores):
    texto = " | ".join(
        str(valor)
        for valor in valores or []
        if valor
    )

    normalizado = normalizar_texto(texto)

    if not normalizado:
        return []

    encontrados = []

    for nome, aliases in GENERO_ALIASES:
        if any(
            re.search(
                rf"\b{re.escape(alias)}\b",
                normalizado,
            )
            for alias in aliases
        ):
            if nome not in encontrados:
                encontrados.append(nome)

    if "nao ficcao" in normalizado and "Ficção" in encontrados:
        encontrados.remove("Ficção")

    return encontrados[:3]


def procurar_livro_local(isbn):
    isbn = normalizar_isbn(isbn)

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
                {"isbn": isbn},
            )
            .mappings()
            .first()
        )

    if not resultado:
        return None

    autores = [
        parte.strip()
        for parte in str(resultado["autores"] or "").split(",")
        if parte.strip()
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
        "generos": list(resultado["generos"] or []),
    }


def get_json(url, params):
    resposta = session.get(
        url,
        params=params,
        timeout=TIMEOUT_API,
    )

    resposta.raise_for_status()
    return resposta.json()


def procurar_google_books(isbn):
    isbn = normalizar_isbn(isbn)
    variantes = variantes_isbn(isbn)

    for variante in variantes:
        try:
            dados = get_json(
                GOOGLE_BOOKS_URL,
                {
                    "q": f"isbn:{variante}",
                    "maxResults": 10,
                    "printType": "books",
                },
            )
        except Exception:
            continue

        for item in dados.get("items") or []:
            info = item.get("volumeInfo") or {}
            identificadores = info.get("industryIdentifiers") or []

            valores = {
                normalizar_isbn(identificador.get("identifier"))
                for identificador in identificadores
                if identificador.get("identifier")
            }

            if not any(item_isbn in valores for item_isbn in variantes):
                continue

            autores = limpar_autores(info.get("authors") or [])
            titulo = limpar_titulo(
                info.get("title"),
                isbn,
                autores,
            )

            if not titulo:
                continue

            return {
                "sucesso": True,
                "origem": "Google Books API",
                "prioridade": 100,
                "titulo": titulo,
                "isbn": isbn,
                "autores": autores,
                "editora": limpar_editora(info.get("publisher")),
                "data_publicacao": normalizar_data(info.get("publishedDate")),
                "generos": mapear_generos(info.get("categories") or []),
            }

    return {
        "sucesso": False,
        "origem": "Google Books API",
    }


def procurar_open_library(isbn):
    isbn = normalizar_isbn(isbn)
    variantes = variantes_isbn(isbn)

    livro = None
    documento = None

    for variante in variantes:
        try:
            chave = f"ISBN:{variante}"

            dados = get_json(
                OPEN_LIBRARY_BOOKS_URL,
                {
                    "bibkeys": chave,
                    "jscmd": "data",
                    "format": "json",
                },
            )

            livro = dados.get(chave) or livro
        except Exception:
            pass

        try:
            dados = get_json(
                OPEN_LIBRARY_SEARCH_URL,
                {
                    "isbn": variante,
                    "limit": 5,
                    "fields": (
                        "title,"
                        "author_name,"
                        "publisher,"
                        "first_publish_year,"
                        "subject,"
                        "isbn"
                    ),
                },
            )

            for candidato in dados.get("docs") or []:
                isbns = {
                    normalizar_isbn(valor)
                    for valor in candidato.get("isbn") or []
                    if valor
                }

                if set(variantes) & isbns:
                    documento = candidato
                    break
        except Exception:
            pass

        if livro or documento:
            break

    if not livro and not documento:
        return {
            "sucesso": False,
            "origem": "Open Library API",
        }

    titulo = None
    autores = []
    editora = None
    data_publicacao = None
    assuntos = []

    if livro:
        titulo = livro.get("title")

        autores = [
            autor.get("name")
            for autor in livro.get("authors") or []
            if isinstance(autor, dict) and autor.get("name")
        ]

        editoras = livro.get("publishers") or []

        if editoras:
            primeira = editoras[0]
            editora = (
                primeira.get("name")
                if isinstance(primeira, dict)
                else str(primeira)
            )

        data_publicacao = livro.get("publish_date")

        assuntos.extend(
            assunto.get("name")
            for assunto in livro.get("subjects") or []
            if isinstance(assunto, dict) and assunto.get("name")
        )

    if documento:
        titulo = titulo or documento.get("title")
        autores = autores or documento.get("author_name") or []

        if not editora:
            editoras = documento.get("publisher") or []
            editora = editoras[0] if editoras else None

        if not data_publicacao and documento.get("first_publish_year"):
            data_publicacao = str(documento.get("first_publish_year"))

        assuntos.extend(documento.get("subject") or [])

    autores = limpar_autores(autores)

    titulo = limpar_titulo(
        titulo,
        isbn,
        autores,
    )

    if not titulo:
        return {
            "sucesso": False,
            "origem": "Open Library API",
        }

    return {
        "sucesso": True,
        "origem": "Open Library API",
        "prioridade": 90,
        "titulo": titulo,
        "isbn": isbn,
        "autores": autores,
        "editora": limpar_editora(editora),
        "data_publicacao": normalizar_data(data_publicacao),
        "generos": mapear_generos(assuntos),
    }


def extrair_json_ld(html, isbn):
    blocos = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    )

    resultados = []

    for bloco in blocos:
        try:
            dados = json.loads(
                unescape(bloco).strip()
            )
        except Exception:
            continue

        pilha = [dados]

        while pilha:
            atual = pilha.pop()

            if isinstance(atual, list):
                pilha.extend(atual)
                continue

            if not isinstance(atual, dict):
                continue

            pilha.extend(
                valor
                for valor in atual.values()
                if isinstance(valor, (dict, list))
            )

            tipo = atual.get("@type")

            tipos = (
                tipo
                if isinstance(tipo, list)
                else [tipo]
            )

            tipos = {
                normalizar_texto(item)
                for item in tipos
                if item
            }

            if not ({"book", "product"} & tipos):
                continue

            isbn_objeto = normalizar_isbn(
                atual.get("isbn")
                or atual.get("gtin13")
                or atual.get("gtin")
                or ""
            )

            if isbn_objeto and isbn_objeto != isbn:
                continue

            def nomes(valor):
                if not valor:
                    return []

                if isinstance(valor, str):
                    return [valor]

                if isinstance(valor, dict):
                    nome = valor.get("name") or valor.get("title")
                    return [nome] if nome else []

                if isinstance(valor, list):
                    resultado = []

                    for item in valor:
                        resultado.extend(nomes(item))

                    return resultado

                return []

            editoras = nomes(
                atual.get("publisher")
                or atual.get("brand")
            )

            resultados.append(
                {
                    "titulo": atual.get("name") or atual.get("headline"),
                    "autores": nomes(
                        atual.get("author")
                        or atual.get("creator")
                    ),
                    "editora": editoras[0] if editoras else None,
                    "data_publicacao": (
                        atual.get("datePublished")
                        or atual.get("releaseDate")
                    ),
                    "generos": nomes(
                        atual.get("genre")
                        or atual.get("category")
                    ),
                }
            )

    if not resultados:
        return {}

    resultados.sort(
        key=lambda item: sum(
            bool(item.get(campo))
            for campo in (
                "titulo",
                "autores",
                "editora",
                "data_publicacao",
                "generos",
            )
        ),
        reverse=True,
    )

    return resultados[0]


def html_para_texto(html):
    html = re.sub(
        r"(?is)<script.*?</script>",
        " ",
        html,
    )

    html = re.sub(
        r"(?is)<style.*?</style>",
        " ",
        html,
    )

    html = re.sub(
        r"<[^>]+>",
        " ",
        html,
    )

    return re.sub(
        r"\s+",
        " ",
        unescape(html),
    ).strip()


def valor_rotulado(texto, rotulos):
    limites = (
        r"Autor(?:es)?|Author|"
        r"Editora|Editor|Publisher|Editorial|"
        r"ISBN|EAN|"
        r"Data\s+de\s+publica[cç][aã]o|"
        r"Data\s+de\s+lan[cç]amento|"
        r"Published|Publication\s+Date|"
        r"Categoria(?:s)?|G[eé]nero(?:s)?|"
        r"Classifica[cç][aã]o\s+Tem[aá]tica|"
        r"P[aá]ginas|Pages|Idioma|Language|"
        r"Formato|Format"
    )

    for rotulo in rotulos:
        encontrado = re.search(
            rf"(?is)(?:{rotulo})\s*:?\s*(.+?)(?=\s+(?:{limites})\s*:|$)",
            texto,
        )

        if encontrado:
            valor = limpar_texto(encontrado.group(1))

            if valor:
                return valor

    return None


def extrair_pagina_html(url, isbn):
    try:
        resposta = session.get(
            url,
            timeout=TIMEOUT_WEB,
            allow_redirects=True,
        )

        resposta.raise_for_status()
        html = resposta.text
    except Exception:
        return None

    texto = html_para_texto(html)
    evidencia = texto + " " + resposta.url

    if isbn not in normalizar_isbn(evidencia):
        return None

    dados = extrair_json_ld(
        html,
        isbn,
    )

    titulo = dados.get("titulo")
    autores = dados.get("autores") or []
    editora = dados.get("editora")
    data_publicacao = dados.get("data_publicacao")
    generos = dados.get("generos") or []

    if not titulo:
        h1 = re.search(
            r"<h1[^>]*>(.*?)</h1>",
            html,
            flags=re.I | re.S,
        )

        if h1:
            titulo = limpar_texto(h1.group(1))

    if not autores:
        autor = valor_rotulado(
            texto,
            [
                r"Autor(?:es)?",
                r"Author",
            ],
        )

        if autor:
            autores = [autor]

    if not editora:
        editora = valor_rotulado(
            texto,
            [
                r"Editora",
                r"Editor",
                r"Publisher",
                r"Editorial",
            ],
        )

    if not data_publicacao:
        data_publicacao = valor_rotulado(
            texto,
            [
                r"Data\s+de\s+publica[cç][aã]o",
                r"Data\s+de\s+lan[cç]amento",
                r"Publication\s+Date",
                r"Published",
            ],
        )

    if not generos:
        genero = valor_rotulado(
            texto,
            [
                r"Classifica[cç][aã]o\s+Tem[aá]tica",
                r"Categoria(?:s)?",
                r"G[eé]nero(?:s)?",
            ],
        )

        if genero:
            generos = [genero]

    autores = limpar_autores(autores)

    titulo = limpar_titulo(
        titulo,
        isbn,
        autores,
    )

    if not titulo:
        return None

    return {
        "sucesso": True,
        "origem": "Pesquisa Web",
        "prioridade": 85,
        "titulo": titulo,
        "isbn": isbn,
        "autores": autores,
        "editora": limpar_editora(editora),
        "data_publicacao": normalizar_data(data_publicacao),
        "generos": mapear_generos(generos),
    }


def extrair_pagina_reader(url, isbn):
    reader_url = "https://r.jina.ai/" + url

    try:
        resposta = session.get(
            reader_url,
            timeout=TIMEOUT_WEB,
        )

        resposta.raise_for_status()
        texto = resposta.text
    except Exception:
        return None

    if isbn not in normalizar_isbn(texto):
        return None

    titulo = None

    for linha in texto.splitlines():
        linha = linha.strip()

        if linha.startswith("# "):
            titulo = linha[2:].strip()
            break

    autor = valor_rotulado(
        texto,
        [
            r"Autor(?:es)?",
            r"Author",
        ],
    )

    editora = valor_rotulado(
        texto,
        [
            r"Editora",
            r"Editor",
            r"Publisher",
            r"Editorial",
        ],
    )

    data_publicacao = valor_rotulado(
        texto,
        [
            r"Data\s+de\s+publica[cç][aã]o",
            r"Data\s+de\s+lan[cç]amento",
            r"Publication\s+Date",
            r"Published",
        ],
    )

    genero = valor_rotulado(
        texto,
        [
            r"Classifica[cç][aã]o\s+Tem[aá]tica",
            r"Categoria(?:s)?",
            r"G[eé]nero(?:s)?",
        ],
    )

    autores = limpar_autores(
        [autor]
        if autor
        else []
    )

    titulo = limpar_titulo(
        titulo,
        isbn,
        autores,
    )

    if not titulo:
        return None

    return {
        "sucesso": True,
        "origem": "Pesquisa Web",
        "prioridade": 82,
        "titulo": titulo,
        "isbn": isbn,
        "autores": autores,
        "editora": limpar_editora(editora),
        "data_publicacao": normalizar_data(data_publicacao),
        "generos": mapear_generos(
            [genero]
            if genero
            else []
        ),
    }


def pesquisar_ddgs(consulta):
    try:
        return (
            DDGS(
                timeout=TIMEOUT_SEARCH
            ).text(
                consulta,
                region="pt-pt",
                safesearch="moderate",
                max_results=8,
                backend="google,brave,bing",
            )
            or []
        )
    except Exception:
        try:
            return (
                DDGS(
                    timeout=TIMEOUT_SEARCH
                ).text(
                    consulta,
                    region="pt-pt",
                    safesearch="moderate",
                    max_results=8,
                    backend="auto",
                )
                or []
            )
        except Exception:
            return []


def pesquisar_web(isbn, titulo=None, autores=None):
    autor = (
        autores[0]
        if autores
        else None
    )

    consultas = [
        f'"{isbn}"',
        f'"{isbn}" livro',
        f'"{isbn}" autor editora',
    ]

    if titulo:
        consulta = f'"{titulo}" "{isbn}"'

        if autor:
            consulta += f' "{autor}"'

        consultas.append(consulta)

    resultados = []

    with ThreadPoolExecutor(
        max_workers=min(4, len(consultas))
    ) as executor:
        futuros = [
            executor.submit(
                pesquisar_ddgs,
                consulta,
            )
            for consulta in consultas
        ]

        for futuro in as_completed(futuros):
            try:
                resultados.extend(
                    futuro.result()
                )
            except Exception:
                pass

    urls = []
    vistos = set()

    for resultado in resultados:
        url = str(
            resultado.get("href")
            or resultado.get("url")
            or ""
        ).strip()

        if not url or url in vistos:
            continue

        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            continue

        dominio = parsed.netloc.lower()

        if any(
            bloqueado in dominio
            for bloqueado in (
                "google.com",
                "bing.com",
                "duckduckgo.com",
                "facebook.com",
                "instagram.com",
                "youtube.com",
            )
        ):
            continue

        vistos.add(url)
        urls.append(url)

    fontes = []

    with ThreadPoolExecutor(
        max_workers=min(6, len(urls) or 1)
    ) as executor:
        futuros = {
            executor.submit(
                extrair_pagina_html,
                url,
                isbn,
            ): url
            for url in urls[:8]
        }

        for futuro in as_completed(futuros):
            try:
                dados = futuro.result()
            except Exception:
                dados = None

            if dados:
                fontes.append(dados)

    if fontes:
        return fontes

    # Se os sites bloquearam requests normais, tenta o Reader
    # apenas nos primeiros resultados para não deixar o SABIN lento.
    with ThreadPoolExecutor(
        max_workers=min(3, len(urls) or 1)
    ) as executor:
        futuros = {
            executor.submit(
                extrair_pagina_reader,
                url,
                isbn,
            ): url
            for url in urls[:3]
        }

        for futuro in as_completed(futuros):
            try:
                dados = futuro.result()
            except Exception:
                dados = None

            if dados:
                fontes.append(dados)

    return fontes


def prioridade_fonte(fonte):
    return int(
        fonte.get(
            "prioridade",
            50,
        )
    )


def mesclar_fontes(fontes, isbn):
    fontes = [
        fonte
        for fonte in fontes
        if fonte and fonte.get("sucesso")
    ]

    if not fontes:
        return None

    fontes.sort(
        key=prioridade_fonte,
        reverse=True,
    )

    titulo = None
    autores = []
    editora = None
    data_publicacao = None
    generos = []

    fontes_campos = {}

    for fonte in fontes:
        if not titulo and fonte.get("titulo"):
            titulo = fonte["titulo"]
            fontes_campos["titulo"] = fonte["origem"]

        if not autores and fonte.get("autores"):
            autores = limpar_autores(
                fonte["autores"]
            )

            if autores:
                fontes_campos["autores"] = fonte["origem"]

        if not editora and fonte.get("editora"):
            editora = limpar_editora(
                fonte["editora"]
            )

            if editora:
                fontes_campos["editora"] = fonte["origem"]

        if not data_publicacao and fonte.get("data_publicacao"):
            data_publicacao = normalizar_data(
                fonte["data_publicacao"]
            )

            if data_publicacao:
                fontes_campos["data_publicacao"] = fonte["origem"]

        for genero in fonte.get("generos") or []:
            if genero and genero not in generos:
                generos.append(genero)

                if "generos" not in fontes_campos:
                    fontes_campos["generos"] = fonte["origem"]

    titulo = limpar_titulo(
        titulo,
        isbn,
        autores,
    )

    if not titulo:
        return None

    origens = []

    for fonte in fontes:
        origem = fonte.get("origem")

        if origem and origem not in origens:
            origens.append(origem)

    return {
        "sucesso": True,
        "origem": " + ".join(origens),
        "titulo": titulo,
        "isbn": isbn,
        "autores": autores,
        "editora": editora,
        "data_publicacao": data_publicacao,
        "generos": generos[:3],
        "fontes_campos": fontes_campos,
    }


def faltam_campos(resultado):
    if not resultado:
        return True

    return any(
        not resultado.get(campo)
        for campo in (
            "titulo",
            "autores",
            "editora",
            "data_publicacao",
            "generos",
        )
    )


@lru_cache(maxsize=128)
def procurar_externo_cache(isbn):
    fontes = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuros = [
            executor.submit(
                procurar_google_books,
                isbn,
            ),
            executor.submit(
                procurar_open_library,
                isbn,
            ),
        ]

        for futuro in as_completed(futuros):
            try:
                resultado = futuro.result()
            except Exception:
                resultado = None

            if resultado and resultado.get("sucesso"):
                fontes.append(resultado)

    combinado = mesclar_fontes(
        fontes,
        isbn,
    )

    if faltam_campos(combinado):
        titulo = (
            combinado.get("titulo")
            if combinado
            else None
        )

        autores = (
            combinado.get("autores")
            if combinado
            else []
        )

        fontes_web = pesquisar_web(
            isbn,
            titulo=titulo,
            autores=autores,
        )

        fontes.extend(fontes_web)

        combinado = mesclar_fontes(
            fontes,
            isbn,
        )

    return combinado


def procurar_livro(isbn):
    isbn = normalizar_isbn(isbn)

    print(
        f"[BookCatalog] A procurar ISBN {isbn}..."
    )

    if (
        len(isbn) not in (10, 13)
        or not isbn_valido(isbn)
    ):
        return {
            "sucesso": False,
            "erro": "ISBN inválido.",
        }

    local = procurar_livro_local(
        isbn
    )

    if local:
        print(
            "[BookCatalog] Base local: encontrado."
        )

        return local

    print(
        "[BookCatalog] Base local: não encontrado. "
        "A consultar fontes externas..."
    )

    resultado = procurar_externo_cache(
        isbn
    )

    if not resultado:
        print(
            "[BookCatalog] ISBN não encontrado nas fontes externas."
        )

        return {
            "sucesso": False,
            "erro": "ISBN não encontrado.",
        }

    print(
        "[BookCatalog] Fontes por campo:",
        resultado.get(
            "fontes_campos",
            {},
        ),
    )

    return resultado
