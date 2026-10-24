import os

import numpy as np
import pandas as pd

from sqlalchemy import text

from sklearn.linear_model import Ridge
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from analysis.dw_consultas import (
    DW_SCHEMA,
    data_key,
    obter_data_referencia_sql,
    verificar_datas,
)

from services.base_dados import engine


FEATURES = [
    "ordem",
    "mes_sin",
    "mes_cos",
    "lag_1",
    "lag_2",
    "lag_3",
    "media_3",
]


def carregar_receita_mensal():
    """Carrega a receita mensal real a partir do Data Warehouse."""
    query = text(f"""
        SELECT
            DATE_TRUNC(
                'month',
                d.data
            )::date AS mes,

            ROUND(
                SUM(f.receita_atribuida),
                2
            ) AS receita

        FROM {DW_SCHEMA}.fact_vendas f

        JOIN {DW_SCHEMA}.dim_data d
            ON f.data_key = d.data_key

        WHERE
            d.data < DATE_TRUNC(
                'month',
                COALESCE(
                    CAST(:data_referencia AS date),
                    CURRENT_DATE
                )
            )

        GROUP BY
            DATE_TRUNC(
                'month',
                d.data
            )

        ORDER BY mes;
    """)

    with engine.connect() as connection:
        df = pd.read_sql(
            query,
            connection,
            params={
                "data_referencia": obter_data_referencia_sql(),
            },
        )

    if df.empty:
        raise ValueError(
            "Não existem meses completos suficientes "
            "para executar o modelo."
        )

    df["mes"] = pd.to_datetime(
        df["mes"]
    )

    df["receita"] = pd.to_numeric(
        df["receita"]
    )

    return df


def criar_features(df):
    """Prepara as variáveis usadas pelo modelo de previsão."""
    dados = df.copy()

    dados["ordem"] = np.arange(
        len(dados)
    )

    dados["numero_mes"] = (
        dados["mes"].dt.month
    )

    dados["mes_sin"] = np.sin(
        2
        * np.pi
        * dados["numero_mes"]
        / 12
    )

    dados["mes_cos"] = np.cos(
        2
        * np.pi
        * dados["numero_mes"]
        / 12
    )

    dados["lag_1"] = (
        dados["receita"].shift(1)
    )

    dados["lag_2"] = (
        dados["receita"].shift(2)
    )

    dados["lag_3"] = (
        dados["receita"].shift(3)
    )

    dados["media_3"] = (
        dados["receita"]
        .shift(1)
        .rolling(3)
        .mean()
    )

    dados = (
        dados
        .dropna()
        .reset_index(
            drop=True
        )
    )

    return dados


def criar_modelo():
    """Cria o modelo de regressão utilizado para prever a receita."""
    return Pipeline(
        [
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "ridge",
                Ridge(
                    alpha=10.0
                ),
            ),
        ]
    )


def avaliar_modelo(
    dados_modelo
):
    """Avalia a qualidade do modelo com métricas de erro e ajuste."""
    meses_teste = 6

    if len(dados_modelo) <= meses_teste:
        raise ValueError(
            "Não existem dados suficientes "
            "para separar treino e teste."
        )

    treino = (
        dados_modelo
        .iloc[:-meses_teste]
    )

    teste = (
        dados_modelo
        .iloc[-meses_teste:]
    )

    modelo = criar_modelo()

    modelo.fit(
        treino[FEATURES],
        treino["receita"],
    )

    previsoes = modelo.predict(
        teste[FEATURES]
    )

    mae = mean_absolute_error(
        teste["receita"],
        previsoes,
    )

    rmse = np.sqrt(
        mean_squared_error(
            teste["receita"],
            previsoes,
        )
    )

    r2 = r2_score(
        teste["receita"],
        previsoes,
    )

    return (
        mae,
        rmse,
        r2,
    )


def prever_proximos_meses(
    df,
    dados_modelo,
    quantidade=3,
):
    """Gera previsões de receita para os meses seguintes."""
    modelo = criar_modelo()

    modelo.fit(
        dados_modelo[FEATURES],
        dados_modelo["receita"],
    )

    historico = df.copy()

    previsoes = []

    for _ in range(
        quantidade
    ):
        ultimo_mes = (
            historico["mes"]
            .max()
        )

        proximo_mes = (
            ultimo_mes
            + pd.offsets.MonthBegin(1)
        )

        ordem = len(
            historico
        )

        numero_mes = (
            proximo_mes.month
        )

        lag_1 = (
            historico
            .iloc[-1]["receita"]
        )

        lag_2 = (
            historico
            .iloc[-2]["receita"]
        )

        lag_3 = (
            historico
            .iloc[-3]["receita"]
        )

        media_3 = (
            historico
            .iloc[-3:]["receita"]
            .mean()
        )

        entrada = pd.DataFrame(
            [
                {
                    "ordem": ordem,
                    "mes_sin": np.sin(
                        2
                        * np.pi
                        * numero_mes
                        / 12
                    ),
                    "mes_cos": np.cos(
                        2
                        * np.pi
                        * numero_mes
                        / 12
                    ),
                    "lag_1": lag_1,
                    "lag_2": lag_2,
                    "lag_3": lag_3,
                    "media_3": media_3,
                }
            ]
        )

        receita_prevista = (
            modelo.predict(
                entrada[FEATURES]
            )[0]
        )

        receita_prevista = max(
            0,
            receita_prevista,
        )

        previsoes.append(
            {
                "mes": proximo_mes,
                "receita_prevista": round(
                    receita_prevista,
                    2,
                ),
            }
        )

        novo_registo = (
            pd.DataFrame(
                [
                    {
                        "mes": proximo_mes,
                        "receita": receita_prevista,
                    }
                ]
            )
        )

        historico = pd.concat(
            [
                historico,
                novo_registo,
            ],
            ignore_index=True,
        )

    return pd.DataFrame(
        previsoes
    )


def preparar_dados_powerbi(
    df,
    previsoes,
):
    """Organiza os resultados no formato usado pelos relatórios."""
    historico = df.copy()

    historico[
        "receita_real"
    ] = historico["receita"]

    historico[
        "receita_prevista"
    ] = np.nan

    historico[
        "tipo"
    ] = "Histórico"

    historico = historico[
        [
            "mes",
            "receita_real",
            "receita_prevista",
            "tipo",
        ]
    ]

    ultimo_registo = (
        historico
        .tail(1)
        .copy()
    )

    ultimo_registo[
        "receita_prevista"
    ] = ultimo_registo[
        "receita_real"
    ]

    ultimo_registo[
        "tipo"
    ] = "Ligação"

    futuro = previsoes.copy()

    futuro[
        "receita_real"
    ] = np.nan

    futuro[
        "tipo"
    ] = "Previsão"

    futuro = futuro[
        [
            "mes",
            "receita_real",
            "receita_prevista",
            "tipo",
        ]
    ]

    resultado = pd.concat(
        [
            historico,
            ultimo_registo,
            futuro,
        ],
        ignore_index=True,
    )

    return resultado


def guardar_resultados(
    dados_powerbi,
    previsoes,
    mae,
    rmse,
    r2,
    df,
):
    """Guarda previsões e métricas para consulta posterior."""
    os.makedirs(
        "outputs",
        exist_ok=True,
    )

    dados_powerbi.to_csv(
        "outputs/previsao_receita.csv",
        index=False,
        encoding="utf-8-sig",
    )

    ultima_receita = float(
        df.iloc[-1][
            "receita"
        ]
    )

    proxima_receita = float(
        previsoes.iloc[0][
            "receita_prevista"
        ]
    )

    if ultima_receita > 0:
        variacao_prevista = (
            (
                proxima_receita
                - ultima_receita
            )
            / ultima_receita
            * 100
        )
    else:
        variacao_prevista = 0

    if variacao_prevista > 5:
        tendencia = "Subida"

    elif variacao_prevista < -5:
        tendencia = "Descida"

    else:
        tendencia = "Estável"

    metricas = pd.DataFrame(
        [
            {
                "modelo": (
                    "Ridge Regression"
                ),
                "mae": round(
                    mae,
                    2,
                ),
                "rmse": round(
                    rmse,
                    2,
                ),
                "r2": round(
                    r2,
                    4,
                ),
                "ultimo_mes_real": (
                    df.iloc[-1][
                        "mes"
                    ]
                ),
                "ultima_receita_real": round(
                    ultima_receita,
                    2,
                ),
                "proximo_mes": (
                    previsoes.iloc[0][
                        "mes"
                    ]
                ),
                "receita_prevista_proximo_mes": round(
                    proxima_receita,
                    2,
                ),
                "variacao_prevista_percent": round(
                    variacao_prevista,
                    2,
                ),
                "tendencia": tendencia,
            }
        ]
    )

    metricas.to_csv(
        "outputs/metricas_previsao.csv",
        index=False,
        encoding="utf-8-sig",
    )

    guardar_previsao_dw(
        metricas.iloc[0],
        previsoes,
    )


def guardar_previsao_dw(
    metricas,
    previsoes,
):
    """Grava as métricas na dim_modelo_previsao e as previsões na fact_previsao.

    Grão da fact_previsao: mês previsto x modelo (data_key = 1.º dia do mês).
    As previsões anteriores do mesmo modelo são substituídas pelas novas,
    numa única transação.
    """
    chaves_data = [
        data_key(mes)
        for mes in previsoes["mes"]
    ]

    with engine.begin() as connection:
        verificar_datas(
            connection,
            chaves_data,
        )

        modelo_key = connection.execute(
            text(f"""
                INSERT INTO {DW_SCHEMA}.dim_modelo_previsao
                    (modelo, mae, rmse, r2)
                VALUES
                    (:modelo, :mae, :rmse, :r2)
                ON CONFLICT (modelo) DO UPDATE SET
                    mae = EXCLUDED.mae,
                    rmse = EXCLUDED.rmse,
                    r2 = EXCLUDED.r2
                RETURNING modelo_key;
            """),
            {
                "modelo": metricas["modelo"],
                "mae": float(metricas["mae"]),
                "rmse": float(metricas["rmse"]),
                "r2": float(metricas["r2"]),
            },
        ).scalar_one()

        connection.execute(
            text(f"""
                DELETE FROM {DW_SCHEMA}.fact_previsao
                WHERE modelo_key = :modelo_key;
            """),
            {"modelo_key": modelo_key},
        )

        for chave, receita in zip(
            chaves_data,
            previsoes["receita_prevista"],
        ):
            connection.execute(
                text(f"""
                    INSERT INTO {DW_SCHEMA}.fact_previsao
                        (data_key, modelo_key, receita_prevista)
                    VALUES
                        (:data_key, :modelo_key, :receita_prevista);
                """),
                {
                    "data_key": chave,
                    "modelo_key": modelo_key,
                    "receita_prevista": float(receita),
                },
            )


def main():
    print()
    print(
        "SABIN - MODELO PREDITIVO"
    )
    print()

    df = (
        carregar_receita_mensal()
    )

    print(
        f"Meses completos disponíveis: "
        f"{len(df)}"
    )

    print(
        f"Período utilizado: "
        f"{df['mes'].min().date()} "
        f"até "
        f"{df['mes'].max().date()}"
    )

    mes_corrente = (
        pd.Timestamp(
            obter_data_referencia_sql()
            or pd.Timestamp.today()
        )
        .to_period("M")
        .to_timestamp()
    )

    print(
        f"Mês corrente ignorado no treino: "
        f"{mes_corrente.strftime('%m/%Y')}"
    )

    dados_modelo = (
        criar_features(
            df
        )
    )

    mae, rmse, r2 = (
        avaliar_modelo(
            dados_modelo
        )
    )

    previsoes = (
        prever_proximos_meses(
            df,
            dados_modelo,
            quantidade=3,
        )
    )

    dados_powerbi = (
        preparar_dados_powerbi(
            df,
            previsoes,
        )
    )

    guardar_resultados(
        dados_powerbi,
        previsoes,
        mae,
        rmse,
        r2,
        df,
    )

    print()
    print("AVALIAÇÃO")

    print(
        f"MAE: {mae:.2f} €"
    )

    print(
        f"RMSE: {rmse:.2f} €"
    )

    print(
        f"R²: {r2:.4f}"
    )

    print()
    print("PREVISÕES")

    for _, linha in (
        previsoes.iterrows()
    ):
        print(
            f"{linha['mes'].strftime('%m/%Y')}: "
            f"{linha['receita_prevista']:.2f} €"
        )

    print()

    print(
        "Tabelas atualizadas:"
    )

    print(
        f"{DW_SCHEMA}.dim_modelo_previsao"
    )

    print(
        f"{DW_SCHEMA}.fact_previsao"
    )

    print()

    print(
        "Modelo preditivo executado "
        "com sucesso."
    )


if __name__ == "__main__":
    main()