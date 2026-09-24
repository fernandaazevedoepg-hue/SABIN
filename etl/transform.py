import pandas as pd

from extract import extrair_tabela


def transformar_dim_cliente(clientes):
    # Cria a dimensão cliente
    dim_cliente = clientes[
        [
            "id",
            "nome_completo",
            "data_registo",
        ]
    ].copy()

    dim_cliente = dim_cliente.rename(
        columns={
            "id": "cliente_id_origem"
        }
    )

    return dim_cliente


def transformar_dim_livro(livros):
    # Cria a dimensão livro
    dim_livro = livros[
        [
            "id",
            "titulo",
            "isbn",
            "editora",
            "data_publicacao",
        ]
    ].copy()

    dim_livro = dim_livro.rename(
        columns={
            "id": "livro_id_origem"
        }
    )

    return dim_livro


def transformar_dim_pagamento(vendas):
    # Cria a dimensão pagamento
    dim_pagamento = (
        vendas[["metodo_pagamento"]]
        .drop_duplicates()
        .sort_values("metodo_pagamento")
        .reset_index(drop=True)
    )

    return dim_pagamento


def transformar_dim_data(vendas):
    # Cria a dimensão data
    datas = vendas["data_venda"].dt.date.unique()

    dim_data = pd.DataFrame(
        {
            "data": pd.to_datetime(datas)
        }
    )

    dim_data = dim_data.sort_values("data").reset_index(drop=True)

    dim_data["data_key"] = (
        dim_data["data"]
        .dt.strftime("%Y%m%d")
        .astype(int)
    )

    dim_data["dia"] = dim_data["data"].dt.day
    dim_data["mes"] = dim_data["data"].dt.month
    dim_data["trimestre"] = dim_data["data"].dt.quarter
    dim_data["ano"] = dim_data["data"].dt.year

    dim_data["nome_mes"] = (
        dim_data["data"]
        .dt.month
        .map(
            {
                1: "Janeiro",
                2: "Fevereiro",
                3: "Março",
                4: "Abril",
                5: "Maio",
                6: "Junho",
                7: "Julho",
                8: "Agosto",
                9: "Setembro",
                10: "Outubro",
                11: "Novembro",
                12: "Dezembro",
            }
        )
    )

    dim_data["dia_semana"] = (
        dim_data["data"]
        .dt.dayofweek
        .map(
            {
                0: "Segunda-feira",
                1: "Terça-feira",
                2: "Quarta-feira",
                3: "Quinta-feira",
                4: "Sexta-feira",
                5: "Sábado",
                6: "Domingo",
            }
        )
    )

    dim_data["fim_semana"] = (
        dim_data["data"].dt.dayofweek >= 5
    )

    return dim_data[
        [
            "data_key",
            "data",
            "dia",
            "mes",
            "nome_mes",
            "trimestre",
            "ano",
            "dia_semana",
            "fim_semana",
        ]
    ]


def transformar_dim_autor(autores):
    # Cria a dimensão autor
    dim_autor = autores[
        [
            "id",
            "nome",
            "nacionalidade",
            "data_nascimento",
        ]
    ].copy()

    dim_autor = dim_autor.rename(
        columns={
            "id": "autor_id_origem"
        }
    )

    return dim_autor


def transformar_dim_genero(generos):
    # Cria a dimensão género
    dim_genero = generos[
        [
            "id",
            "nome",
            "descricao",
        ]
    ].copy()

    dim_genero = dim_genero.rename(
        columns={
            "id": "genero_id_origem"
        }
    )

    return dim_genero


def transformar_fact_vendas(
    vendas,
    itens_venda,
    dim_cliente,
    dim_livro,
    dim_pagamento,
    dim_data,
):
    # Mantém apenas vendas concluídas
    vendas_concluidas = vendas[
        vendas["status"] == "Concluída"
    ].copy()

    # Seleciona os dados necessários das vendas
    vendas_base = vendas_concluidas[
        [
            "id",
            "cliente_id",
            "data_venda",
            "metodo_pagamento",
        ]
    ].copy()

    vendas_base = vendas_base.rename(
        columns={
            "id": "venda_id_origem"
        }
    )

    # Prepara os itens das vendas
    itens_base = itens_venda.copy()

    itens_base = itens_base.rename(
        columns={
            "id": "item_venda_id_origem"
        }
    )

    # Junta cada item à venda a que pertence
    fact = itens_base.merge(
        vendas_base,
        left_on="venda_id",
        right_on="venda_id_origem",
        how="inner",
        validate="many_to_one",
    )

    # Cria a chave da dimensão data
    fact["data_key"] = (
        pd.to_datetime(fact["data_venda"])
        .dt.strftime("%Y%m%d")
        .astype(int)
    )

    # Procura a chave do livro no Data Warehouse
    fact = fact.merge(
        dim_livro[
            [
                "livro_key",
                "livro_id_origem",
            ]
        ],
        left_on="livro_id",
        right_on="livro_id_origem",
        how="left",
        validate="many_to_one",
    )

    # Procura a chave do método de pagamento
    fact = fact.merge(
        dim_pagamento[
            [
                "pagamento_key",
                "metodo_pagamento",
            ]
        ],
        on="metodo_pagamento",
        how="left",
        validate="many_to_one",
    )

    # Separa apenas os clientes identificados
    clientes_conhecidos = dim_cliente[
        dim_cliente["cliente_id_origem"].notna()
    ][
        [
            "cliente_key",
            "cliente_id_origem",
        ]
    ].copy()

    # Procura a chave do cliente
    fact = fact.merge(
        clientes_conhecidos,
        left_on="cliente_id",
        right_on="cliente_id_origem",
        how="left",
        validate="many_to_one",
    )

    # Descobre a chave do cliente não identificado
    cliente_desconhecido_key = int(
        dim_cliente.loc[
            dim_cliente["cliente_id_origem"].isna(),
            "cliente_key",
        ].iloc[0]
    )

    # Vendas sem cliente recebem a chave do cliente não identificado
    fact["cliente_key"] = (
        fact["cliente_key"]
        .fillna(cliente_desconhecido_key)
        .astype("int64")
    )

    # Confirma que todos os livros foram encontrados
    if fact["livro_key"].isna().any():
        raise ValueError(
            "Existem livros sem correspondência na dim_livro."
        )

    # Confirma que todos os pagamentos foram encontrados
    if fact["pagamento_key"].isna().any():
        raise ValueError(
            "Existem métodos de pagamento sem correspondência."
        )

    # Confirma que todas as datas existem na dimensão data
    if not fact["data_key"].isin(
        dim_data["data_key"]
    ).all():
        raise ValueError(
            "Existem datas sem correspondência na dim_data."
        )

    fact["livro_key"] = fact["livro_key"].astype("int64")
    fact["pagamento_key"] = fact["pagamento_key"].astype("int64")

    # Mantém apenas as colunas da tabela de factos
    fact = fact[
        [
            "data_key",
            "cliente_key",
            "livro_key",
            "pagamento_key",
            "venda_id_origem",
            "item_venda_id_origem",
            "quantidade",
            "preco_unitario",
            "subtotal",
        ]
    ]

    return fact

def transformar_bridge_livro_autor(
    livro_autores,
    dim_livro,
    dim_autor,
):
    # Liga os IDs originais às chaves do Data Warehouse
    bridge = livro_autores.merge(
        dim_livro[
            [
                "livro_key",
                "livro_id_origem",
            ]
        ],
        left_on="livro_id",
        right_on="livro_id_origem",
        how="left",
        validate="many_to_one",
    )

    bridge = bridge.merge(
        dim_autor[
            [
                "autor_key",
                "autor_id_origem",
            ]
        ],
        left_on="autor_id",
        right_on="autor_id_origem",
        how="left",
        validate="many_to_one",
    )

    if bridge["livro_key"].isna().any():
        raise ValueError(
            "Existem livros sem correspondência na dim_livro."
        )

    if bridge["autor_key"].isna().any():
        raise ValueError(
            "Existem autores sem correspondência na dim_autor."
        )

    bridge["livro_key"] = bridge["livro_key"].astype("int64")
    bridge["autor_key"] = bridge["autor_key"].astype("int64")

    return bridge[
        [
            "livro_key",
            "autor_key",
        ]
    ].drop_duplicates()


def transformar_bridge_livro_genero(
    livro_generos,
    dim_livro,
    dim_genero,
):
    # Liga os IDs originais às chaves do Data Warehouse
    bridge = livro_generos.merge(
        dim_livro[
            [
                "livro_key",
                "livro_id_origem",
            ]
        ],
        left_on="livro_id",
        right_on="livro_id_origem",
        how="left",
        validate="many_to_one",
    )

    bridge = bridge.merge(
        dim_genero[
            [
                "genero_key",
                "genero_id_origem",
            ]
        ],
        left_on="genero_id",
        right_on="genero_id_origem",
        how="left",
        validate="many_to_one",
    )

    if bridge["livro_key"].isna().any():
        raise ValueError(
            "Existem livros sem correspondência na dim_livro."
        )

    if bridge["genero_key"].isna().any():
        raise ValueError(
            "Existem géneros sem correspondência na dim_genero."
        )

    bridge["livro_key"] = bridge["livro_key"].astype("int64")
    bridge["genero_key"] = bridge["genero_key"].astype("int64")

    return bridge[
        [
            "livro_key",
            "genero_key",
        ]
    ].drop_duplicates()

def main():
    print("SABIN - ETL | TRANSFORMAÇÃO")

    # Extrair dados da base operacional
    vendas = extrair_tabela("vendas")
    livros = extrair_tabela("livros")
    clientes = extrair_tabela("clientes")
    autores = extrair_tabela("autores")
    generos = extrair_tabela("generos")

    # Apenas vendas concluídas entram nas dimensões analíticas
    vendas = vendas[
        vendas["status"] == "Concluída"
    ].copy()

    # Transformar os dados
    dim_cliente = transformar_dim_cliente(clientes)
    dim_livro = transformar_dim_livro(livros)
    dim_pagamento = transformar_dim_pagamento(vendas)
    dim_data = transformar_dim_data(vendas)
    dim_autor = transformar_dim_autor(autores)
    dim_genero = transformar_dim_genero(generos)

    # Mostrar os resultados
    print(f"dim_cliente   -> {len(dim_cliente)} linha(s)")
    print(f"dim_livro     -> {len(dim_livro)} linha(s)")
    print(f"dim_pagamento -> {len(dim_pagamento)} linha(s)")
    print(f"dim_data      -> {len(dim_data)} linha(s)")
    print(f"dim_autor     -> {len(dim_autor)} linha(s)")
    print(f"dim_genero    -> {len(dim_genero)} linha(s)")

    print("\nDIM_AUTOR:")
    print(dim_autor.head())

    print("\nDIM_GENERO:")
    print(dim_genero.head())


if __name__ == "__main__":
    main()