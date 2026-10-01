import os

import pandas as pd

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL não encontrada "
        "no ficheiro .env"
    )


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


COLUNAS_ALERTAS = [
    "periodo",
    "nivel",
    "tipo",
    "mensagem",
    "variacao_percent",
]


def carregar_metricas():
    query = text("""
        SELECT *
        FROM dw.metricas_previsao;
    """)

    with engine.connect() as connection:
        df = pd.read_sql(
            query,
            connection,
        )

    if df.empty:
        raise ValueError(
            "Não existem métricas "
            "de previsão."
        )

    return df.iloc[0]


def carregar_previsoes():
    query = text("""
        SELECT
            mes,
            receita_prevista

        FROM dw.previsao_receita

        WHERE tipo = 'Previsão'

        ORDER BY mes;
    """)

    with engine.connect() as connection:
        df = pd.read_sql(
            query,
            connection,
        )

    if df.empty:
        raise ValueError(
            "Não existem previsões "
            "disponíveis."
        )

    df["mes"] = pd.to_datetime(
        df["mes"]
    )

    return df


def gerar_alertas(
    metricas,
    previsoes,
):
    alertas = []

    ultima_receita = float(
        metricas[
            "ultima_receita_real"
        ]
    )

    r2 = float(
        metricas["r2"]
    )

    primeiro_mes = (
        previsoes.iloc[0]
    )

    receita_prevista = float(
        primeiro_mes[
            "receita_prevista"
        ]
    )

    if ultima_receita > 0:
        variacao = (
            (
                receita_prevista
                - ultima_receita
            )
            / ultima_receita
            * 100
        )
    else:
        variacao = 0

    if variacao <= -20:
        alertas.append(
            {
                "periodo": (
                    primeiro_mes["mes"]
                ),
                "nivel": "Crítico",
                "tipo": "Receita",
                "mensagem": (
                    "Previsão de queda "
                    "acentuada da receita "
                    "no próximo mês."
                ),
                "variacao_percent": round(
                    variacao,
                    2,
                ),
            }
        )

    elif variacao < -5:
        alertas.append(
            {
                "periodo": (
                    primeiro_mes["mes"]
                ),
                "nivel": "Aviso",
                "tipo": "Receita",
                "mensagem": (
                    "Previsão de redução "
                    "da receita no próximo mês."
                ),
                "variacao_percent": round(
                    variacao,
                    2,
                ),
            }
        )

    elif variacao >= 5:
        alertas.append(
            {
                "periodo": (
                    primeiro_mes["mes"]
                ),
                "nivel": "Positivo",
                "tipo": "Receita",
                "mensagem": (
                    "Previsão de crescimento "
                    "da receita no próximo mês."
                ),
                "variacao_percent": round(
                    variacao,
                    2,
                ),
            }
        )

    if r2 < 0.60:
        alertas.append(
            {
                "periodo": (
                    primeiro_mes["mes"]
                ),
                "nivel": "Informação",
                "tipo": "Modelo",
                "mensagem": (
                    "O modelo apresenta "
                    "capacidade explicativa "
                    "moderada. As previsões "
                    "devem ser interpretadas "
                    "com cautela."
                ),
                "variacao_percent": None,
            }
        )

    for i in range(
        1,
        len(previsoes),
    ):
        anterior = float(
            previsoes.iloc[
                i - 1
            ][
                "receita_prevista"
            ]
        )

        atual = float(
            previsoes.iloc[
                i
            ][
                "receita_prevista"
            ]
        )

        if anterior <= 0:
            continue

        variacao_mes = (
            (
                atual
                - anterior
            )
            / anterior
            * 100
        )

        if variacao_mes >= 5:
            alertas.append(
                {
                    "periodo": (
                        previsoes.iloc[
                            i
                        ]["mes"]
                    ),
                    "nivel": "Positivo",
                    "tipo": "Tendência",
                    "mensagem": (
                        "Previsão de recuperação "
                        "da receita relativamente "
                        "ao mês anterior."
                    ),
                    "variacao_percent": round(
                        variacao_mes,
                        2,
                    ),
                }
            )

        elif variacao_mes <= -5:
            alertas.append(
                {
                    "periodo": (
                        previsoes.iloc[
                            i
                        ]["mes"]
                    ),
                    "nivel": "Aviso",
                    "tipo": "Tendência",
                    "mensagem": (
                        "Previsão de nova redução "
                        "da receita relativamente "
                        "ao mês anterior."
                    ),
                    "variacao_percent": round(
                        variacao_mes,
                        2,
                    ),
                }
            )

    return pd.DataFrame(
        alertas,
        columns=COLUNAS_ALERTAS,
    )


def guardar_alertas(
    alertas
):
    os.makedirs(
        "outputs",
        exist_ok=True,
    )

    alertas.to_csv(
        "outputs/alertas_previsao.csv",
        index=False,
        encoding="utf-8-sig",
    )

    alertas.to_sql(
        "alertas_previsao",
        engine,
        schema="dw",
        if_exists="replace",
        index=False,
    )


def main():
    print()
    print(
        "SABIN - ALERTAS PREDITIVOS"
    )
    print()

    metricas = (
        carregar_metricas()
    )

    previsoes = (
        carregar_previsoes()
    )

    alertas = gerar_alertas(
        metricas,
        previsoes,
    )

    guardar_alertas(
        alertas
    )

    print(
        f"Alertas gerados: "
        f"{len(alertas)}"
    )

    print()

    for _, alerta in (
        alertas.iterrows()
    ):
        print(
            f"[{alerta['nivel']}] "
            f"{alerta['periodo'].strftime('%m/%Y')} - "
            f"{alerta['mensagem']}"
        )

        if pd.notna(
            alerta[
                "variacao_percent"
            ]
        ):
            print(
                f"Variação: "
                f"{alerta['variacao_percent']:.2f}%"
            )

        print()

    print(
        "Tabela atualizada:"
    )

    print(
        "dw.alertas_previsao"
    )

    print()

    print(
        "Alertas gerados "
        "com sucesso."
    )


if __name__ == "__main__":
    main()