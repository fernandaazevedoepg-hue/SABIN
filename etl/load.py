import pandas as pd
from sqlalchemy import text

from extract import DW_SCHEMA, engine, extrair_tabela

from transform import (
    transformar_dim_cliente,
    transformar_dim_livro,
    transformar_dim_pagamento,
    transformar_dim_data,
    transformar_dim_autor,
    transformar_dim_genero,
    transformar_fact_vendas,
)


# Níveis de stock usados pela fact_stock (dimensão fixa do modelo).
NIVEIS_STOCK = [
    ("Crítico", "Repor stock com prioridade", 1),
    ("Atenção", "Planear reposição", 2),
    ("Normal", "Stock suficiente", 3),
    ("Sem procura recente", "Sem procura recente", 4),
]


def limpar_data_warehouse(conn):
    """Limpa as tabelas recarregadas em cada execução do ETL.

    A dim_data, as dimensões de apoio e os factos de previsão e alertas
    não são limpos: o calendário é fixo e a previsão e os alertas são
    atualizados pelos respetivos scripts. Sem CASCADE, para que a base de
    dados recuse a operação se alguma outra tabela depender destas.
    """
    query = f"""
    TRUNCATE TABLE
        {DW_SCHEMA}.fact_vendas,
        {DW_SCHEMA}.fact_stock,
        {DW_SCHEMA}.dim_autor,
        {DW_SCHEMA}.dim_genero,
        {DW_SCHEMA}.dim_cliente,
        {DW_SCHEMA}.dim_livro,
        {DW_SCHEMA}.dim_pagamento
    RESTART IDENTITY;
    """

    conn.execute(text(query))


def carregar_dim_data(conn, dim_data):
    """Acrescenta ao calendário apenas os dias que ainda não existem."""
    existentes = pd.read_sql(
        text(f"SELECT data_key FROM {DW_SCHEMA}.dim_data;"),
        conn,
    )

    novos = dim_data[
        ~dim_data["data_key"].isin(existentes["data_key"])
    ]

    novos.to_sql(
        "dim_data",
        conn,
        schema=DW_SCHEMA,
        if_exists="append",
        index=False,
    )

    return len(novos)


def carregar_dim_nivel_stock(conn):
    """Garante que os níveis de stock existem (não altera os existentes)."""
    query = text(f"""
        INSERT INTO {DW_SCHEMA}.dim_nivel_stock (nivel, recomendacao, ordem)
        VALUES (:nivel, :recomendacao, :ordem)
        ON CONFLICT (nivel) DO NOTHING;
    """)

    for nivel, recomendacao, ordem in NIVEIS_STOCK:
        conn.execute(
            query,
            {
                "nivel": nivel,
                "recomendacao": recomendacao,
                "ordem": ordem,
            },
        )


def ler_historico_stock(conn):
    """Guarda as fotografias de stock antes de as chaves dos livros mudarem.

    A tabela fica bloqueada até ao fim da transação, para que uma
    atualização de stock feita ao mesmo tempo pela aplicação espere pela
    carga em vez de se perder.
    """
    conn.execute(text(
        f"LOCK TABLE {DW_SCHEMA}.fact_stock IN EXCLUSIVE MODE;"
    ))

    query = text(f"""
        SELECT
            l.livro_id_origem,
            f.data_key,
            f.nivel_key,
            f.estoque_atual,
            f.qtd_reservada,
            f.stock_disponivel,
            f.unidades_ultimos_3_meses,
            f.media_mensal_vendas,
            f.meses_cobertura,
            f.quantidade_recomendada,
            f.preco_venda
        FROM {DW_SCHEMA}.fact_stock f
        JOIN {DW_SCHEMA}.dim_livro l
            ON l.livro_key = f.livro_key;
    """)

    return pd.read_sql(query, conn)


def repor_historico_stock(conn, historico, dim_livro_dw):
    """Volta a gravar as fotografias de stock com as novas chaves dos livros."""
    if historico.empty:
        return 0, 0

    total_antes = len(historico)

    # Fotografias de livros que já não existem na base operacional são descartadas.
    historico = historico.merge(
        dim_livro_dw[
            [
                "livro_key",
                "livro_id_origem",
            ]
        ],
        on="livro_id_origem",
        how="inner",
        validate="many_to_one",
    )

    descartadas = total_antes - len(historico)

    historico = historico.drop(columns=["livro_id_origem"])

    historico.to_sql(
        "fact_stock",
        conn,
        schema=DW_SCHEMA,
        if_exists="append",
        index=False,
    )

    return len(historico), descartadas


def carregar_dimensao(conn, nome_tabela, dados):
    dados.to_sql(
        nome_tabela,
        conn,
        schema=DW_SCHEMA,
        if_exists="append",
        index=False,
    )


def carregar_dim_cliente(conn, dim_cliente):
    """Carrega os clientes e inclui o registo para vendas sem identificação."""
    cliente_desconhecido = pd.DataFrame(
        [
            {
                "cliente_id_origem": None,
                "nome_completo": "Cliente não identificado",
            }
        ]
    )

    dim_cliente = pd.concat(
        [cliente_desconhecido, dim_cliente],
        ignore_index=True,
    )

    carregar_dimensao(conn, "dim_cliente", dim_cliente)


def carregar_dim_autor(conn, dim_autor):
    """Carrega os autores, com o membro 0 para livros sem autor."""
    sem_autor = pd.DataFrame(
        [
            {
                "autor_key": 0,
                "autor_id_origem": 0,
                "nome": "Sem autor",
            }
        ]
    )

    carregar_dimensao(conn, "dim_autor", sem_autor)
    carregar_dimensao(conn, "dim_autor", dim_autor)


def carregar_dim_genero(conn, dim_genero):
    """Carrega os géneros, com o membro 0 para livros sem género."""
    sem_genero = pd.DataFrame(
        [
            {
                "genero_key": 0,
                "genero_id_origem": 0,
                "nome": "Sem género",
            }
        ]
    )

    carregar_dimensao(conn, "dim_genero", sem_genero)
    carregar_dimensao(conn, "dim_genero", dim_genero)


def ler_dimensao(conn, nome_tabela):
    """Lê uma dimensão carregada para obter as respetivas chaves."""
    query = text(f"SELECT * FROM {DW_SCHEMA}.{nome_tabela};")

    return pd.read_sql(query, conn)


def verificar_carga(conn, vendas_concluidas, itens_venda):
    """Compara o Data Warehouse com a base operacional.

    Se algum valor não coincidir, é lançada uma exceção e a transação é
    anulada: o Data Warehouse fica como estava antes da execução.
    """
    itens = itens_venda[
        itens_venda["venda_id"].isin(vendas_concluidas["id"])
    ]

    esperado = {
        "vendas": int(vendas_concluidas["id"].nunique()),
        "itens": int(itens["id"].nunique()),
        "unidades": int(itens["quantidade"].sum()),
        "receita": round(float(itens["subtotal"].sum()), 2),
    }

    obtido = conn.execute(text(f"""
        SELECT
            COUNT(DISTINCT venda_id_origem) AS vendas,
            COUNT(DISTINCT item_venda_id_origem) AS itens,
            COALESCE(ROUND(SUM(quantidade_atribuida)), 0) AS unidades,
            COALESCE(ROUND(SUM(receita_atribuida), 2), 0) AS receita
        FROM {DW_SCHEMA}.fact_vendas;
    """)).mappings().one()

    obtido = {
        "vendas": int(obtido["vendas"]),
        "itens": int(obtido["itens"]),
        "unidades": int(obtido["unidades"]),
        "receita": round(float(obtido["receita"]), 2),
    }

    pesos_errados = conn.execute(text(f"""
        SELECT COUNT(*)
        FROM (
            SELECT item_venda_id_origem
            FROM {DW_SCHEMA}.fact_vendas
            GROUP BY item_venda_id_origem
            HAVING ROUND(SUM(peso), 6) <> 1
        ) x;
    """)).scalar_one()

    if obtido != esperado or pesos_errados:
        raise RuntimeError(
            "A carga não coincide com a base operacional "
            f"(esperado {esperado}, obtido {obtido}, "
            f"itens com peso diferente de 1: {pesos_errados}). "
            "Nada foi alterado no Data Warehouse."
        )

    return obtido


def main():
    print(f"SABIN - ETL | CARGA DO DATA WAREHOUSE (esquema {DW_SCHEMA})")

    # Extração dos dados da base operacional.
    vendas = extrair_tabela("vendas")
    itens_venda = extrair_tabela("itens_venda")
    livros = extrair_tabela("livros")
    clientes = extrair_tabela("clientes")
    autores = extrair_tabela("autores")
    generos = extrair_tabela("generos")
    livro_autores = extrair_tabela("livro_autores")
    livro_generos = extrair_tabela("livro_generos")

    vendas_concluidas = vendas[
        vendas["status"] == "Concluída"
    ].copy()

    # Preparação das dimensões analíticas.
    dim_cliente = transformar_dim_cliente(clientes)
    dim_livro = transformar_dim_livro(livros)
    dim_pagamento = transformar_dim_pagamento(vendas_concluidas)
    dim_data = transformar_dim_data(vendas_concluidas)
    dim_autor = transformar_dim_autor(autores)
    dim_genero = transformar_dim_genero(generos)

    # Limpeza e carga numa única transação: se algum passo falhar,
    # o Data Warehouse fica exatamente como estava.
    with engine.begin() as conn:
        dias_novos = carregar_dim_data(conn, dim_data)
        carregar_dim_nivel_stock(conn)

        print(f"dim_data      -> {dias_novos} dia(s) acrescentado(s)")
        print("dim_nivel_stock -> verificada")

        historico_stock = ler_historico_stock(conn)

        # Reinicia as tabelas antes de carregar os novos dados.
        limpar_data_warehouse(conn)

        # Carga das dimensões.
        carregar_dim_cliente(conn, dim_cliente)
        carregar_dimensao(conn, "dim_livro", dim_livro)
        carregar_dimensao(conn, "dim_pagamento", dim_pagamento)
        carregar_dim_autor(conn, dim_autor)
        carregar_dim_genero(conn, dim_genero)

        print("dim_cliente   -> carregada")
        print("dim_livro     -> carregada")
        print("dim_pagamento -> carregada")
        print("dim_autor     -> carregada")
        print("dim_genero    -> carregada")

        # Lê as dimensões para obter as chaves geradas pela base de dados.
        dim_cliente_dw = ler_dimensao(conn, "dim_cliente")
        dim_livro_dw = ler_dimensao(conn, "dim_livro")
        dim_pagamento_dw = ler_dimensao(conn, "dim_pagamento")
        dim_data_dw = ler_dimensao(conn, "dim_data")
        dim_autor_dw = ler_dimensao(conn, "dim_autor")
        dim_genero_dw = ler_dimensao(conn, "dim_genero")

        # Constrói a tabela de factos (item x autor x género).
        fact_vendas = transformar_fact_vendas(
            vendas,
            itens_venda,
            livro_autores,
            livro_generos,
            dim_cliente_dw,
            dim_livro_dw,
            dim_autor_dw,
            dim_genero_dw,
            dim_pagamento_dw,
            dim_data_dw,
        )

        print()
        print(
            f"fact_vendas preparada -> "
            f"{len(fact_vendas)} linha(s)"
        )

        print(
            "Vendas distintas:",
            fact_vendas["venda_id_origem"].nunique()
        )

        print(
            "Itens de venda:",
            fact_vendas["item_venda_id_origem"].nunique()
        )

        print(
            "Unidades vendidas:",
            round(fact_vendas["quantidade_atribuida"].sum())
        )

        print(
            f"Receita total: "
            f"{fact_vendas['receita_atribuida'].sum():.2f} €"
        )

        print(
            "Linhas duplicadas (item x autor x género):",
            fact_vendas[
                [
                    "item_venda_id_origem",
                    "autor_key",
                    "genero_key",
                ]
            ]
            .duplicated()
            .sum()
        )

        # Carga da tabela de factos.
        carregar_dimensao(conn, "fact_vendas", fact_vendas)

        print("fact_vendas -> carregada")

        # Repõe as fotografias de stock anteriores.
        repostas, descartadas = repor_historico_stock(
            conn,
            historico_stock,
            dim_livro_dw,
        )

        print(
            f"fact_stock  -> {repostas} linha(s) de histórico mantida(s), "
            f"{descartadas} descartada(s)"
        )

        verificacao = verificar_carga(
            conn,
            vendas_concluidas,
            itens_venda,
        )

        print(
            "Verificação com a base operacional: OK "
            f"({verificacao['vendas']} vendas, "
            f"{verificacao['itens']} itens, "
            f"{verificacao['unidades']} unidades, "
            f"{verificacao['receita']:.2f} €)"
        )

    print()
    print("Data Warehouse carregado com sucesso.")


if __name__ == "__main__":
    main()
