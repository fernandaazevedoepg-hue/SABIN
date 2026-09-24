import pandas as pd
from sqlalchemy import text

from extract import engine, extrair_tabela

from transform import (
    transformar_dim_cliente,
    transformar_dim_livro,
    transformar_dim_pagamento,
    transformar_dim_data,
    transformar_dim_autor,
    transformar_dim_genero,
    transformar_fact_vendas,
    transformar_bridge_livro_autor,
    transformar_bridge_livro_genero,
)


def limpar_data_warehouse():
    # Limpa todas as tabelas do Data Warehouse
    query = """
    TRUNCATE TABLE
        dw.fact_vendas,
        dw.bridge_livro_autor,
        dw.bridge_livro_genero,
        dw.dim_autor,
        dw.dim_genero,
        dw.dim_cliente,
        dw.dim_livro,
        dw.dim_pagamento,
        dw.dim_data
    RESTART IDENTITY CASCADE;
    """

    with engine.begin() as conn:
        conn.execute(text(query))


def carregar_dim_cliente(dim_cliente):
    # Cria o cliente utilizado nas vendas sem identificação
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


def carregar_dim_autor(dim_autor):
    dim_autor.to_sql(
        "dim_autor",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )


def carregar_dim_genero(dim_genero):
    dim_genero.to_sql(
        "dim_genero",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )


def carregar_bridge_livro_autor(bridge):
    bridge.to_sql(
        "bridge_livro_autor",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )


def carregar_bridge_livro_genero(bridge):
    bridge.to_sql(
        "bridge_livro_genero",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )


def ler_dimensao(nome_tabela):
    # Lê uma dimensão já carregada no Data Warehouse
    query = f"SELECT * FROM dw.{nome_tabela};"

    return pd.read_sql(query, engine)


def carregar_fact_vendas(fact_vendas):
    fact_vendas.to_sql(
        "fact_vendas",
        engine,
        schema="dw",
        if_exists="append",
        index=False,
    )


def main():
    print("SABIN - ETL | CARGA DO DATA WAREHOUSE")

    # Extract
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

    # Transform das dimensões
    dim_cliente = transformar_dim_cliente(clientes)
    dim_livro = transformar_dim_livro(livros)
    dim_pagamento = transformar_dim_pagamento(vendas_concluidas)
    dim_data = transformar_dim_data(vendas_concluidas)
    dim_autor = transformar_dim_autor(autores)
    dim_genero = transformar_dim_genero(generos)

    # Limpar o Data Warehouse
    limpar_data_warehouse()

    # Load das dimensões
    carregar_dim_cliente(dim_cliente)
    carregar_dim_livro(dim_livro)
    carregar_dim_pagamento(dim_pagamento)
    carregar_dim_data(dim_data)
    carregar_dim_autor(dim_autor)
    carregar_dim_genero(dim_genero)

    print("dim_cliente   -> carregada")
    print("dim_livro     -> carregada")
    print("dim_pagamento -> carregada")
    print("dim_data      -> carregada")
    print("dim_autor     -> carregada")
    print("dim_genero    -> carregada")

    # Ler dimensões já com as surrogate keys
    dim_cliente_dw = ler_dimensao("dim_cliente")
    dim_livro_dw = ler_dimensao("dim_livro")
    dim_pagamento_dw = ler_dimensao("dim_pagamento")
    dim_data_dw = ler_dimensao("dim_data")
    dim_autor_dw = ler_dimensao("dim_autor")
    dim_genero_dw = ler_dimensao("dim_genero")

    # Criar as bridges
    bridge_livro_autor = transformar_bridge_livro_autor(
        livro_autores,
        dim_livro_dw,
        dim_autor_dw,
    )

    bridge_livro_genero = transformar_bridge_livro_genero(
        livro_generos,
        dim_livro_dw,
        dim_genero_dw,
    )

    # Carregar as bridges
    carregar_bridge_livro_autor(bridge_livro_autor)
    carregar_bridge_livro_genero(bridge_livro_genero)

    print(
        f"bridge_livro_autor  -> "
        f"{len(bridge_livro_autor)} linha(s)"
    )

    print(
        f"bridge_livro_genero -> "
        f"{len(bridge_livro_genero)} linha(s)"
    )

    # Criar a fact_vendas
    fact_vendas = transformar_fact_vendas(
        vendas,
        itens_venda,
        dim_cliente_dw,
        dim_livro_dw,
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
        "Unidades vendidas:",
        fact_vendas["quantidade"].sum()
    )

    print(
        f"Receita total: "
        f"{fact_vendas['subtotal'].sum():.2f} €"
    )

    print(
        "Itens duplicados:",
        fact_vendas["item_venda_id_origem"]
        .duplicated()
        .sum()
    )

    # Load da fact
    carregar_fact_vendas(fact_vendas)

    print("fact_vendas -> carregada")
    print()
    print("Data Warehouse carregado com sucesso.")


if __name__ == "__main__":
    main()