import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation

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


def carregar_livros_gestao():
    query = text("""
        SELECT
            id,
            titulo,
            isbn,
            preco_venda,
            estoque_atual,
            qtd_reservada,
            GREATEST(
                estoque_atual - qtd_reservada,
                0
            ) AS stock_disponivel,
            editora,
            data_publicacao
        FROM public.livros
        ORDER BY titulo;
    """)

    with engine.connect() as connection:
        resultados = (
            connection.execute(query)
            .mappings()
            .all()
        )

    livros = []

    for resultado in resultados:
        livros.append(
            {
                "id": int(resultado["id"]),
                "titulo": resultado["titulo"],
                "isbn": resultado["isbn"],
                "preco_venda": float(
                    resultado["preco_venda"]
                ),
                "estoque_atual": int(
                    resultado["estoque_atual"]
                ),
                "qtd_reservada": int(
                    resultado["qtd_reservada"]
                ),
                "stock_disponivel": int(
                    resultado["stock_disponivel"]
                ),
                "editora": resultado["editora"],
                "data_publicacao": (
                    resultado["data_publicacao"].isoformat()
                    if resultado["data_publicacao"]
                    else None
                ),
            }
        )

    return livros


def carregar_autores_gestao():
    query = text("""
        SELECT
            id,
            nome
        FROM public.autores
        ORDER BY nome;
    """)

    with engine.connect() as connection:
        resultados = (
            connection.execute(query)
            .mappings()
            .all()
        )

    return [
        {
            "id": int(resultado["id"]),
            "nome": resultado["nome"],
        }
        for resultado in resultados
    ]


def carregar_generos_gestao():
    query = text("""
        SELECT
            id,
            nome
        FROM public.generos
        ORDER BY nome;
    """)

    with engine.connect() as connection:
        resultados = (
            connection.execute(query)
            .mappings()
            .all()
        )

    return [
        {
            "id": int(resultado["id"]),
            "nome": resultado["nome"],
        }
        for resultado in resultados
    ]


def obter_livro_gestao(livro_id):
    if not livro_id:
        return None

    query = text("""
        SELECT
            id,
            titulo,
            isbn,
            preco_venda,
            estoque_atual,
            qtd_reservada,
            GREATEST(
                estoque_atual - qtd_reservada,
                0
            ) AS stock_disponivel,
            editora,
            data_publicacao
        FROM public.livros
        WHERE id = :livro_id;
    """)

    with engine.connect() as connection:
        resultado = (
            connection.execute(
                query,
                {
                    "livro_id": int(livro_id),
                },
            )
            .mappings()
            .first()
        )

    if not resultado:
        return None

    return {
        "id": int(resultado["id"]),
        "titulo": resultado["titulo"],
        "isbn": resultado["isbn"],
        "preco_venda": float(
            resultado["preco_venda"]
        ),
        "estoque_atual": int(
            resultado["estoque_atual"]
        ),
        "qtd_reservada": int(
            resultado["qtd_reservada"]
        ),
        "stock_disponivel": int(
            resultado["stock_disponivel"]
        ),
        "editora": resultado["editora"],
        "data_publicacao": (
            resultado["data_publicacao"].isoformat()
            if resultado["data_publicacao"]
            else None
        ),
    }


def repor_stock(
    livro_id,
    quantidade,
    observacao=None,
):
    if not livro_id:
        raise ValueError(
            "Seleciona um livro."
        )

    try:
        quantidade = int(quantidade)
    except (TypeError, ValueError):
        raise ValueError(
            "A quantidade deve ser um número inteiro."
        )

    if quantidade <= 0:
        raise ValueError(
            "A quantidade a repor deve ser superior a zero."
        )

    with engine.begin() as connection:
        livro = (
            connection.execute(
                text("""
                    SELECT
                        id,
                        titulo,
                        estoque_atual
                    FROM public.livros
                    WHERE id = :livro_id
                    FOR UPDATE;
                """),
                {
                    "livro_id": int(livro_id),
                },
            )
            .mappings()
            .first()
        )

        if not livro:
            raise ValueError(
                "Livro não encontrado."
            )

        stock_anterior = int(
            livro["estoque_atual"]
        )

        stock_novo = (
            stock_anterior
            + quantidade
        )

        connection.execute(
            text("""
                UPDATE public.livros
                SET
                    estoque_atual = :stock_novo,
                    atualizado_em = now()
                WHERE id = :livro_id;
            """),
            {
                "stock_novo": stock_novo,
                "livro_id": int(livro_id),
            },
        )

        connection.execute(
            text("""
                INSERT INTO public.movimentos_stock (
                    livro_id,
                    tipo,
                    quantidade,
                    stock_anterior,
                    stock_novo,
                    origem,
                    referencia_id,
                    observacao
                )
                VALUES (
                    :livro_id,
                    'Entrada',
                    :quantidade,
                    :stock_anterior,
                    :stock_novo,
                    'Reposição',
                    NULL,
                    :observacao
                );
            """),
            {
                "livro_id": int(livro_id),
                "quantidade": quantidade,
                "stock_anterior": stock_anterior,
                "stock_novo": stock_novo,
                "observacao": (
                    observacao.strip()
                    if observacao and observacao.strip()
                    else "Reposição de stock."
                ),
            },
        )

    return {
        "sucesso": True,
        "livro_id": int(livro_id),
        "titulo": livro["titulo"],
        "quantidade_adicionada": quantidade,
        "stock_anterior": stock_anterior,
        "stock_novo": stock_novo,
    }


def alterar_preco(
    livro_id,
    novo_preco,
):
    if not livro_id:
        raise ValueError(
            "Seleciona um livro."
        )

    try:
        novo_preco = Decimal(
            str(novo_preco)
        ).quantize(
            Decimal("0.01")
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "Indica um preço válido."
        )

    if novo_preco <= 0:
        raise ValueError(
            "O novo preço deve ser superior a zero."
        )

    with engine.begin() as connection:
        livro = (
            connection.execute(
                text("""
                    SELECT
                        id,
                        titulo,
                        preco_venda
                    FROM public.livros
                    WHERE id = :livro_id
                    FOR UPDATE;
                """),
                {
                    "livro_id": int(livro_id),
                },
            )
            .mappings()
            .first()
        )

        if not livro:
            raise ValueError(
                "Livro não encontrado."
            )

        preco_anterior = Decimal(
            str(livro["preco_venda"])
        ).quantize(
            Decimal("0.01")
        )

        if novo_preco == preco_anterior:
            raise ValueError(
                "O novo preço é igual ao preço atual."
            )

        connection.execute(
            text("""
                UPDATE public.livros
                SET
                    preco_venda = :novo_preco,
                    atualizado_em = now()
                WHERE id = :livro_id;
            """),
            {
                "novo_preco": novo_preco,
                "livro_id": int(livro_id),
            },
        )

    return {
        "sucesso": True,
        "livro_id": int(livro_id),
        "titulo": livro["titulo"],
        "preco_anterior": float(
            preco_anterior
        ),
        "preco_novo": float(
            novo_preco
        ),
    }


def normalizar_nomes_autores(autores_texto):
    if not autores_texto:
        return []

    if isinstance(autores_texto, (list, tuple)):
        valores = autores_texto
    else:
        valores = re.split(
            r"[;,\n]+",
            str(autores_texto),
        )

    nomes = []

    for valor in valores:
        nome = str(valor or "").strip()

        if nome and nome.lower() not in {
            existente.lower()
            for existente in nomes
        }:
            nomes.append(nome)

    return nomes


def obter_ou_criar_autor(
    connection,
    nome,
):
    existente = (
        connection.execute(
            text("""
                SELECT id
                FROM public.autores
                WHERE LOWER(TRIM(nome)) = LOWER(TRIM(:nome))
                ORDER BY id
                LIMIT 1;
            """),
            {
                "nome": nome,
            },
        )
        .mappings()
        .first()
    )

    if existente:
        return int(existente["id"])

    novo = (
        connection.execute(
            text("""
                INSERT INTO public.autores (
                    nome
                )
                VALUES (
                    :nome
                )
                RETURNING id;
            """),
            {
                "nome": nome,
            },
        )
        .mappings()
        .one()
    )

    return int(novo["id"])


def adicionar_livro(
    titulo,
    isbn,
    preco_venda,
    estoque_inicial=0,
    editora=None,
    data_publicacao=None,
    autores_texto=None,
    genero_ids=None,
):
    titulo = (titulo or "").strip()
    isbn = re.sub(
        r"[^0-9Xx]",
        "",
        str(isbn or ""),
    ).upper()
    editora = (
        editora.strip()
        if editora and editora.strip()
        else None
    )
    autores = normalizar_nomes_autores(
        autores_texto
    )
    genero_ids = genero_ids or []

    if not titulo:
        raise ValueError(
            "Indica o título do livro."
        )

    if len(isbn) not in (10, 13):
        raise ValueError(
            "O ISBN deve ter 10 ou 13 caracteres válidos."
        )

    try:
        preco_venda = Decimal(
            str(preco_venda)
        ).quantize(
            Decimal("0.01")
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "Indica um preço válido."
        )

    if preco_venda <= 0:
        raise ValueError(
            "O preço deve ser superior a zero."
        )

    try:
        estoque_inicial = int(
            estoque_inicial or 0
        )
    except (TypeError, ValueError):
        raise ValueError(
            "O stock inicial deve ser um número inteiro."
        )

    if estoque_inicial < 0:
        raise ValueError(
            "O stock inicial não pode ser negativo."
        )

    data_final = None

    if data_publicacao:
        try:
            data_final = date.fromisoformat(
                str(data_publicacao)
            )
        except ValueError:
            raise ValueError(
                "A data de publicação não é válida."
            )

    with engine.begin() as connection:
        existe = connection.execute(
            text("""
                SELECT id
                FROM public.livros
                WHERE REGEXP_REPLACE(
                    UPPER(isbn),
                    '[^0-9X]',
                    '',
                    'g'
                ) = :isbn;
            """),
            {
                "isbn": isbn,
            },
        ).first()

        if existe:
            raise ValueError(
                "Já existe um livro com este ISBN."
            )

        livro = (
            connection.execute(
                text("""
                    INSERT INTO public.livros (
                        titulo,
                        isbn,
                        preco_venda,
                        estoque_atual,
                        total_vendas_acumuladas,
                        qtd_reservada,
                        data_publicacao,
                        editora
                    )
                    VALUES (
                        :titulo,
                        :isbn,
                        :preco_venda,
                        :estoque_inicial,
                        0,
                        0,
                        :data_publicacao,
                        :editora
                    )
                    RETURNING id, titulo;
                """),
                {
                    "titulo": titulo,
                    "isbn": isbn,
                    "preco_venda": preco_venda,
                    "estoque_inicial": estoque_inicial,
                    "data_publicacao": data_final,
                    "editora": editora,
                },
            )
            .mappings()
            .one()
        )

        livro_id = int(
            livro["id"]
        )

        for nome_autor in autores:
            autor_id = obter_ou_criar_autor(
                connection,
                nome_autor,
            )

            connection.execute(
                text("""
                    INSERT INTO public.livro_autores (
                        livro_id,
                        autor_id
                    )
                    VALUES (
                        :livro_id,
                        :autor_id
                    )
                    ON CONFLICT DO NOTHING;
                """),
                {
                    "livro_id": livro_id,
                    "autor_id": autor_id,
                },
            )

        for genero_id in genero_ids:
            connection.execute(
                text("""
                    INSERT INTO public.livro_generos (
                        livro_id,
                        genero_id
                    )
                    VALUES (
                        :livro_id,
                        :genero_id
                    )
                    ON CONFLICT DO NOTHING;
                """),
                {
                    "livro_id": livro_id,
                    "genero_id": int(genero_id),
                },
            )

        if estoque_inicial > 0:
            connection.execute(
                text("""
                    INSERT INTO public.movimentos_stock (
                        livro_id,
                        tipo,
                        quantidade,
                        stock_anterior,
                        stock_novo,
                        origem,
                        referencia_id,
                        observacao
                    )
                    VALUES (
                        :livro_id,
                        'Entrada',
                        :quantidade,
                        0,
                        :stock_novo,
                        'Stock inicial',
                        NULL,
                        'Stock definido no registo inicial do livro.'
                    );
                """),
                {
                    "livro_id": livro_id,
                    "quantidade": estoque_inicial,
                    "stock_novo": estoque_inicial,
                },
            )

    return {
        "sucesso": True,
        "livro_id": livro_id,
        "titulo": livro["titulo"],
    }

def consultar_movimentos_stock(
    livro_id=None,
    limite=20,
):
    limite = max(
        1,
        min(
            int(limite),
            100,
        ),
    )

    if livro_id:
        query = text("""
            SELECT
                ms.id,
                ms.livro_id,
                l.titulo,
                ms.tipo,
                ms.quantidade,
                ms.stock_anterior,
                ms.stock_novo,
                ms.origem,
                ms.referencia_id,
                ms.data_movimento,
                ms.observacao
            FROM public.movimentos_stock ms
            JOIN public.livros l
                ON l.id = ms.livro_id
            WHERE ms.livro_id = :livro_id
            ORDER BY ms.data_movimento DESC
            LIMIT :limite;
        """)

        parametros = {
            "livro_id": int(livro_id),
            "limite": limite,
        }
    else:
        query = text("""
            SELECT
                ms.id,
                ms.livro_id,
                l.titulo,
                ms.tipo,
                ms.quantidade,
                ms.stock_anterior,
                ms.stock_novo,
                ms.origem,
                ms.referencia_id,
                ms.data_movimento,
                ms.observacao
            FROM public.movimentos_stock ms
            JOIN public.livros l
                ON l.id = ms.livro_id
            ORDER BY ms.data_movimento DESC
            LIMIT :limite;
        """)

        parametros = {
            "limite": limite,
        }

    with engine.connect() as connection:
        resultados = (
            connection.execute(
                query,
                parametros,
            )
            .mappings()
            .all()
        )

    return [
        dict(resultado)
        for resultado in resultados
    ]


def consultar_historico_precos(
    livro_id=None,
    limite=20,
):
    limite = max(
        1,
        min(
            int(limite),
            100,
        ),
    )

    if livro_id:
        query = text("""
            SELECT
                hp.id,
                hp.livro_id,
                l.titulo,
                hp.preco_anterior,
                hp.preco_novo,
                hp.data_alteracao,
                hp.observacao
            FROM public.historico_precos hp
            JOIN public.livros l
                ON l.id = hp.livro_id
            WHERE hp.livro_id = :livro_id
            ORDER BY hp.data_alteracao DESC
            LIMIT :limite;
        """)

        parametros = {
            "livro_id": int(livro_id),
            "limite": limite,
        }
    else:
        query = text("""
            SELECT
                hp.id,
                hp.livro_id,
                l.titulo,
                hp.preco_anterior,
                hp.preco_novo,
                hp.data_alteracao,
                hp.observacao
            FROM public.historico_precos hp
            JOIN public.livros l
                ON l.id = hp.livro_id
            ORDER BY hp.data_alteracao DESC
            LIMIT :limite;
        """)

        parametros = {
            "limite": limite,
        }

    with engine.connect() as connection:
        resultados = (
            connection.execute(
                query,
                parametros,
            )
            .mappings()
            .all()
        )

    return [
        dict(resultado)
        for resultado in resultados
    ]


if __name__ == "__main__":
    livros = carregar_livros_gestao()

    print(
        f"Livros encontrados: {len(livros)}"
    )

    if livros:
        print(
            livros[0]
        )
