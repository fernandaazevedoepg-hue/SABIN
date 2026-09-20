import pandas as pd
from sqlalchemy import text

from extract import engine, extrair_tabela

from transform import (
    transformar_dim_cliente,
    transformar_dim_livro,
    transformar_dim_pagamento,
    transformar_dim_data,
    transformar_fact_vendas,
)


def limpar_data_warehouse():
    # Limpa o Data Warehouse antes da carga completa
    query = """
    TRUNCATE TABLE
        dw.fact_vendas,
        dw.dim_cliente,
        dw.dim_livro,
        dw.dim_pagamento,
        dw.dim_data
    RESTART IDENTITY CASCADE;
    """

    with engine.begin() as conn:
        conn.execute(text(query))


def carregar_dim_cliente(dim_cliente):
    # Cria o cliente usado para vendas sem identificação
    cliente_desconhecido = pd.DataFrame(
        [
            {
                "cliente_id_origem": None,
                "nome_completo": "Cliente não identificado",
                "data_registo": None,
            }
        ]
    )

    dim_cliente = pd.concat(
        [cliente_desconhecido, dim_cliente],
        ignore_index=True,
    )

    dim_cliente.to_sql(
        "dim_cliente",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )


def carregar_dim_livro(dim_livro):
    dim_livro.to_sql(
        "dim_livro",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )


def carregar_dim_pagamento(dim_pagamento):
    dim_pagamento.to_sql(
        "dim_pagamento",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )


def carregar_dim_data(dim_data):
    dim_data.to_sql(
        "dim_data",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )


def ler_dimensao(nome_tabela):
    # Lê a dimensão já carregada no DW
    query = f"SELECT * FROM dw.{nome_tabela};"

    return pd.read_sql(query, engine)


def carregar_fact_vendas(fact_vendas):
    # Carrega a tabela de factos
    fact_vendas.to_sql(
        "fact_vendas",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )


def main():
    print("=" * 60)
    print("SABIN - ETL | CARGA DO DATA WAREHOUSE")
    print("=" * 60)

    # Extract
    vendas = extrair_tabela("vendas")
    itens_venda = extrair_tabela("itens_venda")
    livros = extrair_tabela("livros")
    clientes = extrair_tabela("clientes")

    vendas_concluidas = vendas[
        vendas["status"] == "Concluída"
    ].copy()

    # Transform das dimensões
    dim_cliente = transformar_dim_cliente(clientes)
    dim_livro = transformar_dim_livro(livros)
    dim_pagamento = transformar_dim_pagamento(vendas_concluidas)
    dim_data = transformar_dim_data(vendas_concluidas)

    # Limpar DW
    limpar_data_warehouse()

    # Load das dimensões
    carregar_dim_cliente(dim_cliente)
    carregar_dim_livro(dim_livro)
    carregar_dim_pagamento(dim_pagamento)
    carregar_dim_data(dim_data)

    print("dim_cliente   -> carregada")
    print("dim_livro     -> carregada")
    print("dim_pagamento -> carregada")
    print("dim_data      -> carregada")

    # Ler as dimensões novamente para obter as surrogate keys
    dim_cliente_dw = ler_dimensao("dim_cliente")
    dim_livro_dw = ler_dimensao("dim_livro")
    dim_pagamento_dw = ler_dimensao("dim_pagamento")
    dim_data_dw = ler_dimensao("dim_data")

    # Transform da fact_vendas
    fact_vendas = transformar_fact_vendas(
        vendas,
        itens_venda,
        dim_cliente_dw,
        dim_livro_dw,
        dim_pagamento_dw,
        dim_data_dw,
    )

    print()
    print(f"fact_vendas preparada -> {len(fact_vendas)} linha(s)")
    print(
        "Vendas distintas:",
        fact_vendas["venda_id_origem"].nunique()
    )
    print(
        "Unidades vendidas:",
        fact_vendas["quantidade"].sum()
    )
    print(
        "Receita total:",
        fact_vendas["subtotal"].sum()
    )
    print(
        "Itens duplicados:",
        fact_vendas["item_venda_id_origem"]
        .duplicated()
        .sum()
    )

    # Load da fact
    carregar_fact_vendas(fact_vendas)

    print("fact_vendas   -> carregada")
    print()
    print("Data Warehouse carregado com sucesso.")


if __name__ == "__main__":
    main()