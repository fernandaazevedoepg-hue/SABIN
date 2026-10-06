import os
import re
import json
import unicodedata
from functools import lru_cache
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

HTTP_TIMEOUT_CURTO = 12
HTTP_TIMEOUT_READER = 9

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


def _obter_html(url, timeout=HTTP_TIMEOUT_CURTO):
    resposta = HTTP_SESSION.get(
        url,
        timeout=timeout,
        allow_redirects=True,
    )
    resposta.raise_for_status()

    if not resposta.encoding:
        resposta.encoding = (
            resposta.apparent_encoding
            or "utf-8"
        )

    return resposta.text, resposta.url


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


def _normalizar_texto(valor):
    texto = _sem_acentos(valor).lower()
    texto = re.sub(r"\s+", " ", texto)
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
                valor = encontrado.group(1).strip(" \t\n|:-")
                valor = re.sub(r"\s+", " ", valor)

                if valor and valor not in {"-", "—"}:
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
        nome = str(autor or "").strip()
        chave = _normalizar_texto(nome)

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
            vistos.add(chave)
            resultado.append(nome)

    return resultado


def _pontuar_metadados(dados):
    if not dados:
        return -100

    if _titulo_invalido(dados.get("titulo")):
        return -100

    pontos = 5

    if dados.get("autores"):
        pontos += 4
    if dados.get("editora"):
        pontos += 2
    if dados.get("data_publicacao"):
        pontos += 2
    if dados.get("generos"):
        pontos += 1

    return pontos


def _resultado_web_valido(dados):
    if not dados:
        return False

    if _titulo_invalido(dados.get("titulo")):
        return False

    # Um título sozinho não chega. Exigimos pelo menos autor ou editora,
    # evitando tratar uma página Cloudflare/pesquisa como livro real.
    if not dados.get("autores") and not dados.get("editora"):
        return False

    return _pontuar_metadados(dados) >= 9


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

    return dados if _resultado_web_valido(dados) else None


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

        if _resultado_web_valido(dados_json):
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

    return dados if _resultado_web_valido(dados) else None


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

    consultas = [
        f'"{isbn_limpo}"',
        f'"{isbn_limpo}" livro',
        f'"{isbn_limpo}" ISBN',
        f'"{isbn_limpo}" book',
    ]

    links = []
    vistos = set()

    try:
        pesquisador = DDGS(
            timeout=12
        )
    except Exception as erro:
        print(
            "[BookCatalog] Não foi possível iniciar DDGS:",
            erro,
        )
        return []

    for consulta in consultas:
        try:
            resultados = pesquisador.text(
                consulta,
                region="pt-pt",
                safesearch="moderate",
                max_results=20,
                backend="auto",
            ) or []
        except Exception as erro:
            print(
                f"[BookCatalog] DDGS falhou para {consulta!r}:",
                erro,
            )
            resultados = []

        print(
            f"[BookCatalog] DDGS {consulta!r}: "
            f"{len(resultados)} resultado(s)."
        )

        for resultado in resultados:
            if not _resultado_ddgs_valido(
                resultado
            ):
                continue

            href = str(
                resultado.get("href")
                or resultado.get("url")
                or ""
            ).strip()

            if href in vistos:
                continue

            vistos.add(
                href
            )
            links.append(
                href
            )

        if len(links) >= 25:
            break

    return links[:30]


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


# Leitura e pesquisa web


def _ler_candidato_web(url, isbn):
    isbn_limpo = normalizar_isbn(
        isbn
    )

    print(
        f"[BookCatalog] A testar página: {url}"
    )

    # 1) Tenta ler o HTML diretamente.
    try:
        html, url_final = _obter_html(
            url,
            timeout=12,
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
                print(
                    "[BookCatalog] Ficha válida encontrada "
                    f"por HTML: {url_final}"
                )
                return dados

    except Exception as erro:
        print(
            "[BookCatalog] HTML direto falhou:",
            erro,
        )

    # 2) Usa o extrator do DDGS. Isto costuma funcionar em páginas
    # onde a leitura HTTP direta é bloqueada ou demasiado dinâmica.
    try:
        extraido = DDGS(
            timeout=12
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
                print(
                    "[BookCatalog] Ficha válida encontrada "
                    f"pelo DDGS Extract: {url}"
                )
                return dados

    except Exception as erro:
        print(
            "[BookCatalog] DDGS Extract falhou:",
            erro,
        )

    # 3) Último fallback: Jina Reader.
    try:
        markdown = _obter_texto_reader(
            url
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
                print(
                    "[BookCatalog] Ficha válida encontrada "
                    f"pelo Reader: {url}"
                )
                return dados

    except Exception as erro:
        print(
            "[BookCatalog] Reader falhou:",
            erro,
        )

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

    links = _descobrir_links_produto(
        isbn_limpo
    )

    print(
        f"[BookCatalog] Pesquisa Web geral encontrou "
        f"{len(links)} link(s) candidato(s)."
    )

    if not links:
        return {
            "sucesso": False,
            "erro": (
                "Nenhuma página candidata foi encontrada "
                "na pesquisa Web geral."
            ),
        }

    # Lê vários resultados em paralelo. Uma página só é aceite
    # se o conteúdo contiver exatamente o ISBN pesquisado.
    candidatos = links[:12]
    resultados = []

    with ThreadPoolExecutor(
        max_workers=min(
            6,
            len(candidatos),
        )
    ) as executor:
        futuros = {
            executor.submit(
                _ler_candidato_web,
                link,
                isbn_limpo,
            ): link
            for link in candidatos
        }

        for futuro in as_completed(
            futuros
        ):
            link = futuros[
                futuro
            ]

            try:
                dados = futuro.result()
            except Exception as erro:
                print(
                    f"[BookCatalog] "
                    f"Erro ao ler {link}: "
                    f"{erro}"
                )
                dados = None

            if dados:
                resultados.append(
                    dados
                )

    if not resultados:
        return {
            "sucesso": False,
            "erro": (
                "As páginas encontradas não continham "
                "uma ficha bibliográfica válida com o ISBN exato."
            ),
        }

    resultados.sort(
        key=_pontuar_metadados,
        reverse=True,
    )

    melhor = resultados[0]

    # Se houver várias páginas válidas, completa campos em falta
    # usando as restantes, sem misturar dados quando já existem.
    autores = list(
        melhor.get(
            "autores"
        )
        or []
    )
    generos = list(
        melhor.get(
            "generos"
        )
        or []
    )

    autores_normalizados = {
        _normalizar_texto(
            autor
        )
        for autor in autores
    }

    generos_normalizados = {
        _normalizar_texto(
            genero
        )
        for genero in generos
    }

    for resultado in resultados[1:]:
        if not melhor.get(
            "editora"
        ):
            melhor[
                "editora"
            ] = resultado.get(
                "editora"
            )

        if not melhor.get(
            "data_publicacao"
        ):
            melhor[
                "data_publicacao"
            ] = resultado.get(
                "data_publicacao"
            )

        for autor in (
            resultado.get(
                "autores"
            )
            or []
        ):
            chave = (
                _normalizar_texto(
                    autor
                )
            )

            if (
                chave
                and chave
                not in autores_normalizados
            ):
                autores.append(
                    autor
                )
                autores_normalizados.add(
                    chave
                )

        for genero in (
            resultado.get(
                "generos"
            )
            or []
        ):
            chave = (
                _normalizar_texto(
                    genero
                )
            )

            if (
                chave
                and chave
                not in generos_normalizados
            ):
                generos.append(
                    genero
                )
                generos_normalizados.add(
                    chave
                )

    melhor[
        "autores"
    ] = autores

    melhor[
        "generos"
    ] = generos

    print(
        "[BookCatalog] Melhor ficha Web geral: "
        f"{melhor.get('url_origem')} | "
        f"título={melhor.get('titulo')!r} | "
        f"autor={melhor.get('autores')!r} | "
        f"pontuação={_pontuar_metadados(melhor)}"
    )

    return melhor


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
        texto_item = str(
            item or ""
        ).strip()

        if not texto_item:
            continue

        chave = _normalizar_texto(
            texto_item
        )

        if chave in vistos:
            continue

        vistos.add(chave)
        resultado.append(
            texto_item
        )

    return resultado


def _mesclar_resultados_livro(
    resultados,
    isbn_limpo,
):
    validos = [
        resultado
        for resultado in resultados
        if (
            resultado
            and resultado.get(
                "sucesso"
            )
        )
    ]

    if not validos:
        return None

    titulo = None
    editora = None
    data_publicacao = None
    autores = []
    generos = []
    origens = []

    for resultado in validos:
        origem = resultado.get(
            "origem"
        )

        if (
            origem
            and origem not in origens
        ):
            origens.append(
                origem
            )

        titulo_resultado = (
            resultado.get(
                "titulo"
            )
        )

        if (
            not titulo
            and not _titulo_invalido(
                titulo_resultado
            )
        ):
            titulo = str(
                titulo_resultado
            ).strip()

        if not editora:
            valor_editora = (
                resultado.get(
                    "editora"
                )
            )

            if valor_editora:
                editora = str(
                    valor_editora
                ).strip()

        if not data_publicacao:
            valor_data = (
                resultado.get(
                    "data_publicacao"
                )
            )

            if valor_data:
                data_publicacao = str(
                    valor_data
                ).strip()

        autores_existentes = {
            _normalizar_texto(
                autor
            )
            for autor in autores
        }

        for autor in (
            _normalizar_lista_metadados(
                resultado.get(
                    "autores"
                )
            )
        ):
            chave = _normalizar_texto(
                autor
            )

            if chave not in autores_existentes:
                autores.append(
                    autor
                )
                autores_existentes.add(
                    chave
                )

        generos_existentes = {
            _normalizar_texto(
                genero
            )
            for genero in generos
        }

        for genero in (
            _normalizar_lista_metadados(
                resultado.get(
                    "generos"
                )
            )
        ):
            chave = _normalizar_texto(
                genero
            )

            if chave not in generos_existentes:
                generos.append(
                    genero
                )
                generos_existentes.add(
                    chave
                )

    if _titulo_invalido(titulo):
        return None

    return {
        "sucesso": True,
        "origem": (
            " + ".join(origens)
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
        "generos": generos,
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
