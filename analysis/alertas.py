import os

import pandas as pd

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from analysis.dw_consultas import (
    DW_SCHEMA,
    carregar_metricas_previsao,
    carregar_previsoes_modelo,
    data_key,
    verificar_datas,
)


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
    """Carrega as métricas usadas para avaliar as previsões."""
    metricas = carregar_metricas_previsao(
        engine
    )

    if not metricas:
        raise ValueError(
            "Não existem métricas "
            "de previsão."
        )

    return pd.Series(metricas)


def carregar_previsoes():
    """Carrega a série de receitas previstas para análise."""
    df = carregar_previsoes_modelo(
        engine
    )[
        [
            "mes",
            "receita_prevista",
        ]
    ]

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
    """Gera alertas a partir da variação da receita e da qualidade do modelo."""
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
    alertas,
    modelo_key,
):
    """Guarda os alertas em CSV e na fact_alerta_previsao.

    Grão: mês do alerta x modelo x alerta. Cada combinação nível, tipo e
    mensagem é procurada na dim_alerta_previsao e acrescentada se for nova.
    Os alertas anteriores do mesmo modelo são substituídos numa única
    transação.
    """
    os.makedirs(
        "outputs",
        exist_ok=True,
    )

    alertas.to_csv(
        "outputs/alertas_previsao.csv",
        index=False,
        encoding="utf-8-sig",
    )

    with engine.begin() as connection:
        chaves_data = [
            data_key(periodo)
            for periodo in alertas["periodo"]
        ]

        verificar_datas(
            connection,
            chaves_data,
        )

        connection.execute(
            text(f"""
                DELETE FROM {DW_SCHEMA}.fact_alerta_previsao
                WHERE modelo_key = :modelo_key;
            """),
            {"modelo_key": modelo_key},
        )

        for chave, (_, alerta) in zip(
            chaves_data,
            alertas.iterrows(),
        ):
            alerta_key = obter_alerta_key(
                connection,
                alerta,
            )

            variacao = alerta["variacao_percent"]

            connection.execute(
                text(f"""
                    INSERT INTO {DW_SCHEMA}.fact_alerta_previsao
                        (data_key, modelo_key, alerta_key, variacao_percent)
                    VALUES
                        (:data_key, :modelo_key, :alerta_key, :variacao);
                """),
                {
                    "data_key": chave,
                    "modelo_key": modelo_key,
                    "alerta_key": alerta_key,
                    "variacao": (
                        float(variacao)
                        if pd.notna(variacao)
                        else None
                    ),
                },
            )


def obter_alerta_key(
    connection,
    alerta,
):
    """Devolve a chave do alerta na dim_alerta_previsao, criando-a se for novo."""
    parametros = {
        "nivel": alerta["nivel"],
        "tipo": alerta["tipo"],
        "mensagem": alerta["mensagem"],
    }

    connection.execute(
        text(f"""
            INSERT INTO {DW_SCHEMA}.dim_alerta_previsao
                (nivel, tipo, mensagem, ordem)
            SELECT
                :nivel,
                :tipo,
                :mensagem,
                COALESCE(MAX(ordem), 0) + 1
            FROM {DW_SCHEMA}.dim_alerta_previsao
            ON CONFLICT (nivel, tipo, mensagem) DO NOTHING;
        """),
        parametros,
    )

    return connection.execute(
        text(f"""
            SELECT alerta_key
            FROM {DW_SCHEMA}.dim_alerta_previsao
            WHERE nivel = :nivel
              AND tipo = :tipo
              AND mensagem = :mensagem;
        """),
        parametros,
    ).scalar_one()


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
        alertas,
        int(metricas["modelo_key"]),
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
        f"{DW_SCHEMA}.fact_alerta_previsao"
    )

    print()

    print(
        "Alertas gerados "
        "com sucesso."
    )


if __name__ == "__main__":
    main()