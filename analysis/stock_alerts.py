import os

import numpy as np
import pandas as pd

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL não encontrada no ficheiro .env"
    )

engine = create_engine(DATABASE_URL)


def obter_data_referencia():
    query = text("""
        SELECT MAX(d.data) AS ultima_data
        FROM dw.fact_vendas f
        JOIN dw.dim_data d
            ON d.data_key = f.data_key;
    """)

    with engine.connect() as connection:
        resultado = pd.read_sql(
            query,
            connection
        )

    return pd.to_datetime(
        resultado.iloc[0]["ultima_data"]
    )


def carregar_stock():
    query = text("""
        SELECT
            id AS livro_id,
            titulo,
            isbn,
            preco_venda,
            estoque_atual,
            qtd_reservada
        FROM public.livros
        ORDER BY titulo;
    """)

    with engine.connect() as connection:
        df = pd.read_sql(
            query,
            connection
        )

    return df


def carregar_vendas_recentes(
    data_inicio,
    data_fim
):
    query = text("""
        SELECT
            l.livro_id_origem AS livro_id,
            SUM(f.quantidade) AS unidades_ultimos_3_meses
        FROM dw.fact_vendas f
        JOIN dw.dim_data d
            ON d.data_key = f.data_key
        JOIN dw.dim_livro l
            ON l.livro_key = f.livro_key
        WHERE d.data >= :data_inicio
          AND d.data < :data_fim
        GROUP BY l.livro_id_origem;
    """)

    with engine.connect() as connection:
        df = pd.read_sql(
            query,
            connection,
            params={
                "data_inicio": data_inicio,
                "data_fim": data_fim
            }
        )

    return df


def classificar_alerta(linha):
    media = linha["media_mensal_vendas"]
    cobertura = linha["meses_cobertura"]
    stock = linha["stock_disponivel"]

    if media == 0:
        return "Sem procura recente"

    if stock <= 0:
        return "Crítico"

    if cobertura < 1:
        return "Crítico"

    if cobertura < 2:
        return "Atenção"

    return "Normal"


def criar_recomendacao(linha):
    nivel = linha["nivel"]

    if nivel == "Crítico":
        return "Repor stock com prioridade"

    if nivel == "Atenção":
        return "Planear reposição"

    if nivel == "Sem procura recente":
        return "Sem reposição urgente"

    return "Stock suficiente"


def analisar_stock():
    data_referencia = obter_data_referencia()

    primeiro_dia_mes = (
        data_referencia
        .to_period("M")
        .to_timestamp()
    )

    data_inicio = (
        primeiro_dia_mes
        - pd.DateOffset(months=2)
    )

    data_fim = (
        primeiro_dia_mes
        + pd.DateOffset(months=1)
    )

    stock = carregar_stock()

    vendas = carregar_vendas_recentes(
        data_inicio,
        data_fim
    )

    dados = stock.merge(
        vendas,
        on="livro_id",
        how="left"
    )

    dados[
        "unidades_ultimos_3_meses"
    ] = (
        dados["unidades_ultimos_3_meses"]
        .fillna(0)
        .astype(int)
    )

    dados["stock_disponivel"] = (
        dados["estoque_atual"]
        - dados["qtd_reservada"]
    ).clip(lower=0)

    dados["media_mensal_vendas"] = (
        dados["unidades_ultimos_3_meses"]
        / 3
    ).round(2)

    dados["meses_cobertura"] = np.where(
        dados["media_mensal_vendas"] > 0,
        (
            dados["stock_disponivel"]
            / dados["media_mensal_vendas"]
        ),
        np.nan
    )

    dados["meses_cobertura"] = (
        dados["meses_cobertura"]
        .round(2)
    )

    # Objetivo de stock para cerca de 3 meses
    dados["quantidade_recomendada"] = np.ceil(
        (
            dados["media_mensal_vendas"] * 3
        )
        - dados["stock_disponivel"]
    ).clip(lower=0).astype(int)

    dados["nivel"] = dados.apply(
        classificar_alerta,
        axis=1
    )

    dados["recomendacao"] = dados.apply(
        criar_recomendacao,
        axis=1
    )

    dados["data_referencia"] = (
        data_referencia.date()
    )

    ordem = {
        "Crítico": 1,
        "Atenção": 2,
        "Normal": 3,
        "Sem procura recente": 4
    }

    dados["ordem"] = (
        dados["nivel"]
        .map(ordem)
    )

    dados = dados.sort_values(
        [
            "ordem",
            "meses_cobertura"
        ],
        na_position="last"
    )

    dados = dados.drop(
        columns=["ordem"]
    )

    return dados, data_inicio, data_referencia


def guardar_resultados(dados):
    os.makedirs(
        "outputs",
        exist_ok=True
    )

    dados.to_csv(
        "outputs/alertas_stock.csv",
        index=False,
        encoding="utf-8-sig"
    )

    dados.to_sql(
        "alertas_stock",
        engine,
        schema="dw",
        if_exists="replace",
        index=False
    )


def main():
    print()
    print("SABIN - ALERTAS DE STOCK")
    print()

    dados, data_inicio, data_referencia = (
        analisar_stock()
    )

    guardar_resultados(dados)

    print(
        f"Período analisado: "
        f"{data_inicio.strftime('%m/%Y')} "
        f"até "
        f"{data_referencia.strftime('%m/%Y')}"
    )

    print()

    print(
        f"Livros analisados: {len(dados)}"
    )

    print(
        "Críticos:",
        len(
            dados[
                dados["nivel"] == "Crítico"
            ]
        )
    )

    print(
        "Atenção:",
        len(
            dados[
                dados["nivel"] == "Atenção"
            ]
        )
    )

    print(
        "Normais:",
        len(
            dados[
                dados["nivel"] == "Normal"
            ]
        )
    )

    print(
        "Sem procura recente:",
        len(
            dados[
                dados["nivel"]
                == "Sem procura recente"
            ]
        )
    )

    print()
    print("LIVROS QUE NECESSITAM DE ATENÇÃO")
    print()

    alertas = dados[
        dados["nivel"].isin(
            ["Crítico", "Atenção"]
        )
    ]

    if alertas.empty:
        print(
            "Nenhum alerta de stock encontrado."
        )

    else:
        for _, linha in alertas.iterrows():
            print(
                f"[{linha['nivel']}] "
                f"{linha['titulo']}"
            )

            print(
                f"Stock disponível: "
                f"{linha['stock_disponivel']}"
            )

            print(
                f"Média mensal: "
                f"{linha['media_mensal_vendas']:.2f}"
            )

            print(
                f"Meses de cobertura: "
                f"{linha['meses_cobertura']:.2f}"
            )

            print(
                f"Reposição recomendada: "
                f"{linha['quantidade_recomendada']}"
            )

            print()

    print(
        "Tabela criada:"
    )
    print(
        "dw.alertas_stock"
    )

    print()

    print(
        "Ficheiro criado:"
    )
    print(
        "outputs/alertas_stock.csv"
    )

    print()

    print(
        "Análise de stock concluída com sucesso."
    )


if __name__ == "__main__":
    main()