import os
import re
import json
import unicodedata
from functools import lru_cache
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from ddgs import DDGS

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


# Configuração

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL não encontrada no ficheiro .env")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

OPEN_LIBRARY_BOOKS_URL = "https://openlibrary.org/api/books"
OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
GOOGLE_BOOKS_VOLUMES_URL = "https://www.googleapis.com/books/v1/volumes"

HTTP_TIMEOUT_CURTO = 4
HTTP_TIMEOUT_READER = 4

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)


HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }
)

_retry = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET"]),
)

HTTP_SESSION.mount(
    "https://",
    HTTPAdapter(max_retries=_retry),
)
HTTP_SESSION.mount(
    "http://",
    HTTPAdapter(max_retries=_retry),
)

DOMINIOS_BLOQUEADOS_PESQUISA = (
    "google.com",
    "www.google.com",
    "bing.com",
    "www.bing.com",
    "duckduckgo.com",
    "html.duckduckgo.com",
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "tiktok.com",
    "www.tiktok.com",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "pinterest.com",
    "www.pinterest.com",
)

EXTENSOES_IGNORADAS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".mp4",
    ".mp3",
    ".zip",
    ".rar",
    ".7z",
    ".exe",
    ".msi",
)


MARCADORES_BLOQUEIO = (
    "attention required",
    "cloudflare",
    "just a moment",
    "verify you are human",
    "checking your browser",
    "enable javascript and cookies",
    "access denied",
    "cf-chl-",
    "captcha",
    "request blocked",
    "security check",
)

MESES = {
    "janeiro": 1,
    "jan": 1,
    "january": 1,
    "fevereiro": 2,
    "fev": 2,
    "february": 2,
    "marco": 3,
    "mar": 3,
    "march": 3,
    "abril": 4,
    "abr": 4,
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
    "august": 8,
    "setembro": 9,
    "set": 9,
    "september": 9,
    "outubro": 10,
    "out": 10,
    "october": 10,
    "novembro": 11,
    "nov": 11,
    "november": 11,
    "dezembro": 12,
    "dez": 12,
    "december": 12,
}


# Utilitários de ISBN


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
    soma = sum(
        int(digito) * (10 - indice)
        for indice, digito in enumerate(corpo)
    )

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


def _isbn_valido(isbn):
    isbn_limpo = normalizar_isbn(isbn)

    if len(isbn_limpo) == 10:
        if not re.fullmatch(r"\d{9}[\dX]", isbn_limpo):
            return False

        soma = 0
        for indice, caractere in enumerate(isbn_limpo):
            valor = 10 if caractere == "X" else int(caractere)
            soma += valor * (10 - indice)

        return soma % 11 == 0

    if len(isbn_limpo) == 13:
        if not isbn_limpo.isdigit():
            return False

        soma = sum(
            int(digito) * (1 if indice % 2 == 0 else 3)
            for indice, digito in enumerate(isbn_limpo[:12])
        )
        controlo = (10 - (soma % 10)) % 10

        return controlo == int(isbn_limpo[-1])

    return False


# Base local da Bookmarked


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
                {"isbn": isbn_limpo},
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


# HTTP


def _criar_pedido(url, accept=None):
    return Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Accept": accept
            or "text/html,application/xhtml+xml,application/json,application/xml;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache",
        },
    )


def _obter_json(url, parametros, timeout=HTTP_TIMEOUT_CURTO):
    resposta = HTTP_SESSION.get(
        url,
        params=parametros,
        timeout=timeout,
    )
    resposta.raise_for_status()
    return resposta.json()


def _pontuar_texto_corrompido(texto):
    valor = str(
        texto or ""
    )

    marcadores = (
        "\ufffd",
        "Ã¡",
        "Ã¢",
        "Ã£",
        "Ã©",
        "Ãª",
        "Ã­",
        "Ã³",
        "Ã´",
        "Ãµ",
        "Ãº",
        "Ã§",
        "Â ",
        "â€“",
        "â€”",
        "â€™",
        "â€œ",
        "â€",
    )

    pontos = (
        valor.count("\ufffd")
        * 50
    )

    for marcador in marcadores:
        pontos += (
            valor.count(
                marcador
            )
            * 10
        )

    return pontos


def _decodificar_resposta_http(
    resposta,
):
    conteudo = resposta.content

    codificacoes = []

    for codificacao in (
        resposta.encoding,
        resposta.apparent_encoding,
        "utf-8",
        "cp1252",
        "latin-1",
    ):
        if (
            codificacao
            and codificacao.lower()
            not in {
                item.lower()
                for item
                in codificacoes
            }
        ):
            codificacoes.append(
                codificacao
            )

    candidatos = []

    for codificacao in codificacoes:
        try:
            texto = conteudo.decode(
                codificacao,
                errors="replace",
            )
        except (
            LookupError,
            UnicodeDecodeError,
        ):
            continue

        candidatos.append(
            (
                _pontuar_texto_corrompido(
                    texto
                ),
                texto,
            )
        )

    if not candidatos:
        return conteudo.decode(
            "utf-8",
            errors="replace",
        )

    candidatos.sort(
        key=lambda item: item[0]
    )

    return candidatos[0][1]


def _obter_html(
    url,
    timeout=HTTP_TIMEOUT_CURTO,
):
    resposta = HTTP_SESSION.get(
        url,
        timeout=timeout,
        allow_redirects=True,
    )

    resposta.raise_for_status()

    return (
        _decodificar_resposta_http(
            resposta
        ),
        resposta.url,
    )


def _obter_texto_reader(url, timeout=HTTP_TIMEOUT_READER):
    # O Reader é usado apenas quando uma loja bloqueia o pedido HTML normal.
    endereco = "https://r.jina.ai/" + str(url)

    with urlopen(
        _criar_pedido(
            endereco,
            accept="text/plain,text/markdown,*/*",
        ),
        timeout=timeout,
    ) as resposta:
        return resposta.read().decode("utf-8", errors="replace")


# Limpeza e deteção de páginas bloqueadas


def _sem_acentos(valor):
    texto = unicodedata.normalize(
        "NFKD",
        str(valor or ""),
    )
    return "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )


def _tentar_corrigir_mojibake(
    texto,
):
    original = str(
        texto or ""
    )

    candidatos = [
        original
    ]

    for codificacao in (
        "latin-1",
        "cp1252",
    ):
        try:
            corrigido = (
                original
                .encode(
                    codificacao
                )
                .decode(
                    "utf-8"
                )
            )

            candidatos.append(
                corrigido
            )
        except (
            UnicodeEncodeError,
            UnicodeDecodeError,
        ):
            pass

    candidatos.sort(
        key=_pontuar_texto_corrompido
    )

    return candidatos[0]


def _limpar_texto_exibicao(valor):
    texto = str(
        valor or ""
    )

    for _ in range(3):
        convertido = unescape(
            texto
        )

        if convertido == texto:
            break

        texto = convertido

    texto = (
        _tentar_corrigir_mojibake(
            texto
        )
    )

    texto = texto.replace(
        "\xa0",
        " ",
    )

    # [Booksmile][23] -> Booksmile
    texto = re.sub(
        r"\[\s*([^\]]+?)\s*\]\[\d+\]",
        r"\1",
        texto,
    )

    # [Booksmile](https://...) -> Booksmile
    texto = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        texto,
    )

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

    return texto.strip(
        " \t\r\n|"
    )


def _normalizar_texto(valor):
    texto = _limpar_texto_exibicao(
        valor
    )

    texto = _sem_acentos(
        texto
    ).lower()

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


def _conteudo_bloqueado(conteudo):
    normalizado = _normalizar_texto(conteudo)
    return any(
        _normalizar_texto(marcador) in normalizado
        for marcador in MARCADORES_BLOQUEIO
    )


def _titulo_invalido(titulo):
    if not titulo:
        return True

    normalizado = _normalizar_texto(titulo)

    if len(normalizado) < 2:
        return True

    if any(
        _normalizar_texto(marcador) in normalizado
        for marcador in MARCADORES_BLOQUEIO
    ):
        return True

    genericos = {
        "pesquisa",
        "search",
        "home",
        "inicio",
        "livros",
        "books",
        "resultado da pesquisa",
        "resultados de pesquisa",
    }

    return normalizado in genericos


def _dominio_confiavel(url):
    """
    O nome da função foi mantido para não quebrar o restante código,
    mas ela já não funciona como whitelist.

    Aceita qualquer página Web pública que pareça utilizável e rejeita
    apenas motores de pesquisa, redes sociais e ficheiros que não fazem
    sentido como ficha bibliográfica.
    """
    valor = str(url or "").strip()

    if not valor:
        return False

    parsed = urlparse(valor)

    if parsed.scheme not in ("http", "https"):
        return False

    dominio = parsed.netloc.lower().split(":")[0]

    if not dominio:
        return False

    if dominio in {
        "127.0.0.1",
        "localhost",
        "0.0.0.0",
    }:
        return False

    for bloqueado in DOMINIOS_BLOQUEADOS_PESQUISA:
        if (
            dominio == bloqueado
            or dominio.endswith("." + bloqueado)
        ):
            return False

    caminho = parsed.path.lower()

    if any(
        caminho.endswith(extensao)
        for extensao in EXTENSOES_IGNORADAS
    ):
        return False

    return True


def _prioridade_dominio(url):
    # Não há sites preferidos. Todas as fontes Web são avaliadas
    # pelos metadados encontrados e pela presença do ISBN exato.
    return 0


# Open Library


def _consultar_openlibrary_books(isbn):
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


def _consultar_openlibrary_search(isbn):
    variantes = set(variantes_isbn(isbn))

    consultas = [
        {
            "isbn": isbn,
            "limit": 5,
            "fields": "title,author_name,publisher,first_publish_year,subject,isbn",
        },
        {
            "q": isbn,
            "limit": 5,
            "fields": "title,author_name,publisher,first_publish_year,subject,isbn",
        },
    ]

    for parametros in consultas:
        dados = _obter_json(
            OPEN_LIBRARY_SEARCH_URL,
            parametros,
        )

        for documento in dados.get("docs") or []:
            isbns_documento = {
                normalizar_isbn(valor)
                for valor in (documento.get("isbn") or [])
                if valor
            }

            if variantes & isbns_documento:
                return documento

    return None


def procurar_livro_open_library(isbn):
    isbn_limpo = normalizar_isbn(isbn)

    dados_livro = None
    dados_pesquisa = None

    for variante in variantes_isbn(isbn_limpo):
        try:
            if not dados_livro:
                dados_livro = _consultar_openlibrary_books(variante)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            pass

        try:
            if not dados_pesquisa:
                dados_pesquisa = _consultar_openlibrary_search(variante)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            pass

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
            if isinstance(autor, dict) and autor.get("name")
        ]

        editoras = dados_livro.get("publishers") or []
        if editoras:
            primeira = editoras[0]
            editora = (
                primeira.get("name")
                if isinstance(primeira, dict)
                else str(primeira)
            )

        data_publicacao = dados_livro.get("publish_date")

        generos = [
            assunto.get("name")
            for assunto in dados_livro.get("subjects", [])
            if isinstance(assunto, dict) and assunto.get("name")
        ]

    if dados_pesquisa:
        titulo = titulo or dados_pesquisa.get("title")
        autores = autores or (dados_pesquisa.get("author_name") or [])

        if not editora:
            editoras = dados_pesquisa.get("publisher") or []
            if editoras:
                editora = editoras[0]

        if not data_publicacao:
            ano = dados_pesquisa.get("first_publish_year")
            if ano:
                data_publicacao = str(ano)

        existentes = {
            _normalizar_texto(genero)
            for genero in generos
        }

        for assunto in dados_pesquisa.get("subject") or []:
            chave = _normalizar_texto(assunto)
            if assunto and chave not in existentes:
                generos.append(str(assunto))
                existentes.add(chave)

    if _titulo_invalido(titulo):
        return {
            "sucesso": False,
            "erro": "Open Library devolveu um resultado inválido.",
        }

    return {
        "sucesso": True,
        "origem": "Open Library API",
        "titulo": titulo,
        "isbn": isbn_limpo,
        "autores": autores,
        "editora": editora,
        "data_publicacao": data_publicacao,
        "generos": generos,
    }


# Google Books


def procurar_livro_google_books(isbn):
    isbn_limpo = normalizar_isbn(isbn)
    variantes = variantes_isbn(isbn_limpo)

    consultas = []
    for variante in variantes:
        consultas.append(f"isbn:{variante}")
    consultas.extend(variantes)

    info_escolhida = None

    for consulta in consultas:
        try:
            dados = _obter_json(
                GOOGLE_BOOKS_VOLUMES_URL,
                {
                    "q": consulta,
                    "maxResults": 10,
                    "printType": "books",
                },
            )
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            continue

        for item in dados.get("items") or []:
            info = item.get("volumeInfo") or {}
            identificadores = info.get("industryIdentifiers") or []

            valores = {
                normalizar_isbn(identificador.get("identifier"))
                for identificador in identificadores
                if identificador.get("identifier")
            }

            if any(variante in valores for variante in variantes):
                info_escolhida = info
                break

        if info_escolhida:
            break

    if not info_escolhida:
        return {
            "sucesso": False,
            "erro": "ISBN não encontrado na Google Books.",
        }

    titulo = info_escolhida.get("title")

    if _titulo_invalido(titulo):
        return {
            "sucesso": False,
            "erro": "Google Books devolveu um resultado inválido.",
        }

    return {
        "sucesso": True,
        "origem": "Google Books API",
        "titulo": titulo,
        "isbn": isbn_limpo,
        "autores": info_escolhida.get("authors") or [],
        "editora": info_escolhida.get("publisher"),
        "data_publicacao": info_escolhida.get("publishedDate"),
        "generos": info_escolhida.get("categories") or [],
    }


# Parsing HTML / Markdown de catálogos web


class _ExtratorTextoHTML(HTMLParser):
    BLOCOS = {
        "address", "article", "aside", "blockquote", "br", "dd", "div",
        "dl", "dt", "figcaption", "figure", "footer", "form", "h1",
        "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main",
        "nav", "ol", "p", "pre", "section", "table", "tbody", "td",
        "tfoot", "th", "thead", "tr", "ul",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []
        self.ignorar = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag in ("script", "style", "noscript"):
            self.ignorar += 1
        elif not self.ignorar and tag in self.BLOCOS:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in ("script", "style", "noscript"):
            self.ignorar = max(0, self.ignorar - 1)
        elif not self.ignorar and tag in self.BLOCOS:
            self.partes.append("\n")

    def handle_data(self, data):
        if not self.ignorar:
            texto = str(data or "").strip()
            if texto:
                self.partes.append(texto)

    def texto(self):
        bruto = " ".join(self.partes)
        bruto = re.sub(r"[ \t]+", " ", bruto)
        bruto = re.sub(r" *\n *", "\n", bruto)
        bruto = re.sub(r"\n{2,}", "\n", bruto)
        return bruto.strip()


class _ExtratorJSONLD(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.em_jsonld = False
        self.buffer = []
        self.blocos = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return

        atributos = {
            str(chave).lower(): str(valor or "")
            for chave, valor in attrs
        }

        if "ld+json" in atributos.get("type", "").lower():
            self.em_jsonld = True
            self.buffer = []

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.em_jsonld:
            bloco = "".join(self.buffer).strip()
            if bloco:
                self.blocos.append(bloco)
            self.em_jsonld = False
            self.buffer = []

    def handle_data(self, data):
        if self.em_jsonld:
            self.buffer.append(data)


def _html_para_texto(html):
    parser = _ExtratorTextoHTML()
    parser.feed(str(html or ""))
    return parser.texto()


def _iterar_json(valor):
    if isinstance(valor, dict):
        yield valor
        for subvalor in valor.values():
            yield from _iterar_json(subvalor)
    elif isinstance(valor, list):
        for item in valor:
            yield from _iterar_json(item)


def _nomes_campo(valor):
    if not valor:
        return []

    if isinstance(valor, str):
        return [valor.strip()] if valor.strip() else []

    if isinstance(valor, dict):
        nome = valor.get("name") or valor.get("title")
        return [str(nome).strip()] if nome else []

    if isinstance(valor, list):
        nomes = []
        for item in valor:
            nomes.extend(_nomes_campo(item))
        return nomes

    return []


def _jsonld_livro(html, isbn):
    if _conteudo_bloqueado(html):
        return None

    parser = _ExtratorJSONLD()
    parser.feed(str(html or ""))

    isbn_limpo = normalizar_isbn(isbn)
    candidatos = []

    for bloco in parser.blocos:
        try:
            dados = json.loads(bloco)
        except (json.JSONDecodeError, TypeError):
            continue

        for objeto in _iterar_json(dados):
            tipo = objeto.get("@type")

            if isinstance(tipo, list):
                tipos = {_normalizar_texto(item) for item in tipo}
            else:
                tipos = {_normalizar_texto(tipo)}

            if not ({"book", "product"} & tipos):
                continue

            isbn_objeto = normalizar_isbn(
                objeto.get("isbn")
                or objeto.get("gtin13")
                or objeto.get("gtin")
                or objeto.get("sku")
                or ""
            )

            if isbn_objeto and isbn_objeto != isbn_limpo:
                continue

            titulo = objeto.get("name") or objeto.get("headline")

            if _titulo_invalido(titulo):
                continue

            autores = _nomes_campo(
                objeto.get("author")
                or objeto.get("creator")
            )

            editora_lista = _nomes_campo(
                objeto.get("publisher")
                or objeto.get("brand")
            )
            editora = editora_lista[0] if editora_lista else None

            data_publicacao = (
                objeto.get("datePublished")
                or objeto.get("releaseDate")
            )

            categoria = (
                objeto.get("genre")
                or objeto.get("category")
            )
            generos = _nomes_campo(categoria)

            candidatos.append(
                {
                    "titulo": str(titulo).strip(),
                    "autores": autores,
                    "editora": editora,
                    "data_publicacao": data_publicacao,
                    "generos": generos,
                }
            )

    if not candidatos:
        return None

    candidatos.sort(
        key=lambda item: _pontuar_metadados(item),
        reverse=True,
    )

    return candidatos[0]


def _meta_html(html, propriedade):
    padroes = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(propriedade)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(propriedade)}["\']',
    ]

    for padrao in padroes:
        encontrado = re.search(padrao, str(html or ""), flags=re.I)
        if encontrado:
            return unescape(encontrado.group(1)).strip()

    return None


def _h1_html(html):
    encontrado = re.search(
        r"<h1[^>]*>(.*?)</h1>",
        str(html or ""),
        flags=re.I | re.S,
    )

    if not encontrado:
        return None

    texto = re.sub(r"<[^>]+>", " ", encontrado.group(1))
    texto = unescape(re.sub(r"\s+", " ", texto)).strip()
    return texto or None


def _linha_valor(texto, rotulos):
    texto = str(texto or "")

    for rotulo in rotulos:
        padroes = [
            rf"(?im)^\s*{rotulo}\s*:?\s*\|\s*([^\n|]+)",
            rf"(?im)^\s*{rotulo}\s*:?\s+([^\n]+)$",
            rf"(?im)^\s*{rotulo}\s*:?\s*$\s*\n\s*([^\n]+)$",
        ]

        for padrao in padroes:
            encontrado = re.search(padrao, texto)
            if encontrado:
                valor = encontrado.group(1).strip(
                    " \t\n|:-"
                )

                valor = _limpar_texto_exibicao(
                    valor
                )

                if valor and valor not in {
                    "-",
                    "—",
                }:
                    return valor

    return None


def _extrair_classificacao_tematica(texto):
    """Extrai apenas a classificação do LIVRO.

    Algumas páginas da WOOK/Bertrand colocam vários campos na mesma linha
    depois de removermos o HTML. Se usarmos uma leitura genérica, o valor de
    "Classificação Temática" pode acabar colado ao EAN, idade recomendada
    ou texto do autor. Aqui limitamos explicitamente o valor ao campo seguinte.
    """
    texto = str(texto or "")

    if not texto:
        return None

    limites = (
        r"EAN",
        r"ISBN",
        r"Idade\s+M[ií]nima",
        r"Tipo\s+de\s+produto",
        r"P[aá]ginas",
        r"Encaderna[cç][aã]o",
        r"Dimens[oõ]es",
        r"SOBRE\s+O\s+AUTOR",
        r"OPINI[AÃ]O\s+DOS\s+LEITORES",
        r"SINOPSE",
    )
    limite = "|".join(limites)

    padroes = [
        rf"(?is)Classifica[cç][aã]o\s+Tem[aá]tica\s*:?\s*(.+?)(?=\s*(?:{limite})\s*:|$)",
        rf"(?is)Tem[aá]tica\s*:?\s*(.+?)(?=\s*(?:{limite})\s*:|$)",
        rf"(?is)Categoria\s*:?\s*(.+?)(?=\s*(?:{limite})\s*:|$)",
    ]

    for padrao in padroes:
        encontrado = re.search(padrao, texto)
        if encontrado:
            valor = re.sub(r"\s+", " ", encontrado.group(1)).strip(" |:-")
            if valor:
                return valor

    # Fallback específico para a estrutura típica da WOOK/Bertrand.
    encontrado = re.search(
        r"(?is)(Livros\s+em\s+Portugu[eê]s\s*>\s*Literatura\s*>\s*[^\n|]+?)(?=\s*(?:EAN|ISBN|Idade\s+M[ií]nima|$))",
        texto,
    )
    if encontrado:
        return re.sub(r"\s+", " ", encontrado.group(1)).strip(" |:-")

    return None


def _normalizar_data_catalogo(valor):
    if not valor:
        return None

    texto_original = str(valor).strip()
    texto = _normalizar_texto(texto_original)

    # AAAA-MM-DD / AAAA-MM
    encontrado = re.search(r"\b(19\d{2}|20\d{2})[-/.](0?[1-9]|1[0-2])(?:[-/.](0?[1-9]|[12]\d|3[01]))?\b", texto)
    if encontrado:
        ano = int(encontrado.group(1))
        mes = int(encontrado.group(2))
        dia = int(encontrado.group(3) or 1)
        return f"{ano:04d}-{mes:02d}-{dia:02d}"

    # MM-AAAA / MM/AAAA
    encontrado = re.search(r"\b(0?[1-9]|1[0-2])[-/.](19\d{2}|20\d{2})\b", texto)
    if encontrado:
        mes = int(encontrado.group(1))
        ano = int(encontrado.group(2))
        return f"{ano:04d}-{mes:02d}-01"

    # agosto de 2025 / August of 2025 / agosto 2025
    for nome_mes, numero_mes in MESES.items():
        if re.search(
            rf"\b{re.escape(nome_mes)}\b(?:\s+(?:de|of))?\s+(19\d{{2}}|20\d{{2}})\b",
            texto,
        ):
            ano = int(
                re.search(
                    rf"\b{re.escape(nome_mes)}\b(?:\s+(?:de|of))?\s+(19\d{{2}}|20\d{{2}})\b",
                    texto,
                ).group(1)
            )
            return f"{ano:04d}-{numero_mes:02d}-01"

    # Só ano.
    encontrado = re.search(r"\b(19\d{2}|20\d{2})\b", texto)
    if encontrado:
        return f"{int(encontrado.group(1)):04d}-01-01"

    return texto_original


def _generos_da_classificacao(valor):
    if not valor:
        return []

    texto = str(valor)
    texto = re.sub(r"<[^>]+>", " > ", texto)
    texto = unescape(texto)
    texto = re.sub(r"\s+", " ", texto).strip()

    partes = [
        parte.strip(" .,:;|-_")
        for parte in re.split(r">|›|»|/|\\|\|", texto)
        if parte.strip(" .,:;|-_")
    ]

    ignorar = {
        "livros",
        "livros em portugues",
        "literatura",
        "books",
        "books in portuguese",
        "fiction",
        "ficcao",
    }

    aliases = [
        ("Realismo Mágico", ("realismo magico", "magical realism", "magic realism")),
        ("Ficção Científica", ("ficcao cientifica", "science fiction", "sci fi")),
        ("Autoajuda", ("autoajuda", "self help", "personal development")),
        ("Distopia", ("distopia", "dystopia", "dystopian")),
        ("Policial", ("policial", "crime fiction", "detective fiction", "mystery fiction")),
        ("Poesia", ("poesia", "poetry", "poems")),
        ("Fantasia", ("fantasia", "fantasy")),
        ("Terror", ("terror", "horror")),
        ("Suspense", ("suspense", "thriller")),
        ("Biografia", ("biografia", "biography", "autobiography", "memoir")),
        ("Infantil", (
            "infantil",
            "juvenile fiction",
            "juvenile nonfiction",
            "children fiction",
            "children nonfiction",
            "children s fiction",
            "children s nonfiction",
            "kids",
            "children",
            "juvenil",
        )),
        ("Aventura", ("aventura", "adventure")),
        ("Romance", ("romance", "romantic fiction", "love stories")),
        ("Ficção", ("ficcao", "fiction", "novel")),
    ]

    encontrados = []

    for parte in partes:
        normalizada = _normalizar_texto(parte)

        if not normalizada or normalizada in ignorar:
            continue

        for nome, termos in aliases:
            if any(
                normalizada == termo
                or normalizada.startswith(termo + " ")
                or normalizada.endswith(" " + termo)
                for termo in termos
            ):
                if nome not in encontrados:
                    encontrados.append(nome)
                break

    if encontrados:
        return encontrados[:3]

    normalizado = _normalizar_texto(texto)

    for nome, termos in aliases:
        if any(re.search(rf"\b{re.escape(termo)}\b", normalizado) for termo in termos):
            return [nome]

    return []


def _generos_da_ficha(texto, classificacao=None, html=None):
    generos = _generos_da_classificacao(classificacao)

    if generos:
        return generos

    fontes = [str(texto or "")]

    if html:
        fontes.append(str(html))

    marcadores = [
        r"Classifica[cç][aã]o\s+Tem[aá]tica",
        r"Classifica[cç][aã]o\s+Tematica",
        r"Tem[aá]tica",
        r"Categoria",
    ]

    for fonte in fontes:
        if not fonte:
            continue

        for marcador in marcadores:
            encontrado = re.search(marcador, fonte, flags=re.I)

            if not encontrado:
                continue

            trecho = fonte[encontrado.start():encontrado.start() + 5000]
            trecho = re.split(
                r"(?i)(?:EAN|ISBN|Idade\s+M[ií]nima|OPINI[AÃ]O\s+DOS\s+LEITORES|SOBRE\s+O\s+AUTOR)",
                trecho,
                maxsplit=1,
            )[0]

            if "<" in trecho and ">" in trecho:
                trecho = _html_para_texto(trecho)

            generos = _generos_da_classificacao(trecho)

            if generos:
                return generos

    return []

def _autor_perto_titulo(texto, titulo):
    if not texto or not titulo:
        return []

    indice = _normalizar_texto(texto).find(_normalizar_texto(titulo))

    if indice < 0:
        trecho = str(texto)[:1000]
    else:
        trecho = str(texto)[max(0, indice - 100):indice + 900]

    padroes = [
        r"(?im)^\s*de\s+([^\n|]{2,100})$",
        r"(?im)^\s*by\s+([^\n|]{2,100})$",
        rf"(?im){re.escape(titulo)}\s+(?:de|by)\s+([^\n|]{{2,100}})",
    ]

    for padrao in padroes:
        encontrado = re.search(padrao, trecho, flags=re.I)
        if encontrado:
            autor = encontrado.group(1).strip(" .|-#")

            # Evita capturar descrições enormes.
            if 2 <= len(autor) <= 100:
                return [autor]

    return []


def _remover_creditos_nao_autor(autores, texto):
    if not autores:
        return []

    excluidos = set()

    for rotulo in (
        r"Pref[aá]cio",
        r"Foreword",
        r"Tradu[cç][aã]o",
        r"Translator",
        r"Tradutor(?:a)?",
        r"Ilustra[cç][aã]o",
    ):
        valor = _linha_valor(texto, [rotulo])

        if valor:
            for nome in re.split(r"\s*[;,]\s*|\s+e\s+|\s+and\s+", valor):
                nome = nome.strip()
                if nome:
                    excluidos.add(_normalizar_texto(nome))

    resultado = []
    vistos = set()

    for autor in autores:
        nome = _limpar_texto_exibicao(
            autor
        )

        chave = _normalizar_texto(
            nome
        )

        if (
            nome
            and chave not in excluidos
            and chave not in vistos
            and not any(
                palavra in chave
                for palavra in (
                    "prefacio",
                    "traducao",
                    "translator",
                    "foreword",
                )
            )
        ):
            vistos.add(
                chave
            )
            resultado.append(
                nome
            )

    return resultado


def _contem_lixo_metadado(
    valor,
):
    normalizado = _normalizar_texto(
        valor
    )

    marcadores = (
        "using the web site",
        "using this website",
        "you confirm",
        "you have read",
        "you agree",
        "agreed to be bound",
        "terms and conditions",
        "privacy policy",
        "cookie policy",
        "cookies",
        "accept all",
        "eur ",
        " eur",
        "preco ",
        "price ",
        "stock ",
        "adicionar ao carrinho",
        "add to cart",
        "comprar",
        "buy now",
        "isbn ",
        "ean ",
        "http://",
        "https://",
        "www.",
    )

    return any(
        marcador in normalizado
        for marcador in marcadores
    )


def _parece_nome_autor(
    valor,
):
    nome = _limpar_texto_exibicao(
        valor
    )

    if not nome:
        return False

    if len(nome) > 90:
        return False

    if _contem_lixo_metadado(
        nome
    ):
        return False

    if re.search(
        r"[$€£]|https?://|\d",
        nome,
        flags=re.I,
    ):
        return False

    normalizado = _normalizar_texto(
        nome
    )

    termos_invalidos = (
        " um banana",
        " uma banana",
        " livro ",
        " ebook ",
        " edition",
        " editions ",
        " edicao",
        " volume ",
        " vol ",
        " preco ",
        " price ",
        " stock ",
        " using ",
        " storygraph",
        " the storygraph",
        " goodreads",
        " website",
        " web site",
        " reviews ",
        " ratings ",
        " browse ",
        " sign in",
        " login",
    )

    if any(
        termo in f" {normalizado} "
        for termo in termos_invalidos
    ):
        return False

    palavras = [
        parte
        for parte in re.split(
            r"\s+",
            nome,
        )
        if parte
    ]

    if not (
        1
        <= len(palavras)
        <= 9
    ):
        return False

    letras = sum(
        caractere.isalpha()
        for caractere in nome
    )

    if letras < 2:
        return False

    proporcao_letras = (
        letras
        / max(
            len(nome),
            1,
        )
    )

    if proporcao_letras < 0.55:
        return False

    return True


def _limpar_autores_validos(
    autores,
):
    resultado = []
    vistos = set()

    for autor in (
        autores
        or []
    ):
        nome = _limpar_texto_exibicao(
            autor
        )

        # Remove funções editoriais coladas ao nome.
        nome = re.sub(
            r"\s*\((?:autor|autora|author|writer)\)\s*",
            " ",
            nome,
            flags=re.I,
        )

        # Remove campos seguintes que algumas páginas colam ao autor.
        nome = re.split(
            r"\s+(?:"
            r"Formato|Format|"
            r"Encaderna[cç][aã]o|"
            r"Binding|"
            r"Editora|Publisher|"
            r"ISBN|EAN|"
            r"Data|Date"
            r")\s*:",
            nome,
            maxsplit=1,
            flags=re.I,
        )[0].strip()

        # Remove preços colados ao nome.
        nome = re.split(
            r"\s+(?:EUR|€|USD|\$)\s*[\d,.]+",
            nome,
            maxsplit=1,
            flags=re.I,
        )[0].strip()

        # "Jeff Kinney Editorial" -> "Jeff Kinney".
        nome = re.sub(
            r"\s+(?:Editorial|Editora|Publisher|Author|Autor)\s*$",
            "",
            nome,
            flags=re.I,
        ).strip()

        if "," in nome:
            partes_virgula = [
                parte.strip()
                for parte in nome.split(",")
                if parte.strip()
            ]

            if partes_virgula:
                primeira = partes_virgula[0]
                resto = " ".join(
                    partes_virgula[1:]
                )

                if (
                    resto
                    and (
                        re.search(
                            r"\d",
                            resto,
                        )
                        or any(
                            termo in _normalizar_texto(
                                resto
                            )
                            for termo in (
                                "banana",
                                "livro",
                                "ebook",
                                "edition",
                                "edicao",
                                "volume",
                                "formato",
                                "capa",
                            )
                        )
                    )
                ):
                    nome = primeira

        nome = re.sub(
            r"\s+",
            " ",
            nome,
        ).strip(
            " .,:;|-"
        )

        if not _parece_nome_autor(
            nome
        ):
            continue

        chave = _normalizar_texto(
            nome
        )

        if chave in vistos:
            continue

        if (
            nome.isupper()
            and len(nome) > 3
        ):
            nome = " ".join(
                parte.capitalize()
                if not (
                    len(parte) <= 3
                    and "." in parte
                )
                else parte
                for parte in nome.split()
            )

        vistos.add(
            chave
        )
        resultado.append(
            nome
        )

    return resultado


def _formatar_nome_editora(
    valor,
):
    editora = (
        _limpar_texto_exibicao(
            valor
        )
    )

    if not editora:
        return None

    # Remove URLs/domínios caso algum resultado da pesquisa
    # tenha devolvido a editora nesse formato.
    editora = re.sub(
        r"^https?://",
        "",
        editora,
        flags=re.I,
    )

    editora = re.sub(
        r"^www\.",
        "",
        editora,
        flags=re.I,
    )

    editora = re.sub(
        r"\.(?:pt|com|br|org|net)(?:/.*)?$",
        "",
        editora,
        flags=re.I,
    )

    # Remove separadores estranhos vindos de snippets/HTML.
    editora = re.sub(
        r"[_/]+",
        " ",
        editora,
    )

    editora = re.sub(
        r"\s+",
        " ",
        editora,
    ).strip()

    chave_compacta = re.sub(
        r"[^a-z0-9]",
        "",
        _sem_acentos(
            editora
        ).lower(),
    )

    # Algumas páginas devolvem o nome da editora todo junto.
    # Mantemos aqui apenas normalizações de marcas editoriais,
    # sem depender de um site específico.
    nomes_conhecidos = {
        "casadasletras": "Casa das Letras",
        "companhiadasletras": "Companhia das Letras",
        "editorapresenca": "Editorial Presença",
        "editorialpresenca": "Editorial Presença",
        "presenca": "Presença",
        "astralcultural": "Astral Cultural",
        "altoastral": "Alto Astral",
        "editoraltoastral": "Alto Astral",
        "booksmile": "Booksmile",
        "portoeditora": "Porto Editora",
        "penguinrandomhouse": "Penguin Random House",
        "harpercollins": "HarperCollins",
        "planeta": "Planeta",
        "editoraplaneta": "Planeta",
        "intrinseca": "Intrínseca",
        "rocco": "Rocco",
        "record": "Record",
        "leya": "Leya",
    }

    if chave_compacta in nomes_conhecidos:
        return nomes_conhecidos[
            chave_compacta
        ]

    # Para nomes que já vêm separados, normaliza a capitalização
    # sem estragar conectores portugueses.
    if " " in editora:
        conectores = {
            "a",
            "as",
            "da",
            "das",
            "de",
            "do",
            "dos",
            "e",
        }

        palavras = []

        for indice, palavra in enumerate(
            editora.split()
        ):
            palavra_limpa = palavra.strip()

            if not palavra_limpa:
                continue

            # Preserva siglas como "Leya", "FNAC", etc.
            if (
                palavra_limpa.isupper()
                and len(
                    palavra_limpa
                ) <= 5
            ):
                palavras.append(
                    palavra_limpa
                )
                continue

            palavra_lower = (
                palavra_limpa.lower()
            )

            if (
                indice > 0
                and palavra_lower
                in conectores
            ):
                palavras.append(
                    palavra_lower
                )
            else:
                palavras.append(
                    palavra_lower[:1].upper()
                    + palavra_lower[1:]
                )

        editora = " ".join(
            palavras
        )

    return editora


def _limpar_editora(
    valor,
):
    editora = (
        _formatar_nome_editora(
            valor
        )
    )

    if not editora:
        return None

    editora = re.sub(
        r"^\s*(?:editora|editor|publisher|editorial)\s*:?\s*",
        "",
        editora,
        flags=re.I,
    )

    # Remove ano colado no final: "Booksmile, 2014".
    editora = re.sub(
        r"\s*[,;|-]?\s*\b(?:19|20)\d{2}\b\s*$",
        "",
        editora,
    )

    editora = editora.strip(
        " [](){}.,;|-"
    )

    # Volta a formatar depois de remover prefixos/ano.
    editora = (
        _formatar_nome_editora(
            editora
        )
    )

    if not editora:
        return None

    if len(editora) > 90:
        return None

    if _contem_lixo_metadado(
        editora
    ):
        return None

    if re.search(
        r"https?://|[$€£]",
        editora,
        flags=re.I,
    ):
        return None

    return editora


def _marca_do_dominio(
    url,
):
    try:
        dominio = urlparse(
            str(url or "")
        ).netloc.lower()

        dominio = dominio.split(
            ":"
        )[0]

        if dominio.startswith(
            "www."
        ):
            dominio = dominio[
                4:
            ]

        if not dominio:
            return None

        partes = [
            parte
            for parte in dominio.split(
                "."
            )
            if parte
        ]

        if len(partes) < 2:
            return None

        return partes[-2]

    except Exception:
        return None


def _remover_sufixo_site_titulo(
    titulo,
    url_origem,
):
    titulo = _limpar_texto_exibicao(
        titulo
    )

    marca = _marca_do_dominio(
        url_origem
    )

    if (
        not titulo
        or not marca
    ):
        return titulo

    partes = re.split(
        r"\s+(?:[-|–—])\s+",
        titulo,
    )

    if len(partes) <= 1:
        return titulo

    ultimo = (
        partes[-1]
        .strip()
    )

    ultimo_compacto = re.sub(
        r"[^a-z0-9]",
        "",
        _sem_acentos(
            ultimo
        ).lower(),
    )

    marca_compacta = re.sub(
        r"[^a-z0-9]",
        "",
        _sem_acentos(
            marca
        ).lower(),
    )

    if (
        ultimo_compacto
        and marca_compacta
        and (
            ultimo_compacto
            == marca_compacta
            or ultimo_compacto.endswith(
                marca_compacta
            )
            or marca_compacta.endswith(
                ultimo_compacto
            )
        )
    ):
        titulo = " - ".join(
            partes[:-1]
        )

    return titulo.strip(
        " .|:-–—"
    )


def _limpar_titulo_livro(
    valor,
):
    titulo = (
        _limpar_texto_exibicao(
            valor
        )
    )

    if not titulo:
        return None

    normalizado_inicial = (
        _normalizar_texto(
            titulo
        )
    )

    prefixos_invalidos = (
        "editions for ",
        "editions of ",
        "edition for ",
        "edition of ",
        "reviews for ",
        "reviews of ",
        "ratings for ",
        "books similar to ",
        "books like ",
    )

    if any(
        normalizado_inicial.startswith(
            prefixo
        )
        for prefixo in prefixos_invalidos
    ):
        return None

    # Remove ISBN acrescentado ao final do título.
    # Exemplos:
    # "O Diário de um Banana 1 (9789896680008)"
    # "O Livro do Ric - 9789899087279"
    titulo = re.sub(
        r"\s*\(\s*(?:\d[\s-]?){9,12}[\dXx]\s*\)\s*$",
        "",
        titulo,
    )

    titulo = re.sub(
        r"\s*(?:[-|–—:])\s*(?:\d[\s-]?){9,12}[\dXx]\s*$",
        "",
        titulo,
    )

    # Remove informação de formato/edição entre parênteses.
    titulo = re.sub(
        r"\s*\([^)]*(?:"
        r"edi[cç][aã]o|edition|"
        r"hardcover|paperback|"
        r"capa dura|brochura|"
        r"kindle|ebook"
        r")[^)]*\)\s*",
        " ",
        titulo,
        flags=re.I,
    )

    # Remove descrições comerciais acrescentadas depois do título.
    titulo = re.sub(
        r"\s+(?:um|uma)\s+"
        r"(?:romance|livro|hist[oó]ria)\s+"
        r"(?:com|de)\s+.+$",
        "",
        titulo,
        flags=re.I,
    )

    # Remove formatos no final.
    titulo = re.sub(
        r"\s*(?:[-|–—])\s*"
        r"(?:hardcover|paperback|"
        r"capa dura|brochura|"
        r"kindle edition|ebook|"
        r"mass market paperback)"
        r"\s*$",
        "",
        titulo,
        flags=re.I,
    )

    # Remove nomes de sites/lojas colados ao título.
    titulo = re.sub(
        r"\s*(?:[:|–—-])\s*"
        r"(?:www\.)?"
        r"(?:amazon(?:\.[a-z.]+)?|wook|bertrand|fnac|google books|"
        r"the storygraph|storygraph|goodreads|bookroo|skoob)"
        r"(?:\s*[:|-]\s*books?)?"
        r".*$",
        "",
        titulo,
        flags=re.I,
    )

    encontrado_parenteses = re.search(
        r"\s*\(([^()]*)\)\s*$",
        titulo,
    )

    if encontrado_parenteses:
        conteudo = (
            encontrado_parenteses
            .group(1)
            .strip()
        )

        titulo_base = titulo[
            :encontrado_parenteses.start()
        ].strip()

        palavras_base = {
            palavra
            for palavra in _normalizar_texto(
                titulo_base
            ).split()
            if palavra
        }

        palavras_parenteses = {
            palavra
            for palavra in _normalizar_texto(
                conteudo
            ).split()
            if palavra
        }

        if (
            palavras_parenteses
            and palavras_parenteses.issubset(
                palavras_base
            )
        ):
            titulo = titulo_base

    titulo = re.sub(
        r"\s+",
        " ",
        titulo,
    ).strip(
        " .|:-–—"
    )

    normalizado_final = (
        _normalizar_texto(
            titulo
        )
    )

    termos_invalidos = (
        "the storygraph",
        "storygraph",
        "goodreads",
        "editions for",
        "editions of",
        "amazon.co.uk",
        "amazon.com",
    )

    if any(
        termo in normalizado_final
        for termo in termos_invalidos
    ):
        return None

    if _titulo_invalido(
        titulo
    ):
        return None

    if len(titulo) > 180:
        return None

    return titulo


def _limpar_titulo_com_autores(
    titulo,
    autores,
):
    titulo = (
        _limpar_titulo_livro(
            titulo
        )
    )

    if not titulo:
        return None

    autores_normalizados = {
        _normalizar_texto(
            autor
        )
        for autor in (
            autores
            or []
        )
        if autor
    }

    partes = [
        parte.strip()
        for parte in re.split(
            r"\s+(?:[-|–—])\s+",
            titulo,
        )
        if parte.strip()
    ]

    if len(partes) <= 1:
        return titulo

    while len(partes) > 1:
        ultimo = partes[-1]
        ultimo_normalizado = (
            _normalizar_texto(
                ultimo
            )
        )

        # Remove o autor quando vem colado ao título:
        # "Título - Rick Riordan".
        if (
            ultimo_normalizado
            in autores_normalizados
        ):
            partes.pop()
            continue

        # Remove um nome de site/serviço no fim:
        # "Título - Rick Riordan - SKOOB".
        parece_site = (
            (
                ultimo.isupper()
                and 2 <= len(ultimo) <= 30
            )
            or "." in ultimo
            or any(
                termo in ultimo_normalizado
                for termo in (
                    "books",
                    "livros",
                    "bookstore",
                    "store",
                    "shop",
                    "amazon",
                    "skoob",
                    "storygraph",
                    "goodreads",
                    "wook",
                    "bertrand",
                    "fnac",
                )
            )
        )

        if parece_site:
            partes.pop()
            continue

        break

    titulo = " - ".join(
        partes
    ).strip()

    return (
        _limpar_titulo_livro(
            titulo
        )
    )


def _sanitizar_resultado_web(
    dados,
):
    if not dados:
        return None

    resultado = dict(
        dados
    )

    titulo_limpo = (
        _remover_sufixo_site_titulo(
            resultado.get(
                "titulo"
            ),
            resultado.get(
                "url_origem"
            ),
        )
    )

    resultado["titulo"] = (
        _limpar_titulo_livro(
            titulo_limpo
        )
    )

    resultado["autores"] = (
        _limpar_autores_validos(
            resultado.get(
                "autores"
            )
            or []
        )
    )

    resultado["editora"] = (
        _limpar_editora(
            resultado.get(
                "editora"
            )
        )
    )

    data_publicacao = (
        resultado.get(
            "data_publicacao"
        )
    )

    resultado[
        "data_publicacao"
    ] = (
        _normalizar_data_catalogo(
            data_publicacao
        )
        if data_publicacao
        else None
    )

    generos = []

    for genero in (
        resultado.get(
            "generos"
        )
        or []
    ):
        for normalizado in (
            _generos_da_classificacao(
                genero
            )
            or []
        ):
            if (
                normalizado
                not in generos
            ):
                generos.append(
                    normalizado
                )

    resultado[
        "generos"
    ] = generos[:3]

    return resultado


def _titulo_para_comparacao(
    titulo,
):
    chave = _normalizar_texto(
        titulo
    )

    chave = re.sub(
        r"\b(?:ebook|livro|book|edicao|edition)\b",
        " ",
        chave,
    )

    chave = re.sub(
        r"\s+",
        " ",
        chave,
    ).strip()

    return chave


def _titulos_semelhantes(
    titulo_a,
    titulo_b,
):
    a = _titulo_para_comparacao(
        titulo_a
    )
    b = _titulo_para_comparacao(
        titulo_b
    )

    if not a or not b:
        return False

    if (
        a in b
        or b in a
    ):
        return True

    return (
        SequenceMatcher(
            None,
            a,
            b,
        ).ratio()
        >= 0.72
    )


def _escolher_titulo_consenso(
    resultados,
):
    candidatos = []

    for resultado in resultados:
        titulo = _limpar_titulo_livro(
            resultado.get(
                "titulo"
            )
        )

        if (
            titulo
            and titulo
            not in candidatos
        ):
            candidatos.append(
                titulo
            )

    if not candidatos:
        return None

    def pontuar(
        candidato,
    ):
        apoio = sum(
            1
            for outro
            in candidatos
            if _titulos_semelhantes(
                candidato,
                outro,
            )
        )

        chave = _titulo_para_comparacao(
            candidato
        )

        palavras = [
            palavra
            for palavra in chave.split()
            if palavra
        ]

        bonus_completude = min(
            len(palavras),
            12,
        )

        # Se o título é apenas o início de outro título claramente
        # mais completo, tratamo-lo como truncado.
        penalizacao_truncado = 0

        for outro in candidatos:
            if outro == candidato:
                continue

            chave_outro = (
                _titulo_para_comparacao(
                    outro
                )
            )

            if (
                chave
                and chave_outro.startswith(
                    chave + " "
                )
                and len(
                    chave_outro.split()
                )
                >= len(palavras) + 2
            ):
                penalizacao_truncado = 12
                break

        # Títulos excessivamente longos costumam trazer subtítulos,
        # nomes do site ou texto promocional.
        penalizacao_longo = max(
            0,
            len(palavras) - 15,
        )

        return (
            apoio * 100
            + bonus_completude * 4
            - penalizacao_truncado * 10
            - penalizacao_longo * 5
        )

    return max(
        candidatos,
        key=pontuar,
    )


def _escolher_valor_consenso(
    valores,
):
    limpos = [
        valor
        for valor in valores
        if valor
    ]

    if not limpos:
        return None

    contagens = {}

    original = {}

    for valor in limpos:
        chave = _normalizar_texto(
            valor
        )

        if not chave:
            continue

        contagens[chave] = (
            contagens.get(
                chave,
                0,
            )
            + 1
        )

        original.setdefault(
            chave,
            valor,
        )

    if not contagens:
        return None

    chave_melhor = max(
        contagens,
        key=lambda chave: (
            contagens[chave],
            -len(
                original[chave]
            ),
        ),
    )

    return original[
        chave_melhor
    ]


def _escolher_data_consenso(
    resultados,
):
    datas = []

    for resultado in resultados:
        valor = resultado.get(
            "data_publicacao"
        )

        if not valor:
            continue

        normalizada = (
            _normalizar_data_catalogo(
                valor
            )
        )

        if normalizada:
            datas.append(
                normalizada
            )

    if not datas:
        return None

    por_ano = {}

    for data in datas:
        encontrado = re.search(
            r"\b(19\d{2}|20\d{2})\b",
            str(data),
        )

        if not encontrado:
            continue

        ano = int(
            encontrado.group(1)
        )

        por_ano.setdefault(
            ano,
            []
        ).append(
            data
        )

    if not por_ano:
        return datas[0]

    maior_quantidade = max(
        len(valores)
        for valores
        in por_ano.values()
    )

    anos_candidatos = [
        ano
        for ano, valores
        in por_ano.items()
        if len(valores)
        == maior_quantidade
    ]

    # Num empate entre anos, privilegia o mais antigo,
    # pois tende a corresponder à edição associada ao ISBN.
    ano = min(
        anos_candidatos
    )

    datas_ano = por_ano[
        ano
    ]

    contagens = {}

    for data in datas_ano:
        contagens[data] = (
            contagens.get(
                data,
                0,
            )
            + 1
        )

    maior_frequencia = max(
        contagens.values()
    )

    mais_frequentes = [
        data
        for data, quantidade
        in contagens.items()
        if quantidade
        == maior_frequencia
    ]

    if len(mais_frequentes) == 1:
        escolhida = (
            mais_frequentes[0]
        )
    else:
        # 01/01 é muitas vezes um placeholder criado quando a fonte
        # informou apenas o ano. Se houver uma data mais precisa,
        # prefere-a.
        precisas = [
            data
            for data
            in mais_frequentes
            if not data.endswith(
                "-01-01"
            )
        ]

        escolhida = (
            precisas[0]
            if precisas
            else mais_frequentes[0]
        )

    # Mesmo que 01/01 tenha uma ocorrência a mais, se só representa
    # "ano conhecido" e houver uma data mensal no mesmo ano,
    # a data mensal é mais informativa.
    if escolhida.endswith(
        "-01-01"
    ):
        precisas_mesmo_ano = [
            data
            for data
            in datas_ano
            if not data.endswith(
                "-01-01"
            )
        ]

        if precisas_mesmo_ano:
            escolhida = max(
                precisas_mesmo_ano,
                key=lambda data: (
                    contagens.get(
                        data,
                        0,
                    ),
                    data,
                ),
            )

    return escolhida


def _consolidar_resultados_web(
    resultados,
    isbn_limpo,
):
    limpos = []

    for resultado in resultados:
        limpo = _sanitizar_resultado_web(
            resultado
        )

        if not limpo:
            continue

        if not _resultado_web_valido(
            limpo
        ):
            continue

        limpos.append(
            limpo
        )

    if not limpos:
        return None

    limpos.sort(
        key=_pontuar_metadados,
        reverse=True,
    )

    melhor_individual = limpos[0]

    titulo = (
        _escolher_titulo_consenso(
            limpos
        )
        or melhor_individual.get(
            "titulo"
        )
    )

    # Autores: usa consenso entre fontes quando possível.
    contagem_autores = {}
    forma_autor = {}

    for resultado in limpos:
        for autor in (
            resultado.get(
                "autores"
            )
            or []
        ):
            chave = _normalizar_texto(
                autor
            )

            if not chave:
                continue

            contagem_autores[
                chave
            ] = (
                contagem_autores.get(
                    chave,
                    0,
                )
                + 1
            )

            forma_autor.setdefault(
                chave,
                autor,
            )

    autores = []

    if contagem_autores:
        maior = max(
            contagem_autores.values()
        )

        limite = (
            2
            if maior >= 2
            else 1
        )

        chaves_autores = [
            chave
            for chave, quantidade
            in contagem_autores.items()
            if quantidade >= limite
        ]

        # Se todos aparecem uma única vez, usa apenas os autores
        # do melhor resultado, evitando juntar lixo de páginas diferentes.
        if maior == 1:
            autores = (
                melhor_individual.get(
                    "autores"
                )
                or []
            )
        else:
            autores = [
                forma_autor[
                    chave
                ]
                for chave
                in chaves_autores
            ]

    editora = (
        _escolher_valor_consenso(
            [
                resultado.get(
                    "editora"
                )
                for resultado
                in limpos
            ]
        )
        or melhor_individual.get(
            "editora"
        )
    )

    data_publicacao = (
        _escolher_data_consenso(
            limpos
        )
        or melhor_individual.get(
            "data_publicacao"
        )
    )

    contagem_generos = {}

    for resultado in limpos:
        for genero in (
            resultado.get(
                "generos"
            )
            or []
        ):
            contagem_generos[
                genero
            ] = (
                contagem_generos.get(
                    genero,
                    0,
                )
                + 1
            )

    generos = []

    if contagem_generos:
        maior_genero = max(
            contagem_generos.values()
        )

        generos = [
            genero
            for genero, quantidade
            in sorted(
                contagem_generos.items(),
                key=lambda item: (
                    -item[1],
                    item[0],
                ),
            )
            if (
                quantidade >= 2
                or maior_genero == 1
            )
        ][:3]

    if not generos:
        generos = (
            melhor_individual.get(
                "generos"
            )
            or []
        )[:3]

    resultado_final = {
        "sucesso": True,
        "origem": "Pesquisa Web",
        "titulo": titulo,
        "isbn": isbn_limpo,
        "autores": (
            _limpar_autores_validos(
                autores
            )
        ),
        "editora": (
            _limpar_editora(
                editora
            )
        ),
        "data_publicacao": (
            _normalizar_data_catalogo(
                data_publicacao
            )
            if data_publicacao
            else None
        ),
        "generos": generos,
        "url_origem": (
            melhor_individual.get(
                "url_origem"
            )
        ),
        "fontes_web": [
            resultado.get(
                "url_origem"
            )
            for resultado
            in limpos
            if resultado.get(
                "url_origem"
            )
        ],
    }

    return (
        resultado_final
        if _resultado_web_valido(
            resultado_final
        )
        else melhor_individual
    )


def _pontuar_metadados(dados):
    if not dados:
        return -100

    sanitizado = (
        _sanitizar_resultado_web(
            dados
        )
    )

    if not sanitizado:
        return -100

    titulo = sanitizado.get(
        "titulo"
    )

    if _titulo_invalido(
        titulo
    ):
        return -100

    pontos = 5

    autores = sanitizado.get(
        "autores"
    ) or []

    if autores:
        pontos += 5

    if sanitizado.get(
        "editora"
    ):
        pontos += 3

    if sanitizado.get(
        "data_publicacao"
    ):
        pontos += 2

    if sanitizado.get(
        "generos"
    ):
        pontos += 2

    if (
        sanitizado.get(
            "url_origem"
        )
        and sanitizado.get(
            "isbn"
        )
    ):
        pontos += 1

    return pontos


def _resultado_web_valido(dados):
    if not dados:
        return False

    sanitizado = (
        _sanitizar_resultado_web(
            dados
        )
    )

    if not sanitizado:
        return False

    if _titulo_invalido(
        sanitizado.get(
            "titulo"
        )
    ):
        return False

    if (
        not sanitizado.get(
            "autores"
        )
        and not sanitizado.get(
            "editora"
        )
    ):
        return False

    return (
        _pontuar_metadados(
            sanitizado
        )
        >= 9
    )


def _extrair_dados_texto(texto, url, isbn, origem="Pesquisa Web"):
    texto = str(texto or "")
    isbn_limpo = normalizar_isbn(isbn)

    if not texto or _conteudo_bloqueado(texto):
        return None

    # A ficha só é aceite se contiver realmente o ISBN pesquisado.
    texto_isbn = re.sub(r"[^0-9Xx]", "", texto).upper()
    if isbn_limpo not in texto_isbn:
        return None

    titulo = _linha_valor(texto, [r"T[ií]tulo", "Title"])

    if not titulo:
        for candidato in re.findall(r"(?im)^#\s+(.+?)\s*$", texto):
            candidato = candidato.strip(" #|")
            if not _titulo_invalido(candidato) and len(candidato) <= 180:
                titulo = candidato
                break

    autores_titulo = []

    if titulo:
        titulo = re.sub(r"\s*[-|]\s*(?:WOOK|Bertrand|FNAC).*?$", "", titulo, flags=re.I).strip()
        titulo = re.sub(r"\s+(?:by|de)\s+[^|]{2,100}\s*[-|].*$", "", titulo, flags=re.I).strip()

        # WOOK costuma usar um H1 do tipo:
        # "A História de Uma Serva de Margaret Atwood".
        # A expressão é gananciosa para separar no ÚLTIMO " de ",
        # preservando títulos que já contenham a palavra "de".
        combinado = re.match(
            r"^(.+)\s+(?:de|by)\s+([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][^|#]{1,100})$",
            titulo,
            flags=re.I,
        )
        if combinado:
            titulo_candidato = combinado.group(1).strip()
            autor_candidato = combinado.group(2).strip(" .-|")
            palavras_autor = [p for p in autor_candidato.split() if p]

            if 1 <= len(palavras_autor) <= 8:
                titulo = titulo_candidato
                autores_titulo = [autor_candidato]

    autores = []

    autor_campo = _linha_valor(
        texto,
        [
            r"Autor(?:\(es\))?",
            "Author",
            "Por",
            "By",
        ],
    )

    if autor_campo:
        autores = [
            parte.strip()
            for parte in re.split(r"\s*[;,]\s*|\s+e\s+|\s+and\s+", autor_campo)
            if parte.strip()
        ]

    if not autores and autores_titulo:
        autores = autores_titulo

    if not autores:
        autores = _autor_perto_titulo(texto, titulo)

    autores = _remover_creditos_nao_autor(autores, texto)

    editora = _linha_valor(
        texto,
        [
            r"Editor/Editora",
            "Editorial",
            "Editor",
            "Editora",
            "Publisher",
        ],
    )

    data_publicacao = _linha_valor(
        texto,
        [
            r"Data de publica[cç][aã]o",
            r"Data de Lan[cç]amento",
            r"Edi[cç][aã]o/reimpress[aã]o",
            r"Ano de edi[cç][aã]o",
            r"Ano de publica[cç][aã]o",
            r"Fecha de lanzamiento",
            r"Release Date",
            r"Published",
            r"Publication Date",
        ],
    )

    if not data_publicacao and editora:
        ano_editora = re.search(
            r"\b(19\d{2}|20\d{2})\b",
            str(editora),
        )
        if ano_editora:
            data_publicacao = ano_editora.group(1)
            editora = re.sub(
                r"\s*,?\s*\b(19\d{2}|20\d{2})\b\s*$",
                "",
                str(editora),
            ).strip(" ,-")

    data_publicacao = _normalizar_data_catalogo(data_publicacao)

    classificacao = _extrair_classificacao_tematica(texto)

    if not classificacao:
        classificacao = _linha_valor(
            texto,
            [
                r"Classifica[cç][aã]o Tem[aá]tica",
                "Temática",
                "Tematica",
                "Categoria",
                r"Categor[ií]a",
                "Categories",
                "Subject",
                "Subjects",
                "Tags",
            ],
        )

    generos = _generos_da_ficha(
        texto,
        classificacao=classificacao,
    )

    dados = {
        "sucesso": True,
        "origem": origem,
        "titulo": titulo,
        "isbn": isbn_limpo,
        "autores": autores,
        "editora": editora,
        "data_publicacao": data_publicacao,
        "generos": generos,
        "url_origem": url,
    }

    dados = (
        _sanitizar_resultado_web(
            dados
        )
    )

    return (
        dados
        if _resultado_web_valido(
            dados
        )
        else None
    )


def _extrair_dados_html(html, url, isbn, origem="Pesquisa Web"):
    html = str(html or "")

    if not html or _conteudo_bloqueado(html):
        return None

    isbn_limpo = normalizar_isbn(isbn)
    html_isbn = re.sub(r"[^0-9Xx]", "", html).upper()

    if isbn_limpo not in html_isbn:
        return None

    jsonld = _jsonld_livro(html, isbn_limpo)
    texto_pagina = _html_para_texto(html)

    dados_texto = _extrair_dados_texto(
        texto_pagina,
        url,
        isbn_limpo,
        origem,
    )

    if jsonld:
        titulo = jsonld.get("titulo")
        autores = _remover_creditos_nao_autor(
            jsonld.get("autores") or [],
            texto_pagina,
        )
        editora = jsonld.get("editora")
        data_publicacao = _normalizar_data_catalogo(
            jsonld.get("data_publicacao")
        )
        generos = []

        for genero in jsonld.get("generos") or []:
            generos.extend(_generos_da_classificacao(genero) or [genero])

        if not generos:
            generos = _generos_da_ficha(
                texto_pagina,
                html=html,
            )

        dados_json = {
            "sucesso": True,
            "origem": origem,
            "titulo": titulo,
            "isbn": isbn_limpo,
            "autores": autores,
            "editora": editora,
            "data_publicacao": data_publicacao,
            "generos": generos,
            "url_origem": url,
        }

        if dados_texto:
            # Completa JSON-LD apenas com campos vazios; nunca mistura autores
            # adicionais encontrados numa biografia mais abaixo da página.
            for campo in ("autores", "editora", "data_publicacao", "generos"):
                if not dados_json.get(campo) and dados_texto.get(campo):
                    dados_json[campo] = dados_texto[campo]

        dados_json = (
            _sanitizar_resultado_web(
                dados_json
            )
        )

        if _resultado_web_valido(
            dados_json
        ):
            return dados_json

    # Fallback normal de texto da própria ficha.
    if dados_texto:
        return dados_texto

    # Último fallback: título de OpenGraph/H1 + campos rotulados.
    titulo = _meta_html(html, "og:title") or _h1_html(html)

    if titulo:
        titulo = re.sub(r"\s*[-|]\s*(?:WOOK|Bertrand|FNAC).*?$", "", titulo, flags=re.I).strip()

    autores = _autor_perto_titulo(texto_pagina, titulo)
    autores = _remover_creditos_nao_autor(autores, texto_pagina)

    editora = _linha_valor(
        texto_pagina,
        ["Editor", "Editora", "Publisher"],
    )

    data_publicacao = _normalizar_data_catalogo(
        _linha_valor(
            texto_pagina,
            [
                r"Data de publica[cç][aã]o",
                r"Data de Lan[cç]amento",
                r"Edi[cç][aã]o/reimpress[aã]o",
            ],
        )
    )

    classificacao = _extrair_classificacao_tematica(texto_pagina)

    if not classificacao:
        classificacao = _linha_valor(
            texto_pagina,
            [r"Classifica[cç][aã]o Tem[aá]tica", "Temática", "Categoria", "Categories"],
        )

    dados = {
        "sucesso": True,
        "origem": origem,
        "titulo": titulo,
        "isbn": isbn_limpo,
        "autores": autores,
        "editora": editora,
        "data_publicacao": data_publicacao,
        "generos": _generos_da_ficha(
            texto_pagina,
            classificacao=classificacao,
            html=html,
        ),
        "url_origem": url,
    }

    dados = (
        _sanitizar_resultado_web(
            dados
        )
    )

    return (
        dados
        if _resultado_web_valido(
            dados
        )
        else None
    )


# Descoberta de páginas por ISBN


def _extrair_links_html(html, base_url):
    links = []
    vistos = set()

    for href in re.findall(
        r"href\s*=\s*[\"']([^\"']+)[\"']",
        str(html or ""),
        flags=re.I,
    ):
        href = unescape(href).strip()

        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue

        absoluto = urljoin(base_url, href)

        # DuckDuckGo redireciona através de uddg=URL.
        if "duckduckgo.com/l/?" in absoluto:
            parametros = parse_qs(urlparse(absoluto).query)
            destino = parametros.get("uddg")
            if destino:
                absoluto = unquote(destino[0])

        if absoluto not in vistos:
            vistos.add(absoluto)
            links.append(absoluto)

    return links


def _extrair_links_markdown(texto):
    links = []
    vistos = set()

    padroes = [
        r"\[[^\]]*\]\((https?://[^)\s]+)",
        r"https?://[^\s<>()\]\[\"']+",
    ]

    for padrao in padroes:
        for bruto in re.findall(padrao, str(texto or "")):
            link = unescape(bruto).strip().rstrip(".,;:")

            if link and link not in vistos:
                vistos.add(link)
                links.append(link)

    return links


def _resultado_ddgs_valido(resultado):
    if not isinstance(resultado, dict):
        return False

    href = str(
        resultado.get("href")
        or resultado.get("url")
        or ""
    ).strip()

    if not href:
        return False

    return _dominio_confiavel(
        href
    )


def _pesquisar_web_ddgs(isbn):
    isbn_limpo = normalizar_isbn(
        isbn
    )

    consulta = f'"{isbn_limpo}"'
    candidatos_por_href = {}

    try:
        resultados = DDGS(
            timeout=5
        ).text(
            consulta,
            region="pt-pt",
            safesearch="moderate",
            max_results=10,
            backend="google, brave, bing",
        ) or []
    except Exception as erro:
        print(
            "[BookCatalog] Pesquisa principal falhou:",
            erro,
        )
        try:
            resultados = DDGS(
                timeout=5
            ).text(
                consulta,
                region="pt-pt",
                safesearch="moderate",
                max_results=8,
                backend="auto",
            ) or []
        except Exception:
            resultados = []

    print(
        f"[BookCatalog] Pesquisa Web por ISBN: "
        f"{len(resultados)} resultado(s)."
    )

    _juntar_candidatos_ddgs(
        candidatos_por_href,
        resultados,
    )

    candidatos = list(
        candidatos_por_href.values()
    )

    candidatos.sort(
        key=_pontuar_candidato_busca,
        reverse=True,
    )

    return candidatos[:8]


def _juntar_candidatos_ddgs(
    destino,
    resultados,
):
    for resultado in (
        resultados
        or []
    ):
        if not _resultado_ddgs_valido(
            resultado
        ):
            continue

        href = str(
            resultado.get(
                "href"
            )
            or resultado.get(
                "url"
            )
            or ""
        ).strip()

        if not href:
            continue

        titulo = (
            _limpar_texto_exibicao(
                resultado.get(
                    "title"
                )
                or ""
            )
        )

        corpo = (
            _limpar_texto_exibicao(
                resultado.get(
                    "body"
                )
                or ""
            )
        )

        if href not in destino:
            destino[
                href
            ] = {
                "href": href,
                "title": titulo,
                "body": corpo,
            }
            continue

        existente = destino[
            href
        ]

        if (
            titulo
            and titulo
            not in existente[
                "title"
            ]
        ):
            existente[
                "title"
            ] = (
                f"{existente['title']} | {titulo}"
                if existente[
                    "title"
                ]
                else titulo
            )

        if (
            corpo
            and corpo
            not in existente[
                "body"
            ]
        ):
            existente[
                "body"
            ] = (
                f"{existente['body']} | {corpo}"
                if existente[
                    "body"
                ]
                else corpo
            )


def _pesquisar_web_por_identidade(
    titulo,
    autores,
    isbn,
):
    titulo_limpo = (
        _limpar_titulo_livro(
            titulo
        )
    )

    autores_limpos = (
        _limpar_autores_validos(
            autores
            or []
        )
    )

    if not titulo_limpo:
        return []

    autor_principal = (
        autores_limpos[0]
        if autores_limpos
        else ""
    )

    isbn_limpo = normalizar_isbn(
        isbn
    )

    if autor_principal:
        consulta = (
            f'"{titulo_limpo}" '
            f'"{autor_principal}" '
            f'"{isbn_limpo}"'
        )
    else:
        consulta = (
            f'"{titulo_limpo}" '
            f'"{isbn_limpo}"'
        )

    candidatos_por_href = {}

    try:
        resultados = DDGS(
            timeout=5
        ).text(
            consulta,
            region="pt-pt",
            safesearch="moderate",
            max_results=8,
            backend="google, brave, bing",
        ) or []
    except Exception:
        resultados = []

    _juntar_candidatos_ddgs(
        candidatos_por_href,
        resultados,
    )

    candidatos = list(
        candidatos_por_href.values()
    )

    candidatos.sort(
        key=_pontuar_candidato_busca,
        reverse=True,
    )

    return candidatos[:6]


def _metadados_objetivos_de_snippets(
    candidatos,
    isbn_limpo,
    titulo_referencia,
):
    editoras = []
    datas = []
    generos = []

    for candidato in candidatos or []:
        if not isinstance(candidato, dict):
            continue

        href = str(candidato.get("href") or "")
        titulo_busca = candidato.get("title") or ""
        corpo_busca = candidato.get("body") or ""
        evidencia = f"{href} {titulo_busca} {corpo_busca}"
        evidencia_isbn = re.sub(r"[^0-9Xx]", "", evidencia).upper()

        if isbn_limpo not in evidencia_isbn:
            continue

        if any(marcador in href.lower() for marcador in ("/editions", "/edicoes", "work/editions")):
            continue

        titulo_candidato = _limpar_titulo_resultado_busca(titulo_busca)
        if (
            titulo_candidato
            and titulo_referencia
            and not _titulos_semelhantes(titulo_candidato, titulo_referencia)
        ):
            continue

        editora = _extrair_editora_resultado_busca(titulo_busca, corpo_busca)
        if editora:
            editora = _limpar_editora(editora)
            if editora:
                editoras.append(editora)

        data = _extrair_data_resultado_busca(titulo_busca, corpo_busca)
        if data:
            datas.append({"data_publicacao": data})

        for genero in _extrair_generos_resultado_busca(titulo_busca, corpo_busca) or []:
            if genero not in generos:
                generos.append(genero)

    return {
        "editora": _escolher_valor_consenso(editoras) if editoras else None,
        "data_publicacao": _escolher_data_consenso(datas) if datas else None,
        "generos": generos[:3],
    }


def _enriquecer_por_identidade(
    consolidado,
    isbn_limpo,
):
    if not consolidado:
        return consolidado

    if (
        consolidado.get("editora")
        and consolidado.get("data_publicacao")
        and consolidado.get("generos")
    ):
        return consolidado

    candidatos = (
        _pesquisar_web_por_identidade(
            consolidado.get(
                "titulo"
            ),
            consolidado.get(
                "autores"
            )
            or [],
            isbn_limpo,
        )
    )

    if not candidatos:
        return consolidado

    snippets = (
        _metadados_objetivos_de_snippets(
            candidatos,
            isbn_limpo,
            consolidado.get(
                "titulo"
            ),
        )
    )

    if (
        not consolidado.get(
            "editora"
        )
        and snippets.get(
            "editora"
        )
    ):
        consolidado[
            "editora"
        ] = snippets[
            "editora"
        ]

    if (
        not consolidado.get(
            "data_publicacao"
        )
        and snippets.get(
            "data_publicacao"
        )
    ):
        consolidado[
            "data_publicacao"
        ] = snippets[
            "data_publicacao"
        ]

    generos = list(
        consolidado.get(
            "generos"
        )
        or []
    )

    for genero in (
        snippets.get(
            "generos"
        )
        or []
    ):
        if genero not in generos:
            generos.append(
                genero
            )

    consolidado[
        "generos"
    ] = generos[:3]

    # Só abre páginas se ainda faltar informação depois dos snippets.
    if (
        consolidado.get("editora")
        and consolidado.get("data_publicacao")
        and consolidado.get("generos")
    ):
        return consolidado

    resultados = []
    candidatos_paginas = candidatos[:3]

    if not candidatos_paginas:
        return consolidado

    with ThreadPoolExecutor(
        max_workers=len(
            candidatos_paginas
        )
    ) as executor:
        futuros = {
            executor.submit(
                _ler_candidato_web,
                candidato,
                isbn_limpo,
            ): candidato
            for candidato
            in candidatos_paginas
        }

        for futuro in as_completed(
            futuros
        ):
            try:
                dados = futuro.result()
            except Exception:
                dados = None

            if dados:
                resultados.append(
                    dados
                )

    complemento = (
        _consolidar_resultados_web(
            resultados,
            isbn_limpo,
        )
        if resultados
        else None
    )

    if not complemento:
        return consolidado

    if (
        not consolidado.get(
            "editora"
        )
        and complemento.get(
            "editora"
        )
    ):
        consolidado[
            "editora"
        ] = complemento[
            "editora"
        ]

    if (
        not consolidado.get(
            "data_publicacao"
        )
        and complemento.get(
            "data_publicacao"
        )
    ):
        consolidado[
            "data_publicacao"
        ] = complemento[
            "data_publicacao"
        ]

    generos = list(
        consolidado.get(
            "generos"
        )
        or []
    )

    for genero in (
        complemento.get(
            "generos"
        )
        or []
    ):
        if genero not in generos:
            generos.append(
                genero
            )

    consolidado[
        "generos"
    ] = generos[:3]

    return consolidado


def _descobrir_links_produto(isbn):
    isbn_limpo = normalizar_isbn(
        isbn
    )

    links = _pesquisar_web_ddgs(
        isbn_limpo
    )

    print(
        f"[BookCatalog] Pesquisa Web geral encontrou "
        f"{len(links)} link(s) candidato(s)."
    )

    return links


def _limpar_titulo_resultado_busca(
    valor,
):
    titulo = (
        _limpar_texto_exibicao(
            valor
        )
    )

    if not titulo:
        return None

    # Remove segmentos finais típicos do site/loja.
    segmentos = [
        segmento.strip()
        for segmento in re.split(
            r"\s+[|–—-]\s+",
            titulo,
        )
        if segmento.strip()
    ]

    while (
        len(segmentos) > 1
        and any(
            termo
            in _normalizar_texto(
                segmentos[-1]
            )
            for termo in (
                "wook",
                "bertrand",
                "fnac",
                "amazon",
                "penguin",
                "livros",
                "livro",
                "ebook",
                "online",
                "store",
                "shop",
            )
        )
    ):
        segmentos.pop()

    titulo = " - ".join(
        segmentos
    ).strip()

    # "Título de Jeff Kinney" -> guarda só o título;
    # o autor é extraído separadamente.
    encontrado = re.match(
        r"^(.+?)\s+de\s+([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÿ'’.\- ]{2,70})$",
        titulo,
    )

    if encontrado:
        possivel_autor = (
            encontrado.group(2)
            .strip()
        )

        if _parece_nome_autor(
            possivel_autor
        ):
            titulo = (
                encontrado.group(1)
                .strip()
            )

    return _limpar_titulo_livro(
        titulo
    )


def _extrair_autor_resultado_busca(
    titulo_busca,
    corpo_busca,
):
    titulo = (
        _limpar_texto_exibicao(
            titulo_busca
        )
    )

    corpo = (
        _limpar_texto_exibicao(
            corpo_busca
        )
    )

    candidatos = []

    if titulo:
        padroes_titulo = [
            r"\s+de\s+([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÿ0-9'’.\- ]{2,70})(?:\s+[|–—-]|$)",
            r"\s+by\s+([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÿ0-9'’.\- ]{2,70})(?:\s+[|–—-]|$)",
        ]

        for padrao in padroes_titulo:
            encontrado = re.search(
                padrao,
                titulo,
                flags=re.I,
            )

            if encontrado:
                candidatos.append(
                    encontrado.group(1)
                )

    if corpo:
        padroes = [
            r"Autor(?:\(a\)|es)?\s*:?\s*([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÿ0-9'’.\- ]{2,70})",
            r"Author\s*:?\s*([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÿ0-9'’.\- ]{2,70})",
        ]

        for padrao in padroes:
            encontrado = re.search(
                padrao,
                corpo,
                flags=re.I,
            )

            if encontrado:
                valor = re.split(
                    r"\b(?:ISBN|EAN|Editora|Editor|Publisher|Data|Date|Páginas|Paginas|Género|Genero|Categoria|Temática|Tematica)\b",
                    encontrado.group(1),
                    maxsplit=1,
                    flags=re.I,
                )[0].strip(
                    " .,:;|-"
                )

                candidatos.append(
                    valor
                )

    limpos = (
        _limpar_autores_validos(
            candidatos
        )
    )

    return limpos[:3]


def _extrair_valor_rotulado_busca(
    texto,
    rotulos,
):
    texto = _limpar_texto_exibicao(
        texto
    )

    if not texto:
        return None

    limites = (
        r"Autor(?:\(es\)|\(a\))?",
        r"Author",
        r"Editor(?:a)?",
        r"Publisher",
        r"Editorial",
        r"ISBN",
        r"EAN",
        r"Data\s+de\s+publica[cç][aã]o",
        r"Data\s+de\s+Lan[cç]amento",
        r"Published",
        r"Publication\s+Date",
        r"Classifica[cç][aã]o\s+Tem[aá]tica",
        r"Categoria(?:s)?",
        r"G[eé]nero(?:s)?",
        r"P[aá]ginas",
        r"Pages",
        r"Idioma",
        r"Language",
        r"Dimens[oõ]es",
        r"Encaderna[cç][aã]o",
    )

    limite = "|".join(
        limites
    )

    for rotulo in rotulos:
        padrao = (
            rf"(?is)(?:{rotulo})\s*:?\s*"
            rf"(.+?)"
            rf"(?=\s+(?:{limite})\s*:|$)"
        )

        encontrado = re.search(
            padrao,
            texto,
        )

        if not encontrado:
            continue

        valor = (
            _limpar_texto_exibicao(
                encontrado.group(1)
            )
        )

        valor = valor.strip(
            " .,:;|-"
        )

        if valor:
            return valor

    return None


def _extrair_editora_resultado_busca(
    titulo_busca,
    corpo_busca,
):
    texto = (
        f"{titulo_busca} "
        f"{corpo_busca}"
    )

    valor = _extrair_valor_rotulado_busca(
        texto,
        [
            r"Editor(?:a)?",
            r"Publisher",
            r"Editorial",
        ],
    )

    return _limpar_editora(
        valor
    )


def _extrair_data_resultado_busca(
    titulo_busca,
    corpo_busca,
):
    texto = (
        f"{titulo_busca} "
        f"{corpo_busca}"
    )

    valor = _extrair_valor_rotulado_busca(
        texto,
        [
            r"Data\s+de\s+publica[cç][aã]o",
            r"Data\s+de\s+Lan[cç]amento",
            r"Edi[cç][aã]o",
            r"Published",
            r"Publication\s+Date",
        ],
    )

    return (
        _normalizar_data_catalogo(
            valor
        )
        if valor
        else None
    )


def _extrair_generos_resultado_busca(
    titulo_busca,
    corpo_busca,
):
    texto = (
        f"{titulo_busca} "
        f"{corpo_busca}"
    )

    classificacao = (
        _extrair_valor_rotulado_busca(
            texto,
            [
                r"Classifica[cç][aã]o\s+Tem[aá]tica",
                r"Tem[aá]tica",
                r"Sub-?categoria",
                r"Categoria(?:s)?",
                r"G[eé]nero(?:s)?",
                r"Subject(?:s)?",
            ],
        )
    )

    if not classificacao:
        return []

    normalizado = (
        _normalizar_texto(
            classificacao
        )
    )

    generos = (
        _generos_da_classificacao(
            classificacao
        )
        or []
    )

    # Termos editoriais comuns em catálogos portugueses.
    if (
        any(
            termo in normalizado
            for termo in (
                "infantis e juvenis",
                "infantil e juvenil",
                "literatura juvenil",
                "juvenil",
                "10 a 14 anos",
                "10-14",
                "10 14",
            )
        )
        and "Infantil"
        not in generos
    ):
        generos.append(
            "Infantil"
        )

    # "Não Ficção" não deve ser confundido com "Ficção".
    if (
        "nao ficcao"
        in normalizado
    ):
        generos = [
            genero
            for genero in generos
            if genero != "Ficção"
        ]

    return generos[:3]


def _pontuar_candidato_busca(
    candidato,
):
    if not isinstance(
        candidato,
        dict,
    ):
        return 0

    texto = (
        f"{candidato.get('title', '')} "
        f"{candidato.get('body', '')}"
    )

    normalizado = (
        _normalizar_texto(
            texto
        )
    )

    pontos = 0

    termos = (
        (
            (
                "data de lancamento",
                "data de publicacao",
                "published",
                "publication date",
                "edicao",
            ),
            5,
        ),
        (
            (
                "classificacao tematica",
                "categoria",
                "genero",
                "fantasia",
                "juvenil",
                "infantil",
            ),
            5,
        ),
        (
            (
                "editora",
                "editor",
                "publisher",
                "editorial",
            ),
            4,
        ),
        (
            (
                "autor",
                "author",
            ),
            3,
        ),
        (
            (
                "isbn",
                "ean",
            ),
            2,
        ),
    )

    for palavras, valor in termos:
        if any(
            palavra in normalizado
            for palavra in palavras
        ):
            pontos += valor

    return pontos


def _extrair_metadados_globais_busca(
    candidatos,
    isbn_limpo,
):
    editoras = []
    datas = []
    generos = []

    for candidato in candidatos:
        dados = _dados_do_resultado_busca(
            candidato,
            isbn_limpo,
        )

        if not dados:
            continue

        editora = dados.get(
            "editora"
        )

        if editora:
            editora = (
                _limpar_editora(
                    editora
                )
            )

            if editora:
                editoras.append(
                    editora
                )

        data = dados.get(
            "data_publicacao"
        )

        if data:
            data = (
                _normalizar_data_catalogo(
                    data
                )
            )

            if data:
                datas.append(
                    {
                        "data_publicacao": data
                    }
                )

        for genero in (
            dados.get(
                "generos"
            )
            or []
        ):
            if (
                genero
                and genero
                not in generos
            ):
                generos.append(
                    genero
                )

    editora_final = (
        _escolher_valor_consenso(
            editoras
        )
        if editoras
        else None
    )

    data_final = (
        _escolher_data_consenso(
            datas
        )
        if datas
        else None
    )

    return {
        "editora": editora_final,
        "data_publicacao": data_final,
        "generos": generos[:3],
    }


def _dados_do_resultado_busca(
    candidato,
    isbn,
):
    if not isinstance(
        candidato,
        dict,
    ):
        return None

    href = str(
        candidato.get(
            "href"
        )
        or ""
    ).strip()

    titulo_busca = (
        candidato.get(
            "title"
        )
        or ""
    )

    corpo_busca = (
        candidato.get(
            "body"
        )
        or ""
    )

    evidencia = (
        f"{href} "
        f"{titulo_busca} "
        f"{corpo_busca}"
    )

    if normalizar_isbn(
        isbn
    ) not in re.sub(
        r"[^0-9Xx]",
        "",
        evidencia,
    ).upper():
        return None

    titulo = (
        _limpar_titulo_resultado_busca(
            titulo_busca
        )
    )

    autores = (
        _extrair_autor_resultado_busca(
            titulo_busca,
            corpo_busca,
        )
    )

    editora = (
        _extrair_editora_resultado_busca(
            titulo_busca,
            corpo_busca,
        )
    )

    data_publicacao = (
        _extrair_data_resultado_busca(
            titulo_busca,
            corpo_busca,
        )
    )

    generos = (
        _extrair_generos_resultado_busca(
            titulo_busca,
            corpo_busca,
        )
    )

    if not titulo:
        return None

    dados = {
        "sucesso": True,
        "origem": "Pesquisa Web",
        "titulo": titulo,
        "isbn": normalizar_isbn(
            isbn
        ),
        "autores": autores,
        "editora": editora,
        "data_publicacao": (
            data_publicacao
        ),
        "generos": generos,
        "url_origem": href,
    }

    return (
        _sanitizar_resultado_web(
            dados
        )
    )


def _mesclar_pagina_com_busca(
    dados_pagina,
    dados_busca,
):
    if not dados_pagina:
        return None

    pagina = (
        _sanitizar_resultado_web(
            dict(
                dados_pagina
            )
        )
    )

    if not pagina:
        return None

    if not dados_busca:
        return pagina

    busca = (
        _sanitizar_resultado_web(
            dict(
                dados_busca
            )
        )
    )

    if not busca:
        return pagina

    titulo_pagina = (
        pagina.get(
            "titulo"
        )
    )

    titulo_busca = (
        busca.get(
            "titulo"
        )
    )

    # O título da pesquisa só corrige um título claramente truncado.
    if (
        titulo_pagina
        and titulo_busca
    ):
        chave_pagina = (
            _titulo_para_comparacao(
                titulo_pagina
            )
        )

        chave_busca = (
            _titulo_para_comparacao(
                titulo_busca
            )
        )

        if (
            chave_pagina
            and chave_busca
            and chave_busca.startswith(
                chave_pagina + " "
            )
            and len(
                chave_busca.split()
            )
            >= len(
                chave_pagina.split()
            ) + 2
        ):
            pagina[
                "titulo"
            ] = titulo_busca

    # Autor do snippet só entra se a página não tiver autor.
    autores_pagina = (
        _limpar_autores_validos(
            pagina.get(
                "autores"
            )
            or []
        )
    )

    autores_busca = (
        _limpar_autores_validos(
            busca.get(
                "autores"
            )
            or []
        )
    )

    if autores_pagina:
        pagina[
            "autores"
        ] = autores_pagina
    elif autores_busca:
        pagina[
            "autores"
        ] = autores_busca

    # Campos objetivos podem ser enriquecidos pelo snippet.
    if (
        not pagina.get(
            "editora"
        )
        and busca.get(
            "editora"
        )
    ):
        pagina[
            "editora"
        ] = busca.get(
            "editora"
        )

    if (
        not pagina.get(
            "data_publicacao"
        )
        and busca.get(
            "data_publicacao"
        )
    ):
        pagina[
            "data_publicacao"
        ] = busca.get(
            "data_publicacao"
        )

    generos_pagina = (
        pagina.get(
            "generos"
        )
        or []
    )

    generos_busca = (
        busca.get(
            "generos"
        )
        or []
    )

    for genero in generos_busca:
        if genero not in generos_pagina:
            generos_pagina.append(
                genero
            )

    pagina[
        "generos"
    ] = generos_pagina[:3]

    return (
        _sanitizar_resultado_web(
            pagina
        )
    )


# Leitura e pesquisa web


def _ler_candidato_web(
    candidato,
    isbn,
):
    isbn_limpo = normalizar_isbn(
        isbn
    )

    if isinstance(
        candidato,
        dict,
    ):
        url = str(
            candidato.get(
                "href"
            )
            or ""
        ).strip()
    else:
        url = str(
            candidato
            or ""
        ).strip()

        candidato = {
            "href": url,
            "title": "",
            "body": "",
        }

    if not url:
        return None

    url_normalizada = (
        url.lower()
    )

    if any(
        marcador in url_normalizada
        for marcador in (
            "/editions",
            "/edicoes",
            "work/editions",
        )
    ):
        return None

    dados_busca = (
        _dados_do_resultado_busca(
            candidato,
            isbn_limpo,
        )
    )

    try:
        html, url_final = _obter_html(
            url,
            timeout=4,
        )

        if not _conteudo_bloqueado(
            html
        ):
            dados = _extrair_dados_html(
                html,
                url_final,
                isbn_limpo,
                "Pesquisa Web",
            )

            if dados:
                return (
                    _mesclar_pagina_com_busca(
                        dados,
                        dados_busca,
                    )
                )

    except Exception:
        pass

    try:
        extraido = DDGS(
            timeout=4
        ).extract(
            url,
            fmt="text_markdown",
        )

        markdown = ""

        if isinstance(
            extraido,
            dict,
        ):
            markdown = str(
                extraido.get(
                    "content"
                )
                or ""
            )

        if (
            markdown
            and not _conteudo_bloqueado(
                markdown
            )
        ):
            dados = _extrair_dados_texto(
                markdown,
                url,
                isbn_limpo,
                "Pesquisa Web",
            )

            if dados:
                return (
                    _mesclar_pagina_com_busca(
                        dados,
                        dados_busca,
                    )
                )

    except Exception:
        pass

    return None


def procurar_livro_google_books_web(isbn):
    """
    Mantido por compatibilidade com o restante fluxo.
    Não faz scraping direto do Google Books, que costuma responder 403.
    A pesquisa Web geral é tratada pelo DDGS.
    """
    return {
        "sucesso": False,
        "erro": (
            "Pesquisa direta no Google Books Web desativada. "
            "A pesquisa Web geral será usada."
        ),
    }


def procurar_livro_pesquisa_web(isbn):
    isbn_limpo = normalizar_isbn(
        isbn
    )

    candidatos = (
        _descobrir_links_produto(
            isbn_limpo
        )
    )

    print(
        f"[BookCatalog] Pesquisa Web encontrou "
        f"{len(candidatos)} candidato(s)."
    )

    if not candidatos:
        return {
            "sucesso": False,
            "erro": (
                "Nenhuma página candidata foi encontrada "
                "na pesquisa Web geral."
            ),
        }

    resultados = []
    candidatos_paginas = candidatos[:4]

    with ThreadPoolExecutor(
        max_workers=len(
            candidatos_paginas
        )
    ) as executor:
        futuros = {
            executor.submit(
                _ler_candidato_web,
                candidato,
                isbn_limpo,
            ): candidato
            for candidato
            in candidatos_paginas
        }

        for futuro in as_completed(
            futuros
        ):
            try:
                dados = futuro.result()
            except Exception:
                dados = None

            if dados:
                resultados.append(
                    dados
                )

    consolidado = (
        _consolidar_resultados_web(
            resultados,
            isbn_limpo,
        )
    )

    if not consolidado:
        return {
            "sucesso": False,
            "erro": (
                "As páginas encontradas não continham "
                "uma ficha bibliográfica válida para este ISBN."
            ),
        }

    snippets = (
        _metadados_objetivos_de_snippets(
            candidatos,
            isbn_limpo,
            consolidado.get(
                "titulo"
            ),
        )
    )

    if (
        not consolidado.get(
            "editora"
        )
        and snippets.get(
            "editora"
        )
    ):
        consolidado[
            "editora"
        ] = snippets[
            "editora"
        ]

    if (
        not consolidado.get(
            "data_publicacao"
        )
        and snippets.get(
            "data_publicacao"
        )
    ):
        consolidado[
            "data_publicacao"
        ] = snippets[
            "data_publicacao"
        ]

    generos = list(
        consolidado.get(
            "generos"
        )
        or []
    )

    for genero in (
        snippets.get(
            "generos"
        )
        or []
    ):
        if genero not in generos:
            generos.append(
                genero
            )

    consolidado[
        "generos"
    ] = generos[:3]

    consolidado = (
        _enriquecer_por_identidade(
            consolidado,
            isbn_limpo,
        )
    )

    consolidado[
        "titulo"
    ] = (
        _limpar_titulo_com_autores(
            consolidado.get(
                "titulo"
            ),
            consolidado.get(
                "autores"
            )
            or [],
        )
        or consolidado.get(
            "titulo"
        )
    )

    print(
        "[BookCatalog] Resultado Web final: "
        f"título={consolidado.get('titulo')!r} | "
        f"autor={consolidado.get('autores')!r} | "
        f"editora={consolidado.get('editora')!r} | "
        f"data={consolidado.get('data_publicacao')!r} | "
        f"géneros={consolidado.get('generos')!r}"
    )

    return consolidado


# Fluxo final usado pelo SABIN


def _normalizar_lista_metadados(valor):
    if not valor:
        return []

    if isinstance(valor, str):
        valores = [valor]
    else:
        valores = list(valor)

    resultado = []
    vistos = set()

    for item in valores:
        texto_item = (
            _limpar_texto_exibicao(
                item
            )
        )

        if not texto_item:
            continue

        chave = _normalizar_texto(
            texto_item
        )

        if chave in vistos:
            continue

        vistos.add(
            chave
        )

        resultado.append(
            texto_item
        )

    return resultado


def _mesclar_resultados_livro(
    resultados,
    isbn_limpo,
):
    validos = []

    for resultado in resultados:
        if not (
            resultado
            and resultado.get(
                "sucesso"
            )
        ):
            continue

        if (
            resultado.get(
                "origem"
            )
            == "Pesquisa Web"
        ):
            resultado = (
                _sanitizar_resultado_web(
                    resultado
                )
            )

        validos.append(
            resultado
        )

    if not validos:
        return None

    # Se existir resultado de API, começa por ele:
    # é estruturado e por isso tem prioridade.
    api = next(
        (
            resultado
            for resultado
            in validos
            if "API" in str(
                resultado.get(
                    "origem"
                )
                or ""
            )
        ),
        None,
    )

    web = next(
        (
            resultado
            for resultado
            in validos
            if resultado.get(
                "origem"
            )
            == "Pesquisa Web"
        ),
        None,
    )

    base = dict(
        api
        or web
        or validos[0]
    )

    if web:
        if not base.get(
            "titulo"
        ):
            base["titulo"] = (
                web.get(
                    "titulo"
                )
            )

        if not base.get(
            "autores"
        ):
            base["autores"] = (
                web.get(
                    "autores"
                )
            )

        if not base.get(
            "editora"
        ):
            base["editora"] = (
                web.get(
                    "editora"
                )
            )

        if not base.get(
            "data_publicacao"
        ):
            base[
                "data_publicacao"
            ] = web.get(
                "data_publicacao"
            )

        if not base.get(
            "generos"
        ):
            base["generos"] = (
                web.get(
                    "generos"
                )
            )

    titulo = (
        _limpar_titulo_livro(
            base.get(
                "titulo"
            )
        )
    )

    autores = (
        _limpar_autores_validos(
            base.get(
                "autores"
            )
            or []
        )
    )

    editora = (
        _limpar_editora(
            base.get(
                "editora"
            )
        )
    )

    data_publicacao = (
        _normalizar_data_catalogo(
            base.get(
                "data_publicacao"
            )
        )
        if base.get(
            "data_publicacao"
        )
        else None
    )

    generos = []

    for genero in (
        base.get(
            "generos"
        )
        or []
    ):
        for nome in (
            _generos_da_classificacao(
                genero
            )
            or []
        ):
            if nome not in generos:
                generos.append(
                    nome
                )

    if _titulo_invalido(
        titulo
    ):
        return None

    origens = []

    for resultado in validos:
        origem = resultado.get(
            "origem"
        )

        if (
            origem
            and origem
            not in origens
        ):
            origens.append(
                origem
            )

    return {
        "sucesso": True,
        "origem": (
            " + ".join(
                origens
            )
            if origens
            else "Fonte externa"
        ),
        "titulo": titulo,
        "isbn": isbn_limpo,
        "autores": autores,
        "editora": editora,
        "data_publicacao": (
            data_publicacao
        ),
        "generos": generos[:3],
    }


def _resultado_precisa_enriquecimento(
    resultado,
):
    if not resultado:
        return True

    return any(
        [
            not resultado.get(
                "autores"
            ),
            not resultado.get(
                "editora"
            ),
            not resultado.get(
                "data_publicacao"
            ),
            not resultado.get(
                "generos"
            ),
        ]
    )


def _consultar_apis_em_paralelo(
    isbn_limpo,
):
    tarefas = {
        "Google Books": (
            procurar_livro_google_books
        ),
        "Open Library": (
            procurar_livro_open_library
        ),
    }

    resultados = {}

    with ThreadPoolExecutor(
        max_workers=2
    ) as executor:
        futuros = {
            executor.submit(
                funcao,
                isbn_limpo,
            ): nome
            for nome, funcao
            in tarefas.items()
        }

        for futuro in as_completed(
            futuros
        ):
            nome = futuros[
                futuro
            ]

            try:
                resultado = (
                    futuro.result()
                )
            except Exception as erro:
                print(
                    f"[BookCatalog] "
                    f"{nome}: erro: "
                    f"{erro}"
                )
                resultado = {
                    "sucesso": False
                }

            resultados[
                nome
            ] = resultado

            print(
                f"[BookCatalog] {nome}: "
                f"{'encontrado' if resultado.get('sucesso') else 'não encontrado'}."
            )

    # Dá prioridade aos dados da Google Books,
    # mas aproveita campos em falta da Open Library.
    ordem = [
        resultados.get(
            "Google Books"
        ),
        resultados.get(
            "Open Library"
        ),
    ]

    return _mesclar_resultados_livro(
        ordem,
        isbn_limpo,
    )


def _procurar_externo_cacheado(
    isbn_limpo,
):
    resultado_api = (
        _consultar_apis_em_paralelo(
            isbn_limpo
        )
    )

    if (
        resultado_api
        and not _resultado_precisa_enriquecimento(
            resultado_api
        )
    ):
        return resultado_api

    if resultado_api:
        print(
            "[BookCatalog] APIs encontraram o livro, "
            "mas faltam metadados. "
            "A iniciar pesquisa Web geral..."
        )
    else:
        print(
            "[BookCatalog] APIs sem resultado. "
            "A iniciar pesquisa Web geral..."
        )

    resultado_web = (
        procurar_livro_pesquisa_web(
            isbn_limpo
        )
    )

    print(
        "[BookCatalog] Pesquisa Web: "
        f"{'encontrado' if resultado_web.get('sucesso') else 'não encontrado'}."
    )

    if resultado_web.get(
        "sucesso"
    ):
        resultado_completo = (
            _mesclar_resultados_livro(
                [
                    resultado_api,
                    resultado_web,
                ],
                isbn_limpo,
            )
        )

        if resultado_completo:
            return resultado_completo

    if resultado_api:
        return resultado_api

    return {
        "sucesso": False,
        "erro": (
            "ISBN não encontrado na Google Books, "
            "Open Library nem na pesquisa Web geral."
        ),
    }


def procurar_livro(isbn):
    """
    Pesquisa usada pelo SABIN.

    Ordem:
      1. Base de dados local da Bookmarked;
      2. Google Books + Open Library em paralelo;
      3. Pesquisa Web geral por metapesquisa DDGS, sem lista fixa de sites;
      4. Só são aceites páginas que contenham o ISBN exato e metadados bibliográficos;
      5. Páginas bloqueadas ou resultados inválidos são ignorados.
    """
    isbn_limpo = normalizar_isbn(isbn)

    if not _isbn_valido(isbn_limpo):
        return {
            "sucesso": False,
            "erro": "O ISBN indicado não é válido.",
        }

    print(f"[BookCatalog] A procurar ISBN {isbn_limpo}...")

    local = procurar_livro_local(isbn_limpo)

    if local:
        print("[BookCatalog] Base local: encontrado.")
        return local

    print(
        "[BookCatalog] Base local: não encontrado. "
        "A consultar fontes externas..."
    )

    resultado = _procurar_externo_cacheado(isbn_limpo)

    # Cópia defensiva: a cache não deve ser alterada pelo app.
    copia = dict(resultado)

    for campo in ("autores", "generos"):
        if isinstance(copia.get(campo), list):
            copia[campo] = list(copia[campo])

    return copia
