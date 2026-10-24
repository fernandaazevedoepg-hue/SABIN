import math
import os

import pandas as pd
from sqlalchemy import text

from analysis.dw_consultas import (
    DW_SCHEMA,
    data_key,
    obter_data_referencia_sql,
    verificar_datas,
)

from services.base_dados import engine


MESES_ANALISE = 3
MESES_STOCK_ALVO = 3


def obter_data_referencia():
    """Obtém a data usada como referência para analisar o stock."""
    query = text("""
        SELECT COALESCE(
            CAST(:data_referencia AS date),
            CURRENT_DATE
        ) AS data_referencia;
    """)

    with engine.connect() as connection:
        resultado = connection.execute(
            query,
            {"data_referencia": obter_data_referencia_sql()},
        ).mappings().one()

    return pd.Timestamp(
        resultado["data_referencia"]
    )


def carregar_livros():
    """Carrega os livros e as quantidades disponíveis."""
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
        dados = pd.read_sql(
            query,
            connection,
        )

    return dados


def carregar_vendas_periodo(
    data_inicio,
    data_fim,
):
    """Obtém as vendas do período usado na análise de stock."""
    query = text("""
        SELECT
            iv.livro_id,
            COALESCE(
                SUM(iv.quantidade),
                0
            ) AS unidades_vendidas
        FROM public.vendas v
        JOIN public.itens_venda iv
            ON iv.venda_id = v.id
        WHERE
            v.status = 'Concluída'
            AND v.data_venda::date >= :data_inicio
            AND v.data_venda::date <= :data_fim
        GROUP BY
            iv.livro_id;
    """)

    with engine.connect() as connection:
        dados = pd.read_sql(
            query,
            connection,
            params={
                "data_inicio": data_inicio.date(),
                "data_fim": data_fim.date(),
            },
        )

    return dados


def calcular_nivel(
    stock_disponivel,
    media_mensal_vendas,
    meses_cobertura,
):
    """Classifica o nível de stock com base nos critérios definidos."""
    if stock_disponivel <= 1:
        return "Crítico"

    if media_mensal_vendas <= 0:
        return "Sem procura recente"

    if meses_cobertura < 1:
        return "Crítico"

    if meses_cobertura < 2:
        return "Atenção"

    return "Normal"


def calcular_recomendacao(nivel):
    """Define a recomendação associada ao nível de stock."""
    if nivel == "Crítico":
        return "Repor stock com prioridade"

    if nivel == "Atenção":
        return "Planear reposição"

    if nivel == "Sem procura recente":
        return "Sem procura recente"

    return "Stock suficiente"


def calcular_quantidade_recomendada(
    stock_disponivel,
    media_mensal_vendas,
    nivel,
):
    """Calcula a quantidade sugerida para reposição."""
    if nivel == "Sem procura recente":
        return 0

    stock_alvo = (
        media_mensal_vendas
        * MESES_STOCK_ALVO
    )

    quantidade = max(
        stock_alvo - stock_disponivel,
        0,
    )

    return int(
        math.ceil(quantidade)
    )


def gerar_alertas_stock():
    """Analisa o stock e cria alertas para os livros que precisam de atenção."""
    data_referencia = obter_data_referencia()

    data_inicio = (
        data_referencia
        - pd.DateOffset(
            months=MESES_ANALISE
        )
    )

    livros = carregar_livros()

    vendas = carregar_vendas_periodo(
        data_inicio,
        data_referencia,
    )

    dados = livros.merge(
        vendas,
        on="livro_id",
        how="left",
    )

    dados[
        "unidades_vendidas"
    ] = (
        dados[
            "unidades_vendidas"
        ]
        .fillna(0)
        .astype(int)
    )

    resultados = []

    for _, livro in dados.iterrows():
        estoque_atual = int(
            livro["estoque_atual"]
        )

        qtd_reservada = int(
            livro["qtd_reservada"]
        )

        stock_disponivel = max(
            estoque_atual
            - qtd_reservada,
            0,
        )

        unidades = int(
            livro[
                "unidades_vendidas"
            ]
        )

        media_mensal = (
            unidades
            / MESES_ANALISE
        )

        if media_mensal > 0:
            meses_cobertura = (
                stock_disponivel
                / media_mensal
            )
        else:
            meses_cobertura = None

        nivel = calcular_nivel(
            stock_disponivel,
            media_mensal,
            (
                meses_cobertura
                if meses_cobertura is not None
                else float("inf")
            ),
        )

        quantidade_recomendada = (
            calcular_quantidade_recomendada(
                stock_disponivel,
                media_mensal,
                nivel,
            )
        )

        recomendacao = (
            calcular_recomendacao(
                nivel
            )
        )

        resultados.append(
            {
                "data_referencia": (
                    data_referencia.date()
                ),
                "livro_id": int(
                    livro["livro_id"]
                ),
                "titulo": livro[
                    "titulo"
                ],
                "isbn": livro[
                    "isbn"
                ],
                "preco_venda": float(
                    livro["preco_venda"]
                ),
                "estoque_atual": (
                    estoque_atual
                ),
                "qtd_reservada": (
                    qtd_reservada
                ),
                "stock_disponivel": (
                    stock_disponivel
                ),
                "unidades_ultimos_3_meses": (
                    unidades
                ),
                "media_mensal_vendas": round(
                    media_mensal,
                    2,
                ),
                "meses_cobertura": (
                    round(
                        meses_cobertura,
                        2,
                    )
                    if meses_cobertura is not None
                    else None
                ),
                "quantidade_recomendada": (
                    quantidade_recomendada
                ),
                "nivel": nivel,
                "recomendacao": (
                    recomendacao
                ),
            }
        )

    return (
        pd.DataFrame(resultados),
        data_inicio,
        data_referencia,
    )


def guardar_alertas_stock(dados):
    """Guarda os alertas de stock para consulta e análise.

    No Data Warehouse, grava uma fotografia por dia na fact_stock (grão
    livro x data): a fotografia do mesmo dia é substituída e as dos dias
    anteriores mantêm-se. Livros que ainda não estão na dim_livro (por
    exemplo, acabados de criar) só entram depois da próxima execução do ETL.
    """
    os.makedirs(
        "outputs",
        exist_ok=True,
    )

    dados.to_csv(
        "outputs/alertas_stock.csv",
        index=False,
        encoding="utf-8-sig",
    )

    if dados.empty:
        return 0

    chave_data = data_key(
        dados.iloc[0]["data_referencia"]
    )

    with engine.begin() as connection:
        verificar_datas(
            connection,
            [chave_data],
        )

        livros = pd.read_sql(
            text(f"""
                SELECT livro_key, livro_id_origem AS livro_id
                FROM {DW_SCHEMA}.dim_livro;
            """),
            connection,
        )

        niveis = pd.read_sql(
            text(f"""
                SELECT nivel_key, nivel
                FROM {DW_SCHEMA}.dim_nivel_stock;
            """),
            connection,
        )

        fact = dados.merge(
            livros,
            on="livro_id",
            how="inner",
            validate="one_to_one",
        ).merge(
            niveis,
            on="nivel",
            how="left",
            validate="many_to_one",
        )

        if fact["nivel_key"].isna().any():
            raise ValueError(
                "Existem níveis de stock sem correspondência "
                "na dim_nivel_stock."
            )

        sem_livro = len(dados) - len(fact)

        if sem_livro:
            print(
                f"Aviso: {sem_livro} livro(s) ainda não estão na "
                "dim_livro e ficam para a próxima execução do ETL."
            )

        fact["data_key"] = chave_data
        fact["nivel_key"] = fact["nivel_key"].astype("int64")

        fact = fact[
            [
                "data_key",
                "livro_key",
                "nivel_key",
                "estoque_atual",
                "qtd_reservada",
                "stock_disponivel",
                "unidades_ultimos_3_meses",
                "media_mensal_vendas",
                "meses_cobertura",
                "quantidade_recomendada",
                "preco_venda",
            ]
        ]

        connection.execute(
            text(f"""
                DELETE FROM {DW_SCHEMA}.fact_stock
                WHERE data_key = :data_key;
            """),
            {"data_key": chave_data},
        )

        fact.to_sql(
            "fact_stock",
            connection,
            schema=DW_SCHEMA,
            if_exists="append",
            index=False,
        )

    return len(fact)


def main():
    print()
    print(
        "SABIN - ALERTAS DE STOCK"
    )
    print()

    dados, data_inicio, data_fim = (
        gerar_alertas_stock()
    )

    gravados = guardar_alertas_stock(
        dados
    )

    criticos = len(
        dados[
            dados["nivel"]
            == "Crítico"
        ]
    )

    atencao = len(
        dados[
            dados["nivel"]
            == "Atenção"
        ]
    )

    normais = len(
        dados[
            dados["nivel"]
            == "Normal"
        ]
    )

    sem_procura = len(
        dados[
            dados["nivel"]
            == "Sem procura recente"
        ]
    )

    print(
        "Período analisado: "
        f"{data_inicio.strftime('%m/%Y')} "
        "até "
        f"{data_fim.strftime('%m/%Y')}"
    )

    print()

    print(
        f"Livros analisados: {len(dados)}"
    )

    print(
        f"Críticos: {criticos}"
    )

    print(
        f"Atenção: {atencao}"
    )

    print(
        f"Normais: {normais}"
    )

    print(
        "Sem procura recente: "
        f"{sem_procura}"
    )

    print()
    print(
        "LIVROS QUE NECESSITAM "
        "DE ATENÇÃO"
    )
    print()

    alertas = dados[
        dados["nivel"].isin(
            [
                "Crítico",
                "Atenção",
            ]
        )
    ]

    if alertas.empty:
        print(
            "Nenhum alerta de stock "
            "encontrado."
        )
    else:
        for _, livro in (
            alertas.iterrows()
        ):
            print(
                f"[{livro['nivel']}] "
                f"{livro['titulo']}"
            )

            print(
                "Stock disponível: "
                f"{livro['stock_disponivel']}"
            )

            if pd.notna(
                livro[
                    "meses_cobertura"
                ]
            ):
                print(
                    "Cobertura: "
                    f"{livro['meses_cobertura']:.2f} "
                    "meses"
                )

            print(
                "Quantidade recomendada: "
                f"{livro['quantidade_recomendada']}"
            )

            print(
                f"Recomendação: "
                f"{livro['recomendacao']}"
            )

            print()

    print(
        "Tabela atualizada:"
    )

    print(
        f"{DW_SCHEMA}.fact_stock "
        f"({gravados} livro(s) em "
        f"{data_fim.strftime('%d/%m/%Y')})"
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
        "Análise de stock concluída "
        "com sucesso."
    )


if __name__ == "__main__":
    main()
