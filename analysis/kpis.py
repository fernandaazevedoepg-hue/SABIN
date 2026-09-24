import pandas as pd

from etl.extract import engine


def carregar_vendas_dw():
    # Lê os dados da tabela de factos
    query = """
    SELECT
        venda_id_origem,
        item_venda_id_origem,
        quantidade,
        preco_unitario,
        subtotal
    FROM dw.fact_vendas;
    """

    return pd.read_sql(query, engine)


def calcular_kpis(fact_vendas):
    # Receita total
    receita_total = fact_vendas["subtotal"].sum()

    # Número de vendas diferentes
    numero_vendas = fact_vendas[
        "venda_id_origem"
    ].nunique()

    # Total de unidades vendidas
    unidades_vendidas = fact_vendas[
        "quantidade"
    ].sum()

    # Número de linhas de venda
    linhas_venda = len(fact_vendas)

    # Ticket médio por venda
    ticket_medio = (
        receita_total / numero_vendas
        if numero_vendas > 0
        else 0
    )

    # Receita média por linha de venda
    valor_medio_linha = (
        receita_total / linhas_venda
        if linhas_venda > 0
        else 0
    )

    # Quantidade média de unidades por venda
    unidades_media_venda = (
        unidades_vendidas / numero_vendas
        if numero_vendas > 0
        else 0
    )

    # Valor médio por unidade vendida
    valor_medio_unidade = (
        receita_total / unidades_vendidas
        if unidades_vendidas > 0
        else 0
    )

    return {
        "receita_total": receita_total,
        "numero_vendas": numero_vendas,
        "unidades_vendidas": unidades_vendidas,
        "linhas_venda": linhas_venda,
        "ticket_medio": ticket_medio,
        "valor_medio_linha": valor_medio_linha,
        "unidades_media_venda": unidades_media_venda,
        "valor_medio_unidade": valor_medio_unidade,
    }


def mostrar_kpis(kpis):
    print("SABIN - INDICADORES DE DESEMPENHO")
    print()

    print(
        f"Receita total: "
        f"{kpis['receita_total']:.2f} €"
    )

    print(
        f"Número de vendas: "
        f"{kpis['numero_vendas']}"
    )

    print(
        f"Unidades vendidas: "
        f"{kpis['unidades_vendidas']}"
    )

    print(
        f"Linhas de venda: "
        f"{kpis['linhas_venda']}"
    )

    print(
        f"Ticket médio: "
        f"{kpis['ticket_medio']:.2f} €"
    )

    print(
        f"Valor médio por linha: "
        f"{kpis['valor_medio_linha']:.2f} €"
    )

    print(
        f"Média de unidades por venda: "
        f"{kpis['unidades_media_venda']:.2f}"
    )

    print(
        f"Valor médio por unidade: "
        f"{kpis['valor_medio_unidade']:.2f} €"
    )


def main():
    fact_vendas = carregar_vendas_dw()

    kpis = calcular_kpis(fact_vendas)

    mostrar_kpis(kpis)


if __name__ == "__main__":
    main()