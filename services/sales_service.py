import os

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
    pool_pre_ping=True
)


METODOS_PAGAMENTO = [
    "Dinheiro",
    "Multibanco",
    "MBWay",
    "Cartão de Crédito",
    "Cartão de Débito",
    "Transferência",
]


def carregar_clientes():
    query = text("""
        SELECT
            id,
            nome_completo,
            nif

        FROM public.clientes

        ORDER BY
            nome_completo;
    """)

    with engine.connect() as connection:
        resultados = connection.execute(
            query
        ).mappings().all()

    return [
        dict(resultado)
        for resultado in resultados
    ]


def carregar_livros_disponiveis():
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
            ) AS stock_disponivel

        FROM public.livros

        WHERE
            GREATEST(
                estoque_atual - qtd_reservada,
                0
            ) > 0

        ORDER BY
            titulo;
    """)

    with engine.connect() as connection:
        resultados = connection.execute(
            query
        ).mappings().all()

    return [
        dict(resultado)
        for resultado in resultados
    ]


def obter_livro(livro_id):
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
            ) AS stock_disponivel

        FROM public.livros

        WHERE id = :livro_id;
    """)

    with engine.connect() as connection:
        resultado = connection.execute(
            query,
            {
                "livro_id": livro_id
            }
        ).mappings().first()

    if not resultado:
        return None

    return dict(resultado)


def registar_venda(
    cliente_id,
    metodo_pagamento,
    itens
):
    if metodo_pagamento not in METODOS_PAGAMENTO:
        raise ValueError(
            "Método de pagamento inválido."
        )

    if not itens:
        raise ValueError(
            "A venda precisa de pelo menos um livro."
        )

    itens_agrupados = {}

    for item in itens:
        livro_id = int(
            item["livro_id"]
        )

        quantidade = int(
            item["quantidade"]
        )

        if quantidade <= 0:
            raise ValueError(
                "A quantidade deve ser superior a zero."
            )

        if livro_id not in itens_agrupados:
            itens_agrupados[
                livro_id
            ] = 0

        itens_agrupados[
            livro_id
        ] += quantidade

    with engine.begin() as connection:
        itens_validados = []
        total_venda = 0

        for livro_id in sorted(
            itens_agrupados.keys()
        ):
            quantidade = (
                itens_agrupados[
                    livro_id
                ]
            )

            query_livro = text("""
                SELECT
                    id,
                    titulo,
                    preco_venda,
                    estoque_atual,
                    qtd_reservada,

                    GREATEST(
                        estoque_atual - qtd_reservada,
                        0
                    ) AS stock_disponivel

                FROM public.livros

                WHERE id = :livro_id

                FOR UPDATE;
            """)

            livro = connection.execute(
                query_livro,
                {
                    "livro_id": livro_id
                }
            ).mappings().first()

            if not livro:
                raise ValueError(
                    f"Livro {livro_id} não encontrado."
                )

            stock_disponivel = int(
                livro["stock_disponivel"]
            )

            if quantidade > stock_disponivel:
                raise ValueError(
                    f"Stock insuficiente para "
                    f"'{livro['titulo']}'. "
                    f"Disponível: {stock_disponivel}."
                )

            preco = float(
                livro["preco_venda"]
            )

            subtotal = (
                preco
                * quantidade
            )

            total_venda += subtotal

            itens_validados.append(
                {
                    "livro_id": livro_id,
                    "titulo": livro["titulo"],
                    "quantidade": quantidade,
                    "preco": preco,
                    "subtotal": subtotal,
                }
            )

        query_venda = text("""
            INSERT INTO public.vendas (
                cliente_id,
                valor_total,
                metodo_pagamento,
                status
            )
            VALUES (
                :cliente_id,
                0,
                :metodo_pagamento,
                'Concluída'
            )
            RETURNING id;
        """)

        venda_id = connection.execute(
            query_venda,
            {
                "cliente_id": cliente_id,
                "metodo_pagamento": metodo_pagamento,
            }
        ).scalar_one()

        query_item = text("""
            INSERT INTO public.itens_venda (
                venda_id,
                livro_id,
                quantidade,
                preco_unitario
            )
            VALUES (
                :venda_id,
                :livro_id,
                :quantidade,
                :preco_unitario
            );
        """)

        for item in itens_validados:
            connection.execute(
                query_item,
                {
                    "venda_id": venda_id,
                    "livro_id": item["livro_id"],
                    "quantidade": item["quantidade"],
                    "preco_unitario": item["preco"],
                }
            )

        query_total = text("""
            UPDATE public.vendas

            SET valor_total = :total

            WHERE id = :venda_id;
        """)

        connection.execute(
            query_total,
            {
                "total": total_venda,
                "venda_id": venda_id,
            }
        )

    return {
        "sucesso": True,
        "venda_id": venda_id,
        "total": total_venda,
        "itens": itens_validados,
    }


if __name__ == "__main__":
    clientes = carregar_clientes()

    livros = carregar_livros_disponiveis()

    print()
    print("SABIN - TESTE DO SERVIÇO DE VENDAS")
    print()

    print(
        f"Clientes encontrados: {len(clientes)}"
    )

    print(
        f"Livros disponíveis: {len(livros)}"
    )

    print()
    print("Primeiros livros:")
    print()

    for livro in livros[:5]:
        print(
            f"- {livro['titulo']} | "
            f"{livro['preco_venda']} € | "
            f"Disponível: "
            f"{livro['stock_disponivel']}"
        )