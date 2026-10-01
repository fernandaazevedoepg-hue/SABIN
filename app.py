import os
import re

import pandas as pd
import plotly.graph_objects as go

from dash import (
    Dash,
    html,
    dcc,
    Input,
    Output,
    State,
    ctx,
)

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from services.book_catalog import procurar_livro
from services.sales_service import (
    METODOS_PAGAMENTO,
    carregar_clientes,
    carregar_livros_disponiveis,
    obter_livro,
    registar_venda,
)
from services.etl_service import executar_atualizacao_analitica


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL não encontrada no ficheiro .env"
    )


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


# Formatação

def formatar_euro(valor):
    if valor is None or pd.isna(valor):
        return "—"

    return (
        f"{float(valor):,.2f} €"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", " ")
    )


def formatar_inteiro(valor):
    if valor is None or pd.isna(valor):
        return "—"

    return (
        f"{int(valor):,}"
        .replace(",", " ")
    )


def formatar_percentagem(valor):
    if valor is None or pd.isna(valor):
        return "—"

    return (
        f"{float(valor):.2f}%"
        .replace(".", ",")
    )


def formatar_mes(valor):
    if valor is None or pd.isna(valor):
        return "—"

    data = pd.to_datetime(valor)
    return data.strftime("%m/%Y")


# Visão Geral

def carregar_kpis():
    query = text("""
        SELECT
            COALESCE(SUM(subtotal), 0) AS receita_total,
            COUNT(DISTINCT venda_id_origem) AS numero_vendas,
            COALESCE(SUM(quantidade), 0) AS unidades_vendidas
        FROM dw.fact_vendas;
    """)

    with engine.connect() as connection:
        resultado = connection.execute(
            query
        ).mappings().one()

    receita_total = float(
        resultado["receita_total"]
    )

    numero_vendas = int(
        resultado["numero_vendas"]
    )

    unidades_vendidas = int(
        resultado["unidades_vendidas"]
    )

    if numero_vendas > 0:
        ticket_medio = receita_total / numero_vendas
    else:
        ticket_medio = 0

    return {
        "receita_total": receita_total,
        "numero_vendas": numero_vendas,
        "unidades_vendidas": unidades_vendidas,
        "ticket_medio": ticket_medio,
    }


def carregar_receita_mensal():
    query = text("""
        SELECT
            DATE_TRUNC('month', d.data)::date AS mes,
            SUM(f.subtotal) AS receita
        FROM dw.fact_vendas f
        JOIN dw.dim_data d
            ON d.data_key = f.data_key
        GROUP BY 1
        ORDER BY 1;
    """)

    with engine.connect() as connection:
        dados = pd.read_sql(
            query,
            connection,
        )

    dados["mes"] = pd.to_datetime(
        dados["mes"]
    )

    return dados


def carregar_top_livros():
    query = text("""
        SELECT
            l.titulo,
            SUM(f.quantidade) AS unidades_vendidas
        FROM dw.fact_vendas f
        JOIN dw.dim_livro l
            ON l.livro_key = f.livro_key
        GROUP BY l.titulo
        ORDER BY unidades_vendidas DESC
        LIMIT 5;
    """)

    with engine.connect() as connection:
        dados = pd.read_sql(
            query,
            connection,
        )

    return dados


# Catálogo

def carregar_catalogo_local():
    query = text("""
        SELECT
            l.id,
            l.titulo,
            l.isbn,
            l.editora,
            l.preco_venda,
            l.estoque_atual,
            l.qtd_reservada,
            GREATEST(
                l.estoque_atual - l.qtd_reservada,
                0
            ) AS stock_disponivel,
            COALESCE(
                (
                    SELECT STRING_AGG(
                        a.nome,
                        ', '
                        ORDER BY a.nome
                    )
                    FROM public.livro_autores la
                    JOIN public.autores a
                        ON a.id = la.autor_id
                    WHERE la.livro_id = l.id
                ),
                '—'
            ) AS autores,
            COALESCE(
                (
                    SELECT STRING_AGG(
                        g.nome,
                        ', '
                        ORDER BY g.nome
                    )
                    FROM public.livro_generos lg
                    JOIN public.generos g
                        ON g.id = lg.genero_id
                    WHERE lg.livro_id = l.id
                ),
                '—'
            ) AS generos
        FROM public.livros l
        ORDER BY l.titulo;
    """)

    with engine.connect() as connection:
        dados = pd.read_sql(
            query,
            connection,
        )

    return dados


def carregar_generos():
    query = text("""
        SELECT nome
        FROM public.generos
        ORDER BY nome;
    """)

    with engine.connect() as connection:
        dados = pd.read_sql(
            query,
            connection,
        )

    return dados["nome"].tolist()


def parece_isbn(valor):
    if not valor:
        return False

    isbn = re.sub(
        r"[^0-9Xx]",
        "",
        valor,
    )

    return len(isbn) in [10, 13]


# Previsões

def carregar_metricas_previsao():
    query = text("""
        SELECT *
        FROM dw.metricas_previsao
        LIMIT 1;
    """)

    with engine.connect() as connection:
        resultado = connection.execute(
            query
        ).mappings().first()

    if not resultado:
        return None

    return dict(resultado)


def carregar_previsao_receita():
    query = text("""
        SELECT
            mes,
            receita_real,
            receita_prevista,
            tipo
        FROM dw.previsao_receita
        ORDER BY mes;
    """)

    with engine.connect() as connection:
        dados = pd.read_sql(
            query,
            connection,
        )

    dados["mes"] = pd.to_datetime(
        dados["mes"]
    )

    return dados


def carregar_alertas_previsao():
    query = text("""
        SELECT
            periodo,
            nivel,
            tipo,
            mensagem,
            variacao_percent
        FROM dw.alertas_previsao
        ORDER BY
            periodo,
            CASE
                WHEN nivel = 'Crítico' THEN 1
                WHEN nivel = 'Aviso' THEN 2
                WHEN nivel = 'Informação' THEN 3
                WHEN nivel = 'Positivo' THEN 4
                ELSE 5
            END;
    """)

    with engine.connect() as connection:
        dados = pd.read_sql(
            query,
            connection,
        )

    dados["periodo"] = pd.to_datetime(
        dados["periodo"]
    )

    return dados


# Stock

def carregar_alertas_stock():
    query = text("""
        SELECT
            titulo,
            estoque_atual,
            qtd_reservada,
            stock_disponivel,
            unidades_ultimos_3_meses,
            media_mensal_vendas,
            meses_cobertura,
            quantidade_recomendada,
            nivel,
            recomendacao
        FROM dw.alertas_stock
        ORDER BY
            CASE
                WHEN nivel = 'Crítico' THEN 1
                WHEN nivel = 'Atenção' THEN 2
                WHEN nivel = 'Normal' THEN 3
                ELSE 4
            END,
            meses_cobertura;
    """)

    with engine.connect() as connection:
        dados = pd.read_sql(
            query,
            connection,
        )

    return dados


# Gráficos

def criar_grafico_receita_mensal(dados):
    figura = go.Figure()

    figura.add_trace(
        go.Scatter(
            x=dados["mes"],
            y=dados["receita"],
            mode="lines+markers",
            name="Receita",
            line={
                "color": "#2563eb",
                "width": 3,
            },
            marker={
                "size": 6,
            },
            hovertemplate=(
                "<b>%{x|%m/%Y}</b><br>"
                "Receita: %{y:.2f} €"
                "<extra></extra>"
            ),
        )
    )

    figura.update_layout(
        height=340,
        margin={
            "l": 20,
            "r": 20,
            "t": 10,
            "b": 20,
        },
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
        hovermode="x unified",
    )

    figura.update_xaxes(
        tickformat="%m/%Y",
        gridcolor="#e2e8f0",
    )

    figura.update_yaxes(
        title="Receita (€)",
        gridcolor="#e2e8f0",
    )

    return figura


def criar_grafico_top_livros(dados):
    dados = dados.sort_values(
        "unidades_vendidas",
        ascending=True,
    ).copy()

    dados["titulo_exibicao"] = (
        dados["titulo"]
        + "\u2003\u2003"
    )

    figura = go.Figure()

    figura.add_trace(
        go.Bar(
            x=dados["unidades_vendidas"],
            y=dados["titulo_exibicao"],
            orientation="h",
            marker={
                "color": "#2563eb",
            },
            hovertext=dados["titulo"],
            hovertemplate=(
                "<b>%{hovertext}</b><br>"
                "%{x} unidades"
                "<extra></extra>"
            ),
        )
    )

    figura.update_layout(
        height=340,
        margin={
            "l": 45,
            "r": 20,
            "t": 10,
            "b": 20,
        },
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
        bargap=0.25,
    )

    figura.update_xaxes(
        title="Unidades Vendidas",
        gridcolor="#e2e8f0",
        zeroline=False,
    )

    figura.update_yaxes(
        title="",
        automargin=True,
    )

    return figura


def criar_grafico_previsao(dados):
    historico = dados[
        (
            dados["tipo"] == "Histórico"
        )
        & dados["receita_real"].notna()
    ]

    previsao = dados[
        dados["receita_prevista"].notna()
    ]

    figura = go.Figure()

    figura.add_trace(
        go.Scatter(
            x=historico["mes"],
            y=historico["receita_real"],
            mode="lines",
            name="Receita Histórica",
            line={
                "color": "#2563eb",
                "width": 3,
            },
        )
    )

    figura.add_trace(
        go.Scatter(
            x=previsao["mes"],
            y=previsao["receita_prevista"],
            mode="lines+markers",
            name="Receita Prevista",
            line={
                "color": "#14b8a6",
                "width": 3,
                "dash": "dot",
            },
            marker={
                "size": 7,
            },
        )
    )

    figura.update_layout(
        height=390,
        margin={
            "l": 20,
            "r": 20,
            "t": 10,
            "b": 20,
        },
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="x unified",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
    )

    figura.update_xaxes(
        tickformat="%m/%Y",
        gridcolor="#e2e8f0",
    )

    figura.update_yaxes(
        title="Receita (€)",
        gridcolor="#e2e8f0",
    )

    return figura


def criar_grafico_stock(dados):
    cores = {
        "Crítico": "#dc2626",
        "Atenção": "#f59e0b",
        "Normal": "#16a34a",
        "Sem procura recente": "#94a3b8",
    }

    figura = go.Figure()

    for nivel in dados["nivel"].unique():
        grupo = dados[
            dados["nivel"] == nivel
        ]

        figura.add_trace(
            go.Scatter(
                x=grupo["media_mensal_vendas"],
                y=grupo["stock_disponivel"],
                mode="markers",
                name=nivel,
                text=grupo["titulo"],
                marker={
                    "size": 10,
                    "color": cores.get(
                        nivel,
                        "#64748b",
                    ),
                },
                customdata=grupo[
                    [
                        "meses_cobertura",
                        "quantidade_recomendada",
                    ]
                ],
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Média mensal: %{x:.2f}<br>"
                    "Stock disponível: %{y}<br>"
                    "Cobertura: %{customdata[0]:.2f} meses<br>"
                    "Repor: %{customdata[1]} unidades"
                    "<extra></extra>"
                ),
            )
        )

    figura.update_layout(
        height=390,
        margin={
            "l": 20,
            "r": 20,
            "t": 10,
            "b": 20,
        },
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
    )

    figura.update_xaxes(
        title="Média Mensal de Vendas",
        gridcolor="#e2e8f0",
    )

    figura.update_yaxes(
        title="Stock Disponível",
        gridcolor="#e2e8f0",
    )

    return figura


# Tabelas e componentes

def criar_tabela_catalogo(dados):
    if dados.empty:
        return html.Div(
            "Nenhum livro encontrado no catálogo da Bookmarked.",
            className="empty-message",
        )

    linhas = []

    for _, livro in dados.iterrows():
        linhas.append(
            html.Tr(
                children=[
                    html.Td(
                        livro["titulo"],
                        className="book-title-cell",
                    ),
                    html.Td(
                        livro["autores"]
                    ),
                    html.Td(
                        livro["generos"]
                    ),
                    html.Td(
                        livro["isbn"]
                    ),
                    html.Td(
                        livro["editora"]
                        if livro["editora"]
                        else "—"
                    ),
                    html.Td(
                        formatar_euro(
                            livro["preco_venda"]
                        )
                    ),
                    html.Td(
                        int(
                            livro["stock_disponivel"]
                        )
                    ),
                ]
            )
        )

    return html.Div(
        className="catalog-table-wrapper",
        children=[
            html.Table(
                className="catalog-table",
                children=[
                    html.Thead(
                        html.Tr(
                            children=[
                                html.Th("Título"),
                                html.Th("Autor"),
                                html.Th("Género"),
                                html.Th("ISBN"),
                                html.Th("Editora"),
                                html.Th("Preço"),
                                html.Th("Disponível"),
                            ]
                        )
                    ),
                    html.Tbody(
                        linhas
                    ),
                ]
            )
        ],
    )


def criar_resultado_externo(
    resultado,
    autores,
):
    return html.Div(
        className="external-result-card",
        children=[
            html.Div(
                className="external-result-header",
                children=[
                    html.Div(
                        children=[
                            html.P(
                                "Livro não encontrado no catálogo local",
                                className="external-result-label",
                            ),
                            html.H3(
                                resultado.get(
                                    "titulo",
                                    "Sem título",
                                )
                            ),
                        ]
                    ),
                    html.Span(
                        "Open Library API",
                        className="origin-badge api",
                    ),
                ],
            ),
            html.Div(
                className="result-grid",
                children=[
                    html.Div(
                        className="result-item",
                        children=[
                            html.Span("ISBN"),
                            html.Strong(
                                resultado.get(
                                    "isbn",
                                    "—",
                                )
                            ),
                        ],
                    ),
                    html.Div(
                        className="result-item",
                        children=[
                            html.Span("Autor"),
                            html.Strong(
                                autores
                            ),
                        ],
                    ),
                    html.Div(
                        className="result-item",
                        children=[
                            html.Span("Editora"),
                            html.Strong(
                                resultado.get(
                                    "editora"
                                )
                                or "—"
                            ),
                        ],
                    ),
                    html.Div(
                        className="result-item",
                        children=[
                            html.Span("Data de Publicação"),
                            html.Strong(
                                str(
                                    resultado.get(
                                        "data_publicacao"
                                    )
                                    or "—"
                                )
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def criar_tabela_alertas(dados):
    linhas = []

    for _, alerta in dados.iterrows():
        nivel = alerta["nivel"]
        classe = "info"

        if nivel == "Crítico":
            classe = "critical"
        elif nivel == "Aviso":
            classe = "warning"
        elif nivel == "Positivo":
            classe = "positive"

        linhas.append(
            html.Tr(
                children=[
                    html.Td(
                        html.Span(
                            nivel,
                            className=(
                                "alert-badge "
                                + classe
                            ),
                        )
                    ),
                    html.Td(
                        formatar_mes(
                            alerta["periodo"]
                        )
                    ),
                    html.Td(
                        alerta["tipo"]
                    ),
                    html.Td(
                        alerta["mensagem"]
                    ),
                    html.Td(
                        formatar_percentagem(
                            alerta["variacao_percent"]
                        )
                    ),
                ]
            )
        )

    return html.Div(
        className="alert-table-wrapper",
        children=[
            html.Table(
                className="alert-table",
                children=[
                    html.Thead(
                        html.Tr(
                            children=[
                                html.Th("Nível"),
                                html.Th("Período"),
                                html.Th("Tipo"),
                                html.Th("Mensagem"),
                                html.Th("Variação"),
                            ]
                        )
                    ),
                    html.Tbody(
                        linhas
                    ),
                ]
            )
        ],
    )


def criar_tabela_stock(dados):
    alertas = dados[
        dados["nivel"].isin(
            [
                "Crítico",
                "Atenção",
            ]
        )
    ]

    linhas = []

    for _, livro in alertas.iterrows():
        if livro["nivel"] == "Crítico":
            classe = "critical"
        else:
            classe = "warning"

        linhas.append(
            html.Tr(
                children=[
                    html.Td(
                        livro["titulo"]
                    ),
                    html.Td(
                        html.Span(
                            livro["nivel"],
                            className=(
                                "alert-badge "
                                + classe
                            ),
                        )
                    ),
                    html.Td(
                        int(
                            livro["stock_disponivel"]
                        )
                    ),
                    html.Td(
                        (
                            f"{livro['meses_cobertura']:.2f}"
                        ).replace(
                            ".",
                            ",",
                        )
                    ),
                    html.Td(
                        int(
                            livro["quantidade_recomendada"]
                        )
                    ),
                ]
            )
        )

    return html.Div(
        className="stock-table-wrapper",
        children=[
            html.Table(
                className="stock-table",
                children=[
                    html.Thead(
                        html.Tr(
                            children=[
                                html.Th("Livro"),
                                html.Th("Nível"),
                                html.Th("Stock"),
                                html.Th("Cobertura"),
                                html.Th("Repor"),
                            ]
                        )
                    ),
                    html.Tbody(
                        linhas
                    ),
                ]
            )
        ],
    )


def criar_tabela_carrinho(carrinho):
    if not carrinho:
        return html.Div(
            "Ainda não adicionaste livros à venda.",
            className="empty-cart",
        )

    linhas = []

    for item in carrinho:
        linhas.append(
            html.Tr(
                children=[
                    html.Td(
                        item["titulo"],
                        className="sale-book-title",
                    ),
                    html.Td(
                        str(item["quantidade"])
                    ),
                    html.Td(
                        formatar_euro(
                            item["preco"]
                        )
                    ),
                    html.Td(
                        formatar_euro(
                            item["subtotal"]
                        )
                    ),
                ]
            )
        )

    return html.Table(
        className="sale-cart-table",
        children=[
            html.Thead(
                html.Tr(
                    children=[
                        html.Th("Livro"),
                        html.Th("Qtd."),
                        html.Th("Preço"),
                        html.Th("Subtotal"),
                    ]
                )
            ),
            html.Tbody(
                linhas
            ),
        ],
    )


# Sidebar

def criar_sidebar():
    return html.Div(
        className="sidebar",
        children=[
            html.Div(
                children=[
                    html.H1("SABIN"),
                    html.P(
                        "Business Intelligence",
                        className="sidebar-subtitle",
                    ),
                ]
            ),
            html.Div(
                className="menu",
                children=[
                    html.Button(
                        "Visão Geral",
                        id="btn-visao-geral",
                        className="menu-button active",
                    ),
                    html.Button(
                        "Registar Venda",
                        id="btn-venda",
                        className="menu-button",
                    ),
                    html.Button(
                        "Catálogo",
                        id="btn-catalogo",
                        className="menu-button",
                    ),
                    html.Button(
                        "Previsões",
                        id="btn-previsoes",
                        className="menu-button",
                    ),
                    html.Button(
                        "Stock e Reposição",
                        id="btn-stock",
                        className="menu-button",
                    ),
                ],
            ),
            html.Div(
                className="sidebar-footer",
                children=[
                    html.P("Bookmarked"),
                    html.Small(
                        "Sistema de apoio à decisão"
                    ),
                ],
            ),
        ],
    )


# Página Visão Geral

def pagina_visao_geral():
    kpis = carregar_kpis()
    receita_mensal = carregar_receita_mensal()
    top_livros = carregar_top_livros()
    metricas = carregar_metricas_previsao()
    stock = carregar_alertas_stock()
    alertas_previsao = carregar_alertas_previsao()

    grafico_receita = criar_grafico_receita_mensal(
        receita_mensal
    )

    grafico_top = criar_grafico_top_livros(
        top_livros
    )

    criticos_stock = len(
        stock[
            stock["nivel"] == "Crítico"
        ]
    )

    atencao_stock = len(
        stock[
            stock["nivel"] == "Atenção"
        ]
    )

    alerta_critico = alertas_previsao[
        alertas_previsao["nivel"] == "Crítico"
    ]

    mensagem_previsao = "Sem alertas críticos."

    if not alerta_critico.empty:
        mensagem_previsao = (
            alerta_critico.iloc[0]["mensagem"]
        )

    return html.Div(
        children=[
            html.Div(
                className="page-header",
                children=[
                    html.H2("Visão Geral"),
                    html.P(
                        "Resumo do desempenho atual da livraria Bookmarked"
                    ),
                ],
            ),
            html.Div(
                className="cards",
                children=[
                    html.Div(
                        className="card",
                        children=[
                            html.P("Receita Total"),
                            html.H3(
                                formatar_euro(
                                    kpis["receita_total"]
                                )
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P("Número de Vendas"),
                            html.H3(
                                formatar_inteiro(
                                    kpis["numero_vendas"]
                                )
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P("Unidades Vendidas"),
                            html.H3(
                                formatar_inteiro(
                                    kpis["unidades_vendidas"]
                                )
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P("Ticket Médio"),
                            html.H3(
                                formatar_euro(
                                    kpis["ticket_medio"]
                                )
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="overview-charts",
                children=[
                    html.Div(
                        className="chart-panel",
                        children=[
                            html.H3(
                                "Evolução Mensal da Receita"
                            ),
                            dcc.Graph(
                                figure=grafico_receita,
                                config={
                                    "displayModeBar": False,
                                },
                            ),
                        ],
                    ),
                    html.Div(
                        className="chart-panel",
                        children=[
                            html.H3(
                                "Top 5 Livros Mais Vendidos"
                            ),
                            dcc.Graph(
                                figure=grafico_top,
                                config={
                                    "displayModeBar": False,
                                },
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="overview-bottom",
                children=[
                    html.Div(
                        className="business-panel",
                        children=[
                            html.H3("Situação Atual"),
                            html.Div(
                                className="business-grid",
                                children=[
                                    html.Div(
                                        className="business-item",
                                        children=[
                                            html.Span(
                                                "Último mês observado"
                                            ),
                                            html.Strong(
                                                formatar_mes(
                                                    metricas["ultimo_mes_real"]
                                                )
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="business-item",
                                        children=[
                                            html.Span(
                                                "Receita do último mês"
                                            ),
                                            html.Strong(
                                                formatar_euro(
                                                    metricas["ultima_receita_real"]
                                                )
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="business-item",
                                        children=[
                                            html.Span(
                                                "Próximo período"
                                            ),
                                            html.Strong(
                                                formatar_mes(
                                                    metricas["proximo_mes"]
                                                )
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="business-item",
                                        children=[
                                            html.Span(
                                                "Receita prevista"
                                            ),
                                            html.Strong(
                                                formatar_euro(
                                                    metricas["receita_prevista_proximo_mes"]
                                                )
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="variation-box",
                                children=[
                                    html.Span(
                                        "Variação prevista"
                                    ),
                                    html.Strong(
                                        formatar_percentagem(
                                            metricas["variacao_prevista_percent"]
                                        ),
                                        className=(
                                            "value-negative"
                                            if float(
                                                metricas["variacao_prevista_percent"]
                                            ) < 0
                                            else "value-positive"
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="business-panel",
                        children=[
                            html.H3("Alertas Recentes"),
                            html.Div(
                                className=(
                                    "overview-alert "
                                    "critical-overview"
                                ),
                                children=[
                                    html.Span("Stock crítico"),
                                    html.Strong(
                                        f"{criticos_stock} livro(s)"
                                    ),
                                ],
                            ),
                            html.Div(
                                className=(
                                    "overview-alert "
                                    "warning-overview"
                                ),
                                children=[
                                    html.Span("Stock em atenção"),
                                    html.Strong(
                                        f"{atencao_stock} livro(s)"
                                    ),
                                ],
                            ),
                            html.Div(
                                className=(
                                    "overview-alert "
                                    "info-overview"
                                ),
                                children=[
                                    html.Span("Previsão"),
                                    html.Strong(
                                        mensagem_previsao
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ]
    )


# Página Registar Venda

def pagina_registar_venda():
    clientes = carregar_clientes()
    livros = carregar_livros_disponiveis()

    opcoes_clientes = [
        {
            "label": "Venda ao balcão — cliente não identificado",
            "value": "balcao",
        }
    ]

    for cliente in clientes:
        opcoes_clientes.append(
            {
                "label": (
                    f"{cliente['nome_completo']} — "
                    f"NIF {cliente['nif']}"
                ),
                "value": cliente["id"],
            }
        )

    opcoes_livros = []

    for livro in livros:
        opcoes_livros.append(
            {
                "label": (
                    f"{livro['titulo']} — "
                    f"{formatar_euro(livro['preco_venda'])} — "
                    f"{livro['stock_disponivel']} disponíveis"
                ),
                "value": livro["id"],
            }
        )

    opcoes_pagamento = [
        {
            "label": metodo,
            "value": metodo,
        }
        for metodo in METODOS_PAGAMENTO
    ]

    return html.Div(
        children=[
            dcc.Store(
                id="sale-cart-store",
                data=[],
            ),
            html.Div(
                className="page-header",
                children=[
                    html.H2("Registar Venda"),
                    html.P(
                        "Registo de uma nova venda na base operacional da Bookmarked"
                    ),
                ],
            ),
            html.Div(
                className="sale-info-banner",
                children=[
                    html.Strong("Importante: "),
                    html.Span(
                        "a venda é gravada na base operacional. "
                        "Os indicadores do Data Warehouse só mudam depois "
                        "de executar novamente o processo ETL."
                    ),
                ],
            ),
            html.Div(
                className="sale-layout",
                children=[
                    html.Div(
                        className="sale-form-panel",
                        children=[
                            html.H3("Dados da Venda"),
                            html.Label(
                                "Cliente",
                                className="form-label",
                            ),
                            dcc.Dropdown(
                                id="sale-client",
                                options=opcoes_clientes,
                                value="balcao",
                                clearable=False,
                                searchable=True,
                                className="sale-dropdown",
                            ),
                            html.Label(
                                "Livro",
                                className="form-label",
                            ),
                            dcc.Dropdown(
                                id="sale-book",
                                options=opcoes_livros,
                                placeholder="Seleciona um livro...",
                                clearable=True,
                                searchable=True,
                                className="sale-dropdown",
                            ),
                            html.Div(
                                id="sale-book-info",
                                className="sale-book-info",
                            ),
                            html.Label(
                                "Quantidade",
                                className="form-label",
                            ),
                            dcc.Input(
                                id="sale-quantity",
                                type="number",
                                value=1,
                                min=1,
                                step=1,
                                className="sale-number-input",
                            ),
                            html.Button(
                                "Adicionar ao Carrinho",
                                id="sale-add-item",
                                className="primary-button sale-add-button",
                            ),
                            html.Div(
                                id="sale-item-message",
                            ),
                            html.Div(
                                className="sale-payment-section",
                                children=[
                                    html.Label(
                                        "Método de Pagamento",
                                        className="form-label",
                                    ),
                                    dcc.Dropdown(
                                        id="sale-payment",
                                        options=opcoes_pagamento,
                                        value="Multibanco",
                                        clearable=False,
                                        className="sale-dropdown",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="sale-cart-panel",
                        children=[
                            html.Div(
                                className="sale-cart-header",
                                children=[
                                    html.Div(
                                        children=[
                                            html.H3("Carrinho"),
                                            html.P(
                                                "Confirma os livros antes de finalizar a venda."
                                            ),
                                        ]
                                    ),
                                    html.Button(
                                        "Limpar",
                                        id="sale-clear-cart",
                                        className="secondary-button",
                                    ),
                                ],
                            ),
                            html.Div(
                                id="sale-cart-container",
                                children=criar_tabela_carrinho([]),
                            ),
                            html.Div(
                                className="sale-total-box",
                                children=[
                                    html.Span("Total da Venda"),
                                    html.Strong(
                                        id="sale-total",
                                        children="0,00 €",
                                    ),
                                ],
                            ),
                            html.Button(
                                "Registar Venda",
                                id="sale-submit",
                                className="primary-button sale-submit-button",
                            ),
                            html.Div(
                                id="sale-final-message",
                            ),
                        ],
                    ),
                ],
            ),
        ]
    )


# Página Catálogo

def pagina_catalogo():
    catalogo = carregar_catalogo_local()
    generos = carregar_generos()

    opcoes_generos = [
        {
            "label": "Todos os géneros",
            "value": "todos",
        }
    ]

    for genero in generos:
        opcoes_generos.append(
            {
                "label": genero,
                "value": genero,
            }
        )

    return html.Div(
        children=[
            html.Div(
                className="page-header",
                children=[
                    html.H2("Catálogo"),
                    html.P(
                        "Consulta e pesquisa dos livros disponíveis na Bookmarked"
                    ),
                ],
            ),
            html.Div(
                className="catalog-local-panel",
                children=[
                    html.Div(
                        className="catalog-section-header",
                        children=[
                            html.Div(
                                children=[
                                    html.H3(
                                        "Catálogo da Bookmarked"
                                    ),
                                    html.P(
                                        "Pesquisa por título, autor ou ISBN e filtra por género."
                                    ),
                                ]
                            ),
                            html.Div(
                                id="catalog-count",
                                className="catalog-count",
                                children=(
                                    f"{len(catalogo)} livros encontrados"
                                ),
                            ),
                        ],
                    ),
                    html.Div(
                        className="catalog-search-row",
                        children=[
                            dcc.Input(
                                id="catalog-search",
                                type="text",
                                placeholder=(
                                    "Pesquisar por título, autor ou ISBN..."
                                ),
                                className="catalog-search-input",
                                debounce=False,
                            ),
                            dcc.Dropdown(
                                id="catalog-genre",
                                options=opcoes_generos,
                                value="todos",
                                clearable=False,
                                searchable=True,
                                className="catalog-genre-dropdown",
                            ),
                            html.Button(
                                "Pesquisar",
                                id="catalog-search-button",
                                className=(
                                    "primary-button "
                                    "catalog-button"
                                ),
                            ),
                        ],
                    ),
                    html.Div(
                        id="catalog-api-message"
                    ),
                    html.Div(
                        id="catalog-table-container",
                        children=criar_tabela_catalogo(
                            catalogo
                        ),
                    ),
                ],
            ),
        ]
    )


# Página Previsões

def pagina_previsoes():
    metricas = carregar_metricas_previsao()
    previsao = carregar_previsao_receita()
    alertas = carregar_alertas_previsao()

    tendencia = metricas["tendencia"]
    variacao = metricas["variacao_prevista_percent"]

    figura = criar_grafico_previsao(
        previsao
    )

    return html.Div(
        children=[
            html.Div(
                className="page-header",
                children=[
                    html.H2("Previsões"),
                    html.P(
                        "Previsão da receita e identificação automática de situações relevantes"
                    ),
                ],
            ),
            html.Div(
                className="cards",
                children=[
                    html.Div(
                        className="card",
                        children=[
                            html.P("Próximo Período"),
                            html.H3(
                                formatar_mes(
                                    metricas["proximo_mes"]
                                )
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P("Receita Prevista"),
                            html.H3(
                                formatar_euro(
                                    metricas["receita_prevista_proximo_mes"]
                                )
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P("Tendência"),
                            html.H3(
                                tendencia,
                                className=(
                                    "value-negative"
                                    if tendencia == "Descida"
                                    else "value-positive"
                                ),
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P("Variação Prevista"),
                            html.H3(
                                formatar_percentagem(
                                    variacao
                                ),
                                className=(
                                    "value-negative"
                                    if float(variacao) < 0
                                    else "value-positive"
                                ),
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="forecast-grid",
                children=[
                    html.Div(
                        className="chart-panel",
                        children=[
                            html.H3(
                                "Receita Histórica e Previsão"
                            ),
                            dcc.Graph(
                                figure=figura,
                                config={
                                    "displayModeBar": False,
                                },
                            ),
                        ],
                    ),
                    html.Div(
                        className="model-panel",
                        children=[
                            html.H3("Resumo do Modelo"),
                            html.Div(
                                className="model-grid",
                                children=[
                                    html.Div(
                                        className="model-item",
                                        children=[
                                            html.Span("Modelo"),
                                            html.Strong(
                                                metricas["modelo"]
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="model-item",
                                        children=[
                                            html.Span(
                                                "Erro Médio (MAE)"
                                            ),
                                            html.Strong(
                                                formatar_euro(
                                                    metricas["mae"]
                                                )
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="model-item",
                                        children=[
                                            html.Span("RMSE"),
                                            html.Strong(
                                                formatar_euro(
                                                    metricas["rmse"]
                                                )
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="model-item",
                                        children=[
                                            html.Span("R² do Modelo"),
                                            html.Strong(
                                                formatar_percentagem(
                                                    float(
                                                        metricas["r2"]
                                                    )
                                                    * 100
                                                )
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.P(
                                "O R² representa a capacidade explicativa do modelo e não uma percentagem de acerto.",
                                className="model-note",
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="alert-panel",
                children=[
                    html.H3("Alertas Preditivos"),
                    criar_tabela_alertas(
                        alertas
                    ),
                ],
            ),
        ]
    )


# Página Stock

def pagina_stock():
    dados = carregar_alertas_stock()

    total_livros = len(dados)

    criticos = len(
        dados[
            dados["nivel"] == "Crítico"
        ]
    )

    atencao = len(
        dados[
            dados["nivel"] == "Atenção"
        ]
    )

    unidades_repor = int(
        dados["quantidade_recomendada"].sum()
    )

    figura = criar_grafico_stock(
        dados
    )

    return html.Div(
        children=[
            html.Div(
                className="page-header",
                children=[
                    html.H2("Stock e Reposição"),
                    html.P(
                        "Monitorização da cobertura de stock e identificação de necessidades de reposição"
                    ),
                ],
            ),
            html.Div(
                className="cards",
                children=[
                    html.Div(
                        className="card",
                        children=[
                            html.P("Livros Analisados"),
                            html.H3(
                                str(total_livros)
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P("Críticos"),
                            html.H3(
                                str(criticos),
                                className="value-negative",
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P("Atenção"),
                            html.H3(
                                str(atencao),
                                className="value-warning",
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P("Unidades a Repor"),
                            html.H3(
                                str(unidades_repor)
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="stock-grid",
                children=[
                    html.Div(
                        className="chart-panel",
                        children=[
                            html.H3(
                                "Procura Mensal vs Stock Disponível"
                            ),
                            dcc.Graph(
                                figure=figura,
                                config={
                                    "displayModeBar": False,
                                },
                            ),
                        ],
                    ),
                    html.Div(
                        className="stock-side",
                        children=[
                            html.Div(
                                className="stock-alert-panel",
                                children=[
                                    html.H3(
                                        "Alertas de Reposição"
                                    ),
                                    criar_tabela_stock(
                                        dados
                                    ),
                                ],
                            ),
                            html.Div(
                                className="criteria-panel",
                                children=[
                                    html.H3(
                                        "Critérios de Alerta"
                                    ),
                                    html.Div(
                                        className="criteria-item",
                                        children=[
                                            html.Span(
                                                "Crítico",
                                                className="criteria-critical",
                                            ),
                                            html.Strong(
                                                "Menos de 1 mês de cobertura"
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="criteria-item",
                                        children=[
                                            html.Span(
                                                "Atenção",
                                                className="criteria-warning",
                                            ),
                                            html.Strong(
                                                "Entre 1 e 2 meses de cobertura"
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="criteria-item",
                                        children=[
                                            html.Span(
                                                "Normal",
                                                className="criteria-normal",
                                            ),
                                            html.Strong(
                                                "2 ou mais meses de cobertura"
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ]
    )


# Aplicação

app = Dash(
    __name__,
    suppress_callback_exceptions=True,
)

app.title = "SABIN"


app.layout = html.Div(
    className="app",
    children=[
        criar_sidebar(),
        html.Main(
            id="page-content",
            className="content",
            children=pagina_visao_geral(),
        ),
    ],
)


# Navegação

@app.callback(
    Output("page-content", "children"),
    Output("btn-visao-geral", "className"),
    Output("btn-venda", "className"),
    Output("btn-catalogo", "className"),
    Output("btn-previsoes", "className"),
    Output("btn-stock", "className"),
    Input("btn-visao-geral", "n_clicks"),
    Input("btn-venda", "n_clicks"),
    Input("btn-catalogo", "n_clicks"),
    Input("btn-previsoes", "n_clicks"),
    Input("btn-stock", "n_clicks"),
)
def navegar(
    visao,
    venda,
    catalogo,
    previsoes,
    stock,
):
    botao = ctx.triggered_id

    normal = "menu-button"
    ativo = "menu-button active"

    if botao == "btn-venda":
        return (
            pagina_registar_venda(),
            normal,
            ativo,
            normal,
            normal,
            normal,
        )

    if botao == "btn-catalogo":
        return (
            pagina_catalogo(),
            normal,
            normal,
            ativo,
            normal,
            normal,
        )

    if botao == "btn-previsoes":
        return (
            pagina_previsoes(),
            normal,
            normal,
            normal,
            ativo,
            normal,
        )

    if botao == "btn-stock":
        return (
            pagina_stock(),
            normal,
            normal,
            normal,
            normal,
            ativo,
        )

    return (
        pagina_visao_geral(),
        ativo,
        normal,
        normal,
        normal,
        normal,
    )


# Catálogo

@app.callback(
    Output("catalog-count", "children"),
    Output("catalog-table-container", "children"),
    Output("catalog-api-message", "children"),
    Input("catalog-search", "value"),
    Input("catalog-genre", "value"),
    Input("catalog-search-button", "n_clicks"),
)
def pesquisar_catalogo(
    pesquisa,
    genero,
    n_clicks,
):
    dados = carregar_catalogo_local()
    dados_filtrados = dados.copy()

    if genero and genero != "todos":
        dados_filtrados = dados_filtrados[
            dados_filtrados["generos"]
            .fillna("")
            .str.lower()
            .str.contains(
                genero.lower(),
                regex=False,
            )
        ]

    termo = ""

    if pesquisa:
        termo = pesquisa.strip().lower()

    if termo:
        mascara = (
            dados_filtrados["titulo"]
            .fillna("")
            .str.lower()
            .str.contains(
                termo,
                regex=False,
            )
            |
            dados_filtrados["isbn"]
            .fillna("")
            .astype(str)
            .str.lower()
            .str.contains(
                termo,
                regex=False,
            )
            |
            dados_filtrados["autores"]
            .fillna("")
            .str.lower()
            .str.contains(
                termo,
                regex=False,
            )
        )

        dados_filtrados = dados_filtrados[
            mascara
        ]

    quantidade = len(
        dados_filtrados
    )

    texto_contagem = (
        f"{quantidade} "
        f"{'livro encontrado' if quantidade == 1 else 'livros encontrados'}"
    )

    resultado_api = ""

    if (
        ctx.triggered_id == "catalog-search-button"
        and termo
        and quantidade == 0
        and parece_isbn(pesquisa)
    ):
        resultado = procurar_livro(
            pesquisa.strip()
        )

        if resultado.get("sucesso"):
            origem = resultado.get("origem")

            if origem == "Open Library API":
                autores = resultado.get("autores")

                if isinstance(autores, list):
                    autores = ", ".join(autores)

                if not autores:
                    autores = "—"

                resultado_api = criar_resultado_externo(
                    resultado,
                    autores,
                )

                texto_contagem = (
                    "0 livros encontrados no catálogo local"
                )
        else:
            resultado_api = html.Div(
                resultado.get(
                    "erro",
                    "ISBN não encontrado no catálogo local nem na Open Library.",
                ),
                className="error-message",
            )

    return (
        texto_contagem,
        criar_tabela_catalogo(
            dados_filtrados
        ),
        resultado_api,
    )


# Informação do livro selecionado na venda

@app.callback(
    Output("sale-book-info", "children"),
    Input("sale-book", "value"),
)
def atualizar_info_livro_venda(
    livro_id,
):
    if not livro_id:
        return ""

    livro = obter_livro(
        livro_id
    )

    if not livro:
        return html.Div(
            "Livro não encontrado.",
            className="sale-error-message",
        )

    return html.Div(
        className="sale-book-summary",
        children=[
            html.Div(
                children=[
                    html.Span("Preço unitário"),
                    html.Strong(
                        formatar_euro(
                            livro["preco_venda"]
                        )
                    ),
                ]
            ),
            html.Div(
                children=[
                    html.Span("Stock disponível"),
                    html.Strong(
                        str(
                            livro["stock_disponivel"]
                        )
                    ),
                ]
            ),
            html.Div(
                children=[
                    html.Span("ISBN"),
                    html.Strong(
                        livro["isbn"]
                    ),
                ]
            ),
        ],
    )


# Carrinho e registo de venda

@app.callback(
    Output("sale-cart-store", "data"),
    Output("sale-item-message", "children"),
    Output("sale-final-message", "children"),
    Input("sale-add-item", "n_clicks"),
    Input("sale-clear-cart", "n_clicks"),
    Input("sale-submit", "n_clicks"),
    State("sale-book", "value"),
    State("sale-quantity", "value"),
    State("sale-client", "value"),
    State("sale-payment", "value"),
    State("sale-cart-store", "data"),
    prevent_initial_call=True,
)
def gerir_venda(
    adicionar,
    limpar,
    registar,
    livro_id,
    quantidade,
    cliente_id,
    metodo_pagamento,
    carrinho,
):
    carrinho = carrinho or []
    acao = ctx.triggered_id

    if acao == "sale-clear-cart":
        return (
            [],
            "",
            html.Div(
                "Carrinho limpo.",
                className="sale-neutral-message",
            ),
        )

    if acao == "sale-add-item":
        if not livro_id:
            return (
                carrinho,
                html.Div(
                    "Seleciona um livro.",
                    className="sale-error-message",
                ),
                "",
            )

        if not quantidade or int(quantidade) <= 0:
            return (
                carrinho,
                html.Div(
                    "Indica uma quantidade válida.",
                    className="sale-error-message",
                ),
                "",
            )

        livro = obter_livro(
            livro_id
        )

        if not livro:
            return (
                carrinho,
                html.Div(
                    "Livro não encontrado.",
                    className="sale-error-message",
                ),
                "",
            )

        quantidade = int(quantidade)
        quantidade_existente = 0

        for item in carrinho:
            if int(item["livro_id"]) == int(livro_id):
                quantidade_existente = int(
                    item["quantidade"]
                )

        quantidade_total = (
            quantidade_existente
            + quantidade
        )

        if quantidade_total > int(
            livro["stock_disponivel"]
        ):
            return (
                carrinho,
                html.Div(
                    (
                        f"Stock insuficiente. "
                        f"Disponível: {livro['stock_disponivel']}."
                    ),
                    className="sale-error-message",
                ),
                "",
            )

        preco = float(
            livro["preco_venda"]
        )

        novo_carrinho = []
        encontrado = False

        for item in carrinho:
            if int(item["livro_id"]) == int(livro_id):
                nova_quantidade = (
                    int(item["quantidade"])
                    + quantidade
                )

                novo_carrinho.append(
                    {
                        "livro_id": int(livro_id),
                        "titulo": livro["titulo"],
                        "quantidade": nova_quantidade,
                        "preco": preco,
                        "subtotal": preco * nova_quantidade,
                    }
                )

                encontrado = True
            else:
                novo_carrinho.append(item)

        if not encontrado:
            novo_carrinho.append(
                {
                    "livro_id": int(livro_id),
                    "titulo": livro["titulo"],
                    "quantidade": quantidade,
                    "preco": preco,
                    "subtotal": preco * quantidade,
                }
            )

        return (
            novo_carrinho,
            html.Div(
                f"{livro['titulo']} adicionado ao carrinho.",
                className="sale-success-message",
            ),
            "",
        )

    if acao == "sale-submit":
        if not carrinho:
            return (
                carrinho,
                "",
                html.Div(
                    "Adiciona pelo menos um livro ao carrinho.",
                    className="sale-error-message",
                ),
            )

        if not metodo_pagamento:
            return (
                carrinho,
                "",
                html.Div(
                    "Seleciona um método de pagamento.",
                    className="sale-error-message",
                ),
            )

        cliente_final = (
            None
            if cliente_id == "balcao"
            else cliente_id
        )

        itens = [
            {
                "livro_id": item["livro_id"],
                "quantidade": item["quantidade"],
            }
            for item in carrinho
        ]

        try:
            resultado = registar_venda(
                cliente_final,
                metodo_pagamento,
                itens,
            )
        except Exception as erro:
            return (
                carrinho,
                "",
                html.Div(
                    f"Não foi possível registar a venda: {erro}",
                    className="sale-error-message",
                ),
            )

        try:
            atualizacao = executar_atualizacao_analitica()
            mensagem_atualizacao = atualizacao["mensagem"]
            atualizacao_ok = True
        except Exception as erro:
            mensagem_atualizacao = (
                "A venda foi registada, mas a atualização analítica falhou: "
                f"{erro}"
            )
            atualizacao_ok = False

        if atualizacao_ok:
            mensagem_final = html.Div(
                className="sale-final-success",
                children=[
                    html.Strong(
                        "Venda registada com sucesso"
                    ),
                    html.Span(
                        f"Venda #{resultado['venda_id']}"
                    ),
                    html.Span(
                        f"Total: {formatar_euro(resultado['total'])}"
                    ),
                    html.Small(
                        "O stock operacional foi atualizado automaticamente."
                    ),
                    html.Small(
                        mensagem_atualizacao
                    ),
                    html.Small(
                        "As análises do SABIN já podem apresentar os novos dados."
                    ),
                ],
            )
        else:
            mensagem_final = html.Div(
                children=[
                    html.Div(
                        className="sale-final-success",
                        children=[
                            html.Strong(
                                "Venda registada com sucesso"
                            ),
                            html.Span(
                                f"Venda #{resultado['venda_id']}"
                            ),
                            html.Span(
                                f"Total: {formatar_euro(resultado['total'])}"
                            ),
                        ],
                    ),
                    html.Div(
                        mensagem_atualizacao,
                        className="sale-error-message",
                    ),
                ]
            )

        return (
            [],
            "",
            mensagem_final,
        )

    return (
        carrinho,
        "",
        "",
    )


@app.callback(
    Output("sale-cart-container", "children"),
    Output("sale-total", "children"),
    Input("sale-cart-store", "data"),
)
def atualizar_carrinho(
    carrinho,
):
    carrinho = carrinho or []

    total = sum(
        float(item["subtotal"])
        for item in carrinho
    )

    return (
        criar_tabela_carrinho(
            carrinho
        ),
        formatar_euro(
            total
        ),
    )


if __name__ == "__main__":
    app.run(
        debug=True
    )
