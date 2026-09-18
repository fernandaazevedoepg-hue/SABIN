import pandas as pd

from extract import extrair_tabela


def transformar_dim_cliente(clientes):
 
   # Transforma os clientes da base operacional na dimensão cliente do Data Warehouse.

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

    # Cria a dimensão livro.

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
  
   # Cria uma dimensão com os métodos de pagamento existentes nas vendas.

    dim_pagamento = (
        vendas[["metodo_pagamento"]]
        .drop_duplicates()
        .sort_values("metodo_pagamento")
        .reset_index(drop=True)
    )

    return dim_pagamento


def transformar_dim_data(vendas):
 
    # Cria a dimensão calendário a partir das datas existentes nas vendas.

    datas = vendas["data_venda"].dt.date.unique()

    dim_data = pd.DataFrame(
        {
            "data": pd.to_datetime(datas)
        }
    )

    dim_data = dim_data.sort_values("data").reset_index(drop=True)

    dim_data["data_key"] = (
        dim_data["data"].dt.strftime("%Y%m%d").astype(int)
    )

    dim_data["dia"] = dim_data["data"].dt.day
    dim_data["mes"] = dim_data["data"].dt.month
    dim_data["trimestre"] = dim_data["data"].dt.quarter
    dim_data["ano"] = dim_data["data"].dt.year

    dim_data["nome_mes"] = (
        dim_data["data"]
        .dt.month
        .map({
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
        })
    )

    dim_data["dia_semana"] = (
        dim_data["data"]
        .dt.dayofweek
        .map({
            0: "Segunda-feira",
            1: "Terça-feira",
            2: "Quarta-feira",
            3: "Quinta-feira",
            4: "Sexta-feira",
            5: "Sábado",
            6: "Domingo",
        })
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


def main():

    print("=" * 60)
    print("SABIN - ETL | TRANSFORMAÇÃO")
    print("=" * 60)

    vendas = extrair_tabela("vendas")
    livros = extrair_tabela("livros")
    clientes = extrair_tabela("clientes")

    # Regra de negócio:
    # apenas vendas concluídas entram no DW
    vendas = vendas[
        vendas["status"] == "Concluída"
    ].copy()

    dim_cliente = transformar_dim_cliente(clientes)
    dim_livro = transformar_dim_livro(livros)
    dim_pagamento = transformar_dim_pagamento(vendas)
    dim_data = transformar_dim_data(vendas)

    print(f"dim_cliente   -> {len(dim_cliente)} linha(s)")
    print(f"dim_livro     -> {len(dim_livro)} linha(s)")
    print(f"dim_pagamento -> {len(dim_pagamento)} linha(s)")
    print(f"dim_data      -> {len(dim_data)} linha(s)")

    print("\nDIM_CLIENTE:")
    print(dim_cliente.head())

    print("\nDIM_PAGAMENTO:")
    print(dim_pagamento)

    print("\nDIM_DATA:")
    print(dim_data.head())


if __name__ == "__main__":
    main()