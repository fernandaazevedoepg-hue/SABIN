import os

import pandas as pd
from sqlalchemy import text

from etl.extract import DW_SCHEMA



def obter_data_referencia_sql():
    #data usada para análise
    data = os.getenv("SABIN_DATA_REFERENCIA")

    if data:
        return pd.Timestamp(data).date()

    return None


SQL_STOCK_ATUAL = f"""
    SELECT
        d.data AS data_referencia,
        l.livro_id_origem AS livro_id,
        l.titulo,
        l.isbn,
        f.preco_venda,
        f.estoque_atual,
        f.qtd_reservada,
        f.stock_disponivel,
        f.unidades_ultimos_3_meses,
        f.media_mensal_vendas,
        f.meses_cobertura,
        f.quantidade_recomendada,
        n.nivel,
        n.recomendacao,
        n.ordem AS ordem_nivel
    FROM {DW_SCHEMA}.fact_stock f
    JOIN {DW_SCHEMA}.dim_data d
        ON d.data_key = f.data_key
    JOIN {DW_SCHEMA}.dim_livro l
        ON l.livro_key = f.livro_key
    JOIN {DW_SCHEMA}.dim_nivel_stock n
        ON n.nivel_key = f.nivel_key
    WHERE f.data_key = (
        SELECT MAX(data_key)
        FROM {DW_SCHEMA}.fact_stock
    )
"""
"""Última fotografia de stock, com as colunas da antiga dw.alertas_stock."""


def _ler(engine, sql, params=None):
    with engine.connect() as connection:
        return pd.read_sql(
            text(sql),
            connection,
            params=params,
        )


def carregar_previsoes_modelo(engine):
    """Previsões do modelo mais recente (mês e receita prevista)."""
    return _ler(engine, f"""
        SELECT
            m.modelo_key,
            m.modelo,
            d.data AS mes,
            f.receita_prevista
        FROM {DW_SCHEMA}.fact_previsao f
        JOIN {DW_SCHEMA}.dim_data d
            ON d.data_key = f.data_key
        JOIN {DW_SCHEMA}.dim_modelo_previsao m
            ON m.modelo_key = f.modelo_key
        WHERE f.modelo_key = (
            SELECT MAX(modelo_key)
            FROM {DW_SCHEMA}.fact_previsao
        )
        ORDER BY d.data;
    """)


def carregar_receita_mensal_real(engine, antes_de):
    """Receita real de cada mês anterior a `antes_de`, a partir da fact_vendas."""
    dados = _ler(engine, f"""
        SELECT
            DATE_TRUNC('month', d.data)::date AS mes,
            ROUND(SUM(f.receita_atribuida), 2) AS receita
        FROM {DW_SCHEMA}.fact_vendas f
        JOIN {DW_SCHEMA}.dim_data d
            ON d.data_key = f.data_key
        WHERE d.data < :antes_de
        GROUP BY 1
        ORDER BY 1;
    """, {"antes_de": antes_de})

    dados["mes"] = pd.to_datetime(dados["mes"])
    dados["receita"] = pd.to_numeric(dados["receita"])

    return dados


def carregar_metricas_previsao(engine):
    """Métricas e resumo da previsão, no formato da antiga dw.metricas_previsao.

    Devolve None se ainda não existirem previsões.
    """
    previsoes = carregar_previsoes_modelo(engine)

    if previsoes.empty:
        return None

    modelo_key = int(previsoes.iloc[0]["modelo_key"])

    modelo = _ler(engine, f"""
        SELECT modelo, mae, rmse, r2
        FROM {DW_SCHEMA}.dim_modelo_previsao
        WHERE modelo_key = :modelo_key;
    """, {"modelo_key": modelo_key}).iloc[0]

    proximo_mes = pd.Timestamp(previsoes.iloc[0]["mes"])
    receita_prevista = float(previsoes.iloc[0]["receita_prevista"])

    historico = carregar_receita_mensal_real(
        engine,
        proximo_mes.date(),
    )

    if historico.empty:
        ultimo_mes_real = None
        ultima_receita = 0.0
    else:
        ultimo_mes_real = historico.iloc[-1]["mes"]
        ultima_receita = float(historico.iloc[-1]["receita"])

    if ultima_receita > 0:
        variacao = (
            (receita_prevista - ultima_receita)
            / ultima_receita
            * 100
        )
    else:
        variacao = 0

    if variacao > 5:
        tendencia = "Subida"
    elif variacao < -5:
        tendencia = "Descida"
    else:
        tendencia = "Estável"

    return {
        "modelo_key": modelo_key,
        "modelo": modelo["modelo"],
        "mae": float(modelo["mae"]) if pd.notna(modelo["mae"]) else None,
        "rmse": float(modelo["rmse"]) if pd.notna(modelo["rmse"]) else None,
        "r2": float(modelo["r2"]) if pd.notna(modelo["r2"]) else None,
        "ultimo_mes_real": ultimo_mes_real,
        "ultima_receita_real": round(ultima_receita, 2),
        "proximo_mes": proximo_mes,
        "receita_prevista_proximo_mes": round(receita_prevista, 2),
        "variacao_prevista_percent": round(variacao, 2),
        "tendencia": tendencia,
    }


def carregar_previsao_receita(engine):
    """Série histórica + ligação + previsão, no formato da antiga dw.previsao_receita."""
    colunas = ["mes", "receita_real", "receita_prevista", "tipo"]

    previsoes = carregar_previsoes_modelo(engine)

    if previsoes.empty:
        return pd.DataFrame(columns=colunas)

    previsoes["mes"] = pd.to_datetime(previsoes["mes"])
    previsoes["receita_prevista"] = pd.to_numeric(previsoes["receita_prevista"])

    historico = carregar_receita_mensal_real(
        engine,
        previsoes.iloc[0]["mes"].date(),
    )

    historico = historico.rename(columns={"receita": "receita_real"})
    historico["receita_prevista"] = float("nan")
    historico["tipo"] = "Histórico"

    partes = [historico[colunas]]

    if not historico.empty:
        ligacao = historico.tail(1).copy()
        ligacao["receita_prevista"] = ligacao["receita_real"]
        ligacao["tipo"] = "Ligação"
        partes.append(ligacao[colunas])

    futuro = previsoes[["mes", "receita_prevista"]].copy()
    futuro["receita_real"] = float("nan")
    futuro["tipo"] = "Previsão"
    partes.append(futuro[colunas])

    return pd.concat(partes, ignore_index=True)


SQL_ALERTAS_PREVISAO = f"""
    SELECT
        d.data AS periodo,
        a.nivel,
        a.tipo,
        a.mensagem,
        f.variacao_percent
    FROM {DW_SCHEMA}.fact_alerta_previsao f
    JOIN {DW_SCHEMA}.dim_data d
        ON d.data_key = f.data_key
    JOIN {DW_SCHEMA}.dim_alerta_previsao a
        ON a.alerta_key = f.alerta_key
    WHERE f.modelo_key = (
        SELECT MAX(modelo_key)
        FROM {DW_SCHEMA}.fact_alerta_previsao
    )
"""
"""Alertas de previsão, com as colunas da antiga dw.alertas_previsao."""


def data_key(data):
    """Chave da dim_data (AAAAMMDD) de uma data."""
    return int(pd.Timestamp(data).strftime("%Y%m%d"))


def verificar_datas(connection, chaves):
    """Confirma que as datas existem na dim_data antes de gravar um facto."""
    existentes = connection.execute(
        text(f"""
            SELECT data_key
            FROM {DW_SCHEMA}.dim_data
            WHERE data_key = ANY(:chaves);
        """),
        {"chaves": list(chaves)},
    ).scalars().all()

    em_falta = sorted(set(chaves) - set(existentes))

    if em_falta:
        raise ValueError(
            f"Datas sem correspondência na dim_data: {em_falta}. "
            "Execute primeiro o ETL (etl/load.py)."
        )
