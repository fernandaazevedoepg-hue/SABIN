import pandas as pd

from etl.extract import DW_SCHEMA
from services.base_dados import engine


def carregar_vendas_dw():
    """Carrega do Data Warehouse os dados necessários aos indicadores.

    A fact_vendas tem uma linha por item x autor x género. As linhas de cada
    item são somadas (os pesos somam 1), para voltar a ter uma linha por item
    de venda, com a quantidade e o subtotal originais.
    """
    query = f"""
    SELECT
        venda_id_origem,
        item_venda_id_origem,
        ROUND(SUM(quantidade_atribuida))::integer AS quantidade,
        MAX(preco_unitario) AS preco_unitario,
        ROUND(SUM(receita_atribuida), 2) AS subtotal
    FROM {DW_SCHEMA}.fact_vendas
    GROUP BY
        venda_id_origem,
        item_venda_id_origem;
    """

    return pd.read_sql(query, engine)


def calcular_kpis(fact_vendas):
    """Calcula indicadores de receita, vendas e quantidades.

    O ticket médio corresponde à receita dividida pelo número de vendas.
    Os rácios devolvem zero quando o respetivo denominador é zero.
    """
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