import os
import re
import unicodedata
from datetime import date, timedelta

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
    no_update,
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
from services.etl_service import (
    solicitar_atualizacao_analitica,
)
from services.customer_service import adicionar_cliente
from services.reservation_service import (
    atualizar_status_reserva,
    carregar_clientes_reserva,
    carregar_livros_reserva,
    carregar_reservas,
    criar_reserva,
    expirar_reservas,
)
from services.export_service import (
    abrir_power_bi,
    gerar_excel,
    gerar_pdf,
)
from services.catalog_service import (
    adicionar_livro,
    atualizar_livro,
    alterar_preco,
    carregar_autores_gestao,
    carregar_generos_gestao,
    carregar_livros_gestao,
    consultar_historico_precos,
    consultar_movimentos_stock,
    obter_livro_gestao,
    repor_stock,
)


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

def _contar_vendas_operacionais():
    query = text("""
        SELECT COUNT(*) AS total
        FROM public.vendas
        WHERE LOWER(TRIM(COALESCE(status, ''))) LIKE 'conclu%';
    """)

    try:
        with engine.connect() as connection:
            resultado = connection.execute(
                query
            ).scalar_one()

        return int(resultado or 0)
    except Exception as erro:
        print(
            "Erro ao contar vendas operacionais:",
            erro,
        )
        return 0


def _contar_vendas_dw():
    query = text("""
        SELECT COUNT(DISTINCT venda_id_origem) AS total
        FROM dw.fact_vendas;
    """)

    try:
        with engine.connect() as connection:
            resultado = connection.execute(
                query
            ).scalar_one()

        return int(resultado or 0)
    except Exception as erro:
        print(
            "Erro ao contar vendas do Data Warehouse:",
            erro,
        )
        return 0


def _usar_dados_operacionais_visao_geral():
    vendas_operacionais = (
        _contar_vendas_operacionais()
    )
    vendas_dw = _contar_vendas_dw()

    return (
        vendas_operacionais > 0
        and vendas_operacionais >= vendas_dw
    )


def carregar_kpis():
    if _usar_dados_operacionais_visao_geral():
        query = text("""
            SELECT
                COALESCE(SUM(iv.subtotal), 0) AS receita_total,
                COUNT(DISTINCT v.id) AS numero_vendas,
                COALESCE(SUM(iv.quantidade), 0) AS unidades_vendidas
            FROM public.vendas v
            JOIN public.itens_venda iv
                ON iv.venda_id = v.id
            WHERE LOWER(TRIM(COALESCE(v.status, ''))) LIKE 'conclu%';
        """)
    else:
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
        ticket_medio = (
            receita_total
            / numero_vendas
        )
    else:
        ticket_medio = 0

    return {
        "receita_total": receita_total,
        "numero_vendas": numero_vendas,
        "unidades_vendidas": unidades_vendidas,
        "ticket_medio": ticket_medio,
    }


def carregar_receita_mensal():
    if _usar_dados_operacionais_visao_geral():
        query = text("""
            SELECT
                DATE_TRUNC(
                    'month',
                    v.data_venda
                )::date AS mes,
                SUM(iv.subtotal) AS receita
            FROM public.vendas v
            JOIN public.itens_venda iv
                ON iv.venda_id = v.id
            WHERE LOWER(TRIM(COALESCE(v.status, ''))) LIKE 'conclu%'
            GROUP BY 1
            ORDER BY 1;
        """)
    else:
        query = text("""
            SELECT
                DATE_TRUNC(
                    'month',
                    d.data
                )::date AS mes,
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

    if not dados.empty:
        dados["mes"] = pd.to_datetime(
            dados["mes"]
        )

    return dados


def carregar_top_livros():
    if _usar_dados_operacionais_visao_geral():
        query = text("""
            SELECT
                l.titulo,
                SUM(iv.quantidade) AS unidades_vendidas
            FROM public.vendas v
            JOIN public.itens_venda iv
                ON iv.venda_id = v.id
            JOIN public.livros l
                ON l.id = iv.livro_id
            WHERE LOWER(TRIM(COALESCE(v.status, ''))) LIKE 'conclu%'
            GROUP BY l.titulo
            ORDER BY unidades_vendidas DESC
            LIMIT 5;
        """)
    else:
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


def carregar_stock_completo():
    query = text("""
        SELECT
            l.id,
            l.titulo,
            l.isbn,
            l.estoque_atual,
            l.qtd_reservada,
            GREATEST(
                l.estoque_atual - l.qtd_reservada,
                0
            ) AS stock_disponivel,
            a.media_mensal_vendas,
            a.meses_cobertura,
            a.nivel
        FROM public.livros l
        LEFT JOIN dw.alertas_stock a
            ON a.livro_id = l.id
        ORDER BY
            CASE
                WHEN a.nivel = 'Crítico' THEN 1
                WHEN a.nivel = 'Atenção' THEN 2
                WHEN a.nivel = 'Normal' THEN 3
                ELSE 4
            END,
            l.titulo;
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

    ordem_niveis = [
        "Crítico",
        "Atenção",
        "Normal",
        "Sem procura recente",
    ]

    figura = go.Figure()

    for nivel in ordem_niveis:
        grupo = dados[
            dados["nivel"] == nivel
        ]

        if grupo.empty:
            continue

        figura.add_trace(
            go.Scatter(
                x=grupo["media_mensal_vendas"],
                y=grupo["stock_disponivel"],
                mode="markers",
                name=nivel,
                text=grupo["titulo"],
                marker={
                    "size": 11,
                    "color": cores.get(
                        nivel,
                        "#64748b",
                    ),
                    "line": {
                        "color": "#ffffff",
                        "width": 1.4,
                    },
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
        height=440,
        autosize=True,
        margin={
            "l": 62,
            "r": 28,
            "t": 82,
            "b": 58,
        },
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.12,
            "xanchor": "center",
            "x": 0.5,
        },
        hovermode="closest",
    )

    figura.update_xaxes(
        title="Média Mensal de Vendas",
        gridcolor="#e2e8f0",
        zeroline=False,
        automargin=True,
    )

    figura.update_yaxes(
        title="Stock Disponível",
        gridcolor="#e2e8f0",
        zeroline=False,
        automargin=True,
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
                        children=[
                            html.Span("Operações"),
                            html.Span(
                                "▾",
                                id="operacoes-arrow",
                                className="menu-arrow",
                            ),
                        ],
                        id="toggle-operacoes",
                        className="menu-section-button",
                    ),
                    html.Div(
                        id="submenu-operacoes",
                        className="submenu collapsed",
                        children=[
                            html.Button(
                                "Registar Venda",
                                id="btn-venda",
                                className="submenu-button",
                            ),
                            html.Button(
                                "Reservas",
                                id="btn-reservas",
                                className="submenu-button",
                            ),
                            html.Button(
                                "Gestão de Catálogo",
                                id="btn-gestao-catalogo",
                                className="submenu-button",
                            ),
                        ],
                    ),
                    html.Button(
                        children=[
                            html.Span("Análises"),
                            html.Span(
                                "▾",
                                id="analises-arrow",
                                className="menu-arrow",
                            ),
                        ],
                        id="toggle-analises",
                        className="menu-section-button",
                    ),
                    html.Div(
                        id="submenu-analises",
                        className="submenu collapsed",
                        children=[
                            html.Button(
                                "Catálogo",
                                id="btn-catalogo",
                                className="submenu-button",
                            ),
                            html.Button(
                                "Previsões",
                                id="btn-previsoes",
                                className="submenu-button",
                            ),
                            html.Button(
                                "Stock e Reposição",
                                id="btn-stock",
                                className="submenu-button",
                            ),
                            html.Button(
                                "Interpretação",
                                id="btn-interpretacao-stock",
                                className="submenu-button",
                            ),
                            html.Button(
                                "Exportações",
                                id="btn-exportacoes",
                                className="submenu-button",
                            ),
                        ],
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

    metricas = (
        carregar_metricas_previsao()
        or {}
    )

    stock = carregar_alertas_stock()
    alertas_previsao = (
        carregar_alertas_previsao()
    )

    grafico_receita = (
        criar_grafico_receita_mensal(
            receita_mensal
        )
    )

    grafico_top = (
        criar_grafico_top_livros(
            top_livros
        )
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
        alertas_previsao["nivel"]
        == "Crítico"
    ]

    mensagem_previsao = (
        "Sem alertas críticos."
    )

    if not alerta_critico.empty:
        mensagem_previsao = (
            alerta_critico
            .iloc[0]["mensagem"]
        )

    variacao = metricas.get(
        "variacao_prevista_percent"
    )

    try:
        variacao_numero = float(
            variacao
        )
    except (
        TypeError,
        ValueError,
    ):
        variacao_numero = 0.0

    return html.Div(
        children=[
            dcc.Interval(
                id="overview-refresh-interval",
                interval=5000,
                n_intervals=0,
            ),
            html.Div(
                className="page-header",
                children=[
                    html.H2(
                        "Visão Geral"
                    ),
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
                            html.P(
                                "Receita Total"
                            ),
                            html.H3(
                                formatar_euro(
                                    kpis[
                                        "receita_total"
                                    ]
                                ),
                                id=(
                                    "overview-revenue-total"
                                ),
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P(
                                "Número de Vendas"
                            ),
                            html.H3(
                                formatar_inteiro(
                                    kpis[
                                        "numero_vendas"
                                    ]
                                ),
                                id=(
                                    "overview-sales-count"
                                ),
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P(
                                "Unidades Vendidas"
                            ),
                            html.H3(
                                formatar_inteiro(
                                    kpis[
                                        "unidades_vendidas"
                                    ]
                                ),
                                id=(
                                    "overview-units-count"
                                ),
                            ),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.P(
                                "Ticket Médio"
                            ),
                            html.H3(
                                formatar_euro(
                                    kpis[
                                        "ticket_medio"
                                    ]
                                ),
                                id=(
                                    "overview-ticket-average"
                                ),
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
                                id=(
                                    "overview-revenue-chart"
                                ),
                                figure=(
                                    grafico_receita
                                ),
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
                                id=(
                                    "overview-top-chart"
                                ),
                                figure=(
                                    grafico_top
                                ),
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
                            html.H3(
                                "Situação Atual"
                            ),
                            html.Div(
                                className=(
                                    "business-grid"
                                ),
                                children=[
                                    html.Div(
                                        className=(
                                            "business-item"
                                        ),
                                        children=[
                                            html.Span(
                                                "Último mês observado"
                                            ),
                                            html.Strong(
                                                formatar_mes(
                                                    metricas.get(
                                                        "ultimo_mes_real"
                                                    )
                                                ),
                                                id=(
                                                    "overview-last-month"
                                                ),
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className=(
                                            "business-item"
                                        ),
                                        children=[
                                            html.Span(
                                                "Receita do último mês"
                                            ),
                                            html.Strong(
                                                formatar_euro(
                                                    metricas.get(
                                                        "ultima_receita_real",
                                                        0,
                                                    )
                                                ),
                                                id=(
                                                    "overview-last-revenue"
                                                ),
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className=(
                                            "business-item"
                                        ),
                                        children=[
                                            html.Span(
                                                "Próximo período"
                                            ),
                                            html.Strong(
                                                formatar_mes(
                                                    metricas.get(
                                                        "proximo_mes"
                                                    )
                                                ),
                                                id=(
                                                    "overview-next-period"
                                                ),
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className=(
                                            "business-item"
                                        ),
                                        children=[
                                            html.Span(
                                                "Receita prevista"
                                            ),
                                            html.Strong(
                                                formatar_euro(
                                                    metricas.get(
                                                        "receita_prevista_proximo_mes",
                                                        0,
                                                    )
                                                ),
                                                id=(
                                                    "overview-forecast-revenue"
                                                ),
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className=(
                                    "variation-box"
                                ),
                                children=[
                                    html.Span(
                                        "Variação prevista"
                                    ),
                                    html.Strong(
                                        formatar_percentagem(
                                            variacao_numero
                                        ),
                                        id=(
                                            "overview-forecast-variation"
                                        ),
                                        className=(
                                            "value-negative"
                                            if variacao_numero
                                            < 0
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
                            html.H3(
                                "Alertas Recentes"
                            ),
                            html.Div(
                                className=(
                                    "overview-alert "
                                    "critical-overview"
                                ),
                                children=[
                                    html.Span(
                                        "Stock crítico"
                                    ),
                                    html.Strong(
                                        (
                                            f"{criticos_stock} "
                                            "livro(s)"
                                        ),
                                        id=(
                                            "overview-stock-critical"
                                        ),
                                    ),
                                ],
                            ),
                            html.Div(
                                className=(
                                    "overview-alert "
                                    "warning-overview"
                                ),
                                children=[
                                    html.Span(
                                        "Stock em atenção"
                                    ),
                                    html.Strong(
                                        (
                                            f"{atencao_stock} "
                                            "livro(s)"
                                        ),
                                        id=(
                                            "overview-stock-warning"
                                        ),
                                    ),
                                ],
                            ),
                            html.Div(
                                className=(
                                    "overview-alert "
                                    "info-overview"
                                ),
                                children=[
                                    html.Span(
                                        "Previsão"
                                    ),
                                    html.Strong(
                                        mensagem_previsao,
                                        id=(
                                            "overview-forecast-alert"
                                        ),
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

def criar_opcoes_clientes_venda():
    clientes = carregar_clientes()

    opcoes = [
        {
            "label": "Venda ao balcão — cliente não identificado",
            "value": "balcao",
        },
        {
            "label": "+ Adicionar novo cliente",
            "value": "novo_cliente",
        },
    ]

    for cliente in clientes:
        opcoes.append(
            {
                "label": (
                    f"{cliente['nome_completo']} — "
                    f"NIF {cliente['nif']}"
                ),
                "value": cliente["id"],
            }
        )

    return opcoes


def criar_opcoes_livros_venda():
    livros = carregar_livros_disponiveis()
    opcoes = []

    for livro in livros:
        opcoes.append(
            {
                "label": (
                    f"{livro['titulo']} — "
                    f"ISBN {livro['isbn']} — "
                    f"{formatar_euro(livro['preco_venda'])} — "
                    f"{livro['stock_disponivel']} disponíveis"
                ),
                "value": livro["id"],
            }
        )

    return opcoes


def pagina_registar_venda():
    opcoes_clientes = criar_opcoes_clientes_venda()
    opcoes_livros = criar_opcoes_livros_venda()

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
                            html.Div(
                                id="sale-new-client-form",
                                className="new-client-form hidden",
                                children=[
                                    html.H4("Novo Cliente"),
                                    html.Div(
                                        className="new-client-grid",
                                        children=[
                                            html.Div(
                                                className="form-field span-2",
                                                children=[
                                                    html.Label(
                                                        "Nome completo",
                                                        className="form-label",
                                                    ),
                                                    dcc.Input(
                                                        id="sale-new-client-name",
                                                        type="text",
                                                        placeholder="Nome completo",
                                                        className="sale-number-input",
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                className="form-field",
                                                children=[
                                                    html.Label(
                                                        "NIF",
                                                        className="form-label",
                                                    ),
                                                    dcc.Input(
                                                        id="sale-new-client-nif",
                                                        type="text",
                                                        placeholder="9 dígitos",
                                                        className="sale-number-input",
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                className="form-field",
                                                children=[
                                                    html.Label(
                                                        "Telemóvel",
                                                        className="form-label",
                                                    ),
                                                    dcc.Input(
                                                        id="sale-new-client-phone",
                                                        type="text",
                                                        placeholder="Opcional",
                                                        className="sale-number-input",
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                className="form-field span-2",
                                                children=[
                                                    html.Label(
                                                        "Email",
                                                        className="form-label",
                                                    ),
                                                    dcc.Input(
                                                        id="sale-new-client-email",
                                                        type="email",
                                                        placeholder="Opcional",
                                                        className="sale-number-input",
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                    html.Button(
                                        "Guardar Cliente",
                                        id="sale-new-client-submit",
                                        className="primary-button new-client-submit",
                                    ),
                                    html.Div(
                                        id="sale-new-client-message",
                                    ),
                                ],
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
                            html.Div(
                                className="quantity-stepper",
                                children=[
                                    html.Button(
                                        "−",
                                        id="sale-quantity-minus",
                                        className="stepper-button",
                                        n_clicks=0,
                                    ),
                                    dcc.Input(
                                        id="sale-quantity",
                                        type="text",
                                        value="1",
                                        className="stepper-input",
                                    ),
                                    html.Button(
                                        "+",
                                        id="sale-quantity-plus",
                                        className="stepper-button",
                                        n_clicks=0,
                                    ),
                                ],
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


# Página Gestão de Catálogo

def criar_tabela_movimentos_stock(movimentos):
    if not movimentos:
        return html.Div(
            "Ainda não existem movimentos de stock para este livro.",
            className="empty-cart",
        )

    linhas = []

    for movimento in movimentos:
        data = pd.to_datetime(
            movimento["data_movimento"]
        ).strftime("%d/%m/%Y %H:%M")

        linhas.append(
            html.Tr(
                children=[
                    html.Td(data),
                    html.Td(movimento["tipo"]),
                    html.Td(str(movimento["quantidade"])),
                    html.Td(
                        f"{movimento['stock_anterior']} → {movimento['stock_novo']}"
                    ),
                    html.Td(movimento["origem"]),
                ]
            )
        )

    return html.Table(
        className="sale-cart-table",
        children=[
            html.Thead(
                html.Tr(
                    children=[
                        html.Th("Data"),
                        html.Th("Tipo"),
                        html.Th("Qtd."),
                        html.Th("Stock"),
                        html.Th("Origem"),
                    ]
                )
            ),
            html.Tbody(linhas),
        ],
    )


def criar_tabela_historico_precos(historico):
    if not historico:
        return html.Div(
            "Ainda não existem alterações de preço para este livro.",
            className="empty-cart",
        )

    linhas = []

    for registo in historico:
        data = pd.to_datetime(
            registo["data_alteracao"]
        ).strftime("%d/%m/%Y %H:%M")

        linhas.append(
            html.Tr(
                children=[
                    html.Td(data),
                    html.Td(
                        formatar_euro(
                            registo["preco_anterior"]
                        )
                    ),
                    html.Td(
                        formatar_euro(
                            registo["preco_novo"]
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
                        html.Th("Data"),
                        html.Th("Preço anterior"),
                        html.Th("Novo preço"),
                    ]
                )
            ),
            html.Tbody(linhas),
        ],
    )


def pagina_gestao_catalogo():
    livros = carregar_livros_gestao()
    generos = carregar_generos_gestao()

    opcoes_livros = [
        {
            "label": (
                f"{livro['titulo']} — "
                f"{livro['isbn']}"
            ),
            "value": livro["id"],
        }
        for livro in livros
    ]

    opcoes_generos = [
        {
            "label": genero["nome"],
            "value": genero["id"],
        }
        for genero in generos
    ]

    return html.Div(
        children=[
            dcc.Store(
                id="management-refresh-store",
                data=0,
            ),
            dcc.Store(
                id="management-edit-refresh-store",
                data=0,
            ),
            html.Div(
                className="page-header",
                children=[
                    html.H2("Gestão de Catálogo"),
                    html.P(
                        "Reposição de stock, atualização de preços e registo de novos livros"
                    ),
                ],
            ),
            html.Div(
                className="sale-form-panel management-select-panel",
                children=[
                    html.H3("Selecionar Livro"),
                    dcc.Dropdown(
                        id="management-book",
                        options=opcoes_livros,
                        placeholder="Seleciona um livro...",
                        clearable=True,
                        searchable=True,
                        className="sale-dropdown",
                    ),
                    html.Div(
                        id="management-book-info",
                        className="sale-book-info",
                    ),
                ],
            ),
            html.Div(
                className="sale-form-panel edit-book-panel",
                children=[
                    html.H3("Editar Informações do Livro"),
                    html.P(
                        "Seleciona um livro acima para corrigir título, ISBN, editora, data, autores ou géneros.",
                        className="form-help",
                    ),
                    html.Div(
                        className="book-form-grid",
                        children=[
                            html.Div(
                                className="form-field span-2",
                                children=[
                                    html.Label("Título", className="form-label"),
                                    dcc.Input(
                                        id="management-edit-title",
                                        type="text",
                                        className="sale-number-input",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field",
                                children=[
                                    html.Label("ISBN", className="form-label"),
                                    dcc.Input(
                                        id="management-edit-isbn",
                                        type="text",
                                        className="sale-number-input",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field",
                                children=[
                                    html.Label("Editora", className="form-label"),
                                    dcc.Input(
                                        id="management-edit-publisher",
                                        type="text",
                                        className="sale-number-input",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field",
                                children=[
                                    html.Label("Data de publicação", className="form-label"),
                                    dcc.DatePickerSingle(
                                        id="management-edit-date",
                                        display_format="DD/MM/YYYY",
                                        placeholder="Seleciona uma data",
                                        className="book-date-picker",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field span-2",
                                children=[
                                    html.Label("Autor(es)", className="form-label"),
                                    dcc.Input(
                                        id="management-edit-authors",
                                        type="text",
                                        placeholder="Ex.: José Saramago",
                                        className="sale-number-input",
                                    ),
                                    html.P(
                                        "Para vários autores, separa os nomes por vírgulas.",
                                        className="form-help",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field span-2",
                                children=[
                                    html.Label("Género(s)", className="form-label"),
                                    dcc.Dropdown(
                                        id="management-edit-genres",
                                        options=opcoes_generos,
                                        multi=True,
                                        placeholder="Seleciona um ou mais géneros",
                                        className="sale-dropdown",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Button(
                        "Guardar Alterações",
                        id="management-edit-submit",
                        className="primary-button add-book-button",
                    ),
                    html.Div(id="management-edit-message"),
                ],
            ),
            html.Div(
                className="sale-layout",
                children=[
                    html.Div(
                        className="sale-form-panel",
                        children=[
                            html.H3("Repor Stock"),
                            html.P(
                                "Adiciona unidades ao stock físico do livro.",
                                className="form-help",
                            ),
                            html.Label(
                                "Quantidade a adicionar",
                                className="form-label",
                            ),
                            html.Div(
                                className="quantity-stepper",
                                children=[
                                    html.Button(
                                        "−",
                                        id="management-stock-minus",
                                        className="stepper-button",
                                    ),
                                    dcc.Input(
                                        id="management-stock-quantity",
                                        type="text",
                                        value="1",
                                        className="stepper-input",
                                    ),
                                    html.Button(
                                        "+",
                                        id="management-stock-plus",
                                        className="stepper-button",
                                    ),
                                ],
                            ),
                            html.Label(
                                "Observação",
                                className="form-label",
                            ),
                            dcc.Textarea(
                                id="management-stock-observation",
                                placeholder="Ex.: Reposição do fornecedor",
                                className="management-textarea",
                            ),
                            html.Button(
                                "Confirmar Reposição",
                                id="management-stock-submit",
                                className="primary-button sale-submit-button",
                            ),
                            html.Div(
                                id="management-stock-message",
                            ),
                        ],
                    ),
                    html.Div(
                        className="sale-form-panel",
                        children=[
                            html.H3("Alterar Preço"),
                            html.P(
                                "Define o preço utilizado nas próximas vendas.",
                                className="form-help",
                            ),
                            html.Label(
                                "Novo preço (€)",
                                className="form-label",
                            ),
                            dcc.Input(
                                id="management-price-input",
                                type="text",
                                placeholder="Ex.: 13.90",
                                className="sale-number-input",
                            ),
                            html.Button(
                                "Atualizar Preço",
                                id="management-price-submit",
                                className="primary-button sale-submit-button",
                            ),
                            html.Div(
                                id="management-price-message",
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="sale-form-panel add-book-panel",
                children=[
                    html.Div(
                        className="panel-heading-row",
                        children=[
                            html.Div(
                                children=[
                                    html.H3("Adicionar Novo Livro"),
                                    html.P(
                                        "Regista um novo título no catálogo da Bookmarked.",
                                        className="form-help",
                                    ),
                                ]
                            ),
                        ],
                    ),
                    html.Div(
                        className="book-form-grid",
                        children=[
                            html.Div(
                                className="form-field span-2",
                                children=[
                                    html.Label(
                                        "Título",
                                        className="form-label",
                                    ),
                                    dcc.Input(
                                        id="new-book-title",
                                        type="text",
                                        placeholder="Título do livro",
                                        className="sale-number-input",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field",
                                children=[
                                    html.Label(
                                        "ISBN",
                                        className="form-label",
                                    ),
                                    dcc.Input(
                                        id="new-book-isbn",
                                        type="text",
                                        placeholder="ISBN-10 ou ISBN-13",
                                        className="sale-number-input",
                                        debounce=0.7,
                                    ),
                                    dcc.Loading(
                                        id="new-book-isbn-loading",
                                        type="circle",
                                        children=html.Div(
                                            id="new-book-api-message",
                                        ),
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field",
                                children=[
                                    html.Label(
                                        "Preço (€)",
                                        className="form-label",
                                    ),
                                    dcc.Input(
                                        id="new-book-price",
                                        type="text",
                                        placeholder="Ex.: 17.50",
                                        className="sale-number-input",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field",
                                children=[
                                    html.Label(
                                        "Stock inicial",
                                        className="form-label",
                                    ),
                                    html.Div(
                                        className="quantity-stepper",
                                        children=[
                                            html.Button(
                                                "−",
                                                id="new-book-stock-minus",
                                                className="stepper-button",
                                                n_clicks=0,
                                            ),
                                            dcc.Input(
                                                id="new-book-stock",
                                                type="text",
                                                value="0",
                                                className="stepper-input",
                                            ),
                                            html.Button(
                                                "+",
                                                id="new-book-stock-plus",
                                                className="stepper-button",
                                                n_clicks=0,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field",
                                children=[
                                    html.Label(
                                        "Editora",
                                        className="form-label",
                                    ),
                                    dcc.Input(
                                        id="new-book-publisher",
                                        type="text",
                                        placeholder="Editora",
                                        className="sale-number-input",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field",
                                children=[
                                    html.Label(
                                        "Data de publicação",
                                        className="form-label",
                                    ),
                                    dcc.DatePickerSingle(
                                        id="new-book-date",
                                        display_format="DD/MM/YYYY",
                                        placeholder="Seleciona uma data",
                                        className="book-date-picker",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field span-2",
                                children=[
                                    html.Label(
                                        "Autor(es)",
                                        className="form-label",
                                    ),
                                    dcc.Input(
                                        id="new-book-authors",
                                        type="text",
                                        placeholder="Ex.: José Saramago",
                                        className="sale-number-input",
                                    ),
                                    html.P(
                                        "Para vários autores, separa os nomes por vírgulas.",
                                        className="form-help",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="form-field span-2",
                                children=[
                                    html.Label(
                                        "Género(s)",
                                        className="form-label",
                                    ),
                                    dcc.Dropdown(
                                        id="new-book-genres",
                                        options=opcoes_generos,
                                        multi=True,
                                        placeholder="Seleciona um ou mais géneros",
                                        className="sale-dropdown",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Button(
                        "Adicionar Livro",
                        id="management-add-book-submit",
                        className="primary-button add-book-button",
                    ),
                    dcc.Loading(
                        id="management-add-loading",
                        type="circle",
                        children=html.Div(
                            id="management-add-message",
                        ),
                    ),
                ],
            ),
            html.Div(
                className="management-history-grid",
                children=[
                    html.Div(
                        className="sale-form-panel",
                        children=[
                            html.H3("Movimentos de Stock"),
                            html.Div(
                                id="management-stock-history",
                                children=html.Div(
                                    "Seleciona um livro para consultar o histórico.",
                                    className="empty-cart",
                                ),
                            ),
                        ],
                    ),
                    html.Div(
                        className="sale-form-panel",
                        children=[
                            html.H3("Histórico de Preços"),
                            html.Div(
                                id="management-price-history",
                                children=html.Div(
                                    "Seleciona um livro para consultar o histórico.",
                                    className="empty-cart",
                                ),
                            ),
                        ],
                    ),
                ],
            ),
        ]
    )


# Página Reservas

def criar_tabela_reservas(dados):
    if not dados:
        return html.Div(
            "Ainda não existem reservas.",
            className="empty-cart",
        )

    linhas = []

    for reserva in dados:
        linhas.append(
            html.Tr(
                children=[
                    html.Td(str(reserva["id"])),
                    html.Td(reserva["cliente"]),
                    html.Td(reserva["livro"]),
                    html.Td(str(reserva["quantidade"])),
                    html.Td(
                        reserva["data_limite"].strftime("%d/%m/%Y")
                        if reserva["data_limite"]
                        else "—"
                    ),
                    html.Td(reserva["status"]),
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
                                html.Th("ID"),
                                html.Th("Cliente"),
                                html.Th("Livro"),
                                html.Th("Qtd."),
                                html.Th("Limite"),
                                html.Th("Estado"),
                            ]
                        )
                    ),
                    html.Tbody(linhas),
                ],
            )
        ],
    )


def pagina_reservas():
    expirar_reservas()

    clientes = carregar_clientes_reserva()
    livros = carregar_livros_reserva()
    reservas = carregar_reservas()

    opcoes_clientes = [
        {
            "label": (
                f"{cliente['nome_completo']} — NIF {cliente['nif']}"
            ),
            "value": cliente["id"],
        }
        for cliente in clientes
    ]

    opcoes_livros = [
        {
            "label": (
                f"{livro['titulo']} — ISBN {livro['isbn']} — "
                f"{livro['stock_disponivel']} disponíveis"
            ),
            "value": livro["id"],
        }
        for livro in livros
        if int(livro["stock_disponivel"]) > 0
    ]

    pendentes = [
        reserva
        for reserva in reservas
        if reserva["status"] == "Pendente"
    ]

    opcoes_pendentes = [
        {
            "label": (
                f"#{reserva['id']} — {reserva['cliente']} — "
                f"{reserva['livro']}"
            ),
            "value": reserva["id"],
        }
        for reserva in pendentes
    ]

    return html.Div(
        children=[
            dcc.Store(
                id="reservation-refresh-store",
                data=0,
            ),
            html.Div(
                className="page-header",
                children=[
                    html.H2("Reservas"),
                    html.P(
                        "Criação e acompanhamento de reservas de livros"
                    ),
                ],
            ),
            html.Div(
                className="sale-layout reservation-layout",
                children=[
                    html.Div(
                        className="sale-form-panel",
                        children=[
                            html.H3("Nova Reserva"),
                            html.Label(
                                "Cliente",
                                className="form-label",
                            ),
                            dcc.Dropdown(
                                id="reservation-client",
                                options=opcoes_clientes,
                                placeholder="Seleciona um cliente...",
                                searchable=True,
                                className="sale-dropdown",
                            ),
                            html.Label(
                                "Livro",
                                className="form-label",
                            ),
                            dcc.Dropdown(
                                id="reservation-book",
                                options=opcoes_livros,
                                placeholder="Seleciona um livro...",
                                searchable=True,
                                className="sale-dropdown",
                            ),
                            html.Label(
                                "Quantidade",
                                className="form-label",
                            ),
                            html.Div(
                                className="quantity-stepper",
                                children=[
                                    html.Button(
                                        "−",
                                        id="reservation-quantity-minus",
                                        className="stepper-button",
                                        n_clicks=0,
                                    ),
                                    dcc.Input(
                                        id="reservation-quantity",
                                        type="text",
                                        value="1",
                                        className="stepper-input",
                                    ),
                                    html.Button(
                                        "+",
                                        id="reservation-quantity-plus",
                                        className="stepper-button",
                                        n_clicks=0,
                                    ),
                                ],
                            ),
                            html.Label(
                                "Reservar até",
                                className="form-label",
                            ),
                            dcc.DatePickerSingle(
                                id="reservation-limit-date",
                                min_date_allowed=date.today(),
                                date=date.today() + timedelta(days=3),
                                display_format="DD/MM/YYYY",
                                className="book-date-picker",
                            ),
                            html.Button(
                                "Criar Reserva",
                                id="reservation-submit",
                                className="primary-button sale-submit-button",
                            ),
                            html.Div(
                                id="reservation-message",
                            ),
                        ],
                    ),
                    html.Div(
                        className="sale-form-panel",
                        children=[
                            html.H3("Gerir Reserva"),
                            html.Label(
                                "Reserva pendente",
                                className="form-label",
                            ),
                            dcc.Dropdown(
                                id="reservation-active",
                                options=opcoes_pendentes,
                                placeholder="Seleciona uma reserva...",
                                searchable=True,
                                className="sale-dropdown",
                            ),
                            html.Div(
                                className="reservation-actions single-action",
                                children=[
                                    html.Button(
                                        "Cancelar Reserva",
                                        id="reservation-cancel",
                                        className="secondary-button",
                                    ),
                                ],
                            ),
                            html.P(
                                "Quando o cliente levantar o livro, regista a venda normalmente em Registar Venda.",
                                className="form-help",
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="sale-form-panel reservation-table-panel",
                children=[
                    html.H3("Todas as Reservas"),
                    html.Div(
                        id="reservation-table-container",
                        children=criar_tabela_reservas(reservas),
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
                    dcc.Loading(
                        id="catalog-api-loading",
                        type="circle",
                        children=html.Div(
                            id="catalog-api-message"
                        ),
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

def criar_tabela_stock_completo(dados):
    if dados.empty:
        return html.Div(
            "Não existem livros no catálogo.",
            className="empty-cart",
        )

    classes_nivel = {
        "Crítico": "stock-status critical",
        "Atenção": "stock-status warning",
        "Normal": "stock-status normal",
        "Sem procura recente": "stock-status neutral",
    }

    linhas = []

    for _, livro in dados.iterrows():
        nivel = (
            livro["nivel"]
            if pd.notna(livro["nivel"])
            else "Sem análise"
        )

        cobertura = (
            f"{float(livro['meses_cobertura']):.2f}"
            .replace(".", ",")
            if pd.notna(livro["meses_cobertura"])
            else "—"
        )

        media = (
            f"{float(livro['media_mensal_vendas']):.2f}"
            .replace(".", ",")
            if pd.notna(livro["media_mensal_vendas"])
            else "—"
        )

        linhas.append(
            html.Tr(
                children=[
                    html.Td(livro["titulo"]),
                    html.Td(str(int(livro["estoque_atual"]))),
                    html.Td(str(int(livro["qtd_reservada"]))),
                    html.Td(str(int(livro["stock_disponivel"]))),
                    html.Td(media),
                    html.Td(cobertura),
                    html.Td(
                        html.Span(
                            nivel,
                            className=classes_nivel.get(
                                nivel,
                                "stock-status neutral",
                            ),
                        )
                    ),
                ]
            )
        )

    return html.Div(
        className="stock-table-wrapper",
        children=[
            html.Table(
                className="stock-table stock-all-table",
                children=[
                    html.Thead(
                        html.Tr(
                            children=[
                                html.Th("Livro"),
                                html.Th("Stock físico"),
                                html.Th("Reservado"),
                                html.Th("Disponível"),
                                html.Th("Média mensal"),
                                html.Th("Cobertura"),
                                html.Th("Estado"),
                            ]
                        )
                    ),
                    html.Tbody(linhas),
                ],
            )
        ],
    )



def formatar_numero_simples(
    valor,
    casas=2,
):
    if valor is None or pd.isna(valor):
        return "—"

    return (
        f"{float(valor):.{casas}f}"
        .replace(".", ",")
    )


def criar_interpretacao_stock(
    dados,
    stock_completo,
):
    dados = dados.copy()
    stock_completo = stock_completo.copy()

    colunas_numericas_dados = [
        "stock_disponivel",
        "media_mensal_vendas",
        "meses_cobertura",
        "quantidade_recomendada",
    ]

    for coluna in colunas_numericas_dados:
        if coluna in dados.columns:
            dados[coluna] = pd.to_numeric(
                dados[coluna],
                errors="coerce",
            )

    colunas_numericas_stock = [
        "stock_disponivel",
        "media_mensal_vendas",
        "meses_cobertura",
        "estoque_atual",
        "qtd_reservada",
    ]

    for coluna in colunas_numericas_stock:
        if coluna in stock_completo.columns:
            stock_completo[coluna] = pd.to_numeric(
                stock_completo[coluna],
                errors="coerce",
            )

    total_livros = len(stock_completo)

    criticos = dados[
        dados["nivel"] == "Crítico"
    ].copy()

    atencao = dados[
        dados["nivel"] == "Atenção"
    ].copy()

    normais = dados[
        dados["nivel"] == "Normal"
    ].copy()

    sem_procura = stock_completo[
        stock_completo["nivel"] == "Sem procura recente"
    ].copy()

    alertas = dados[
        dados["nivel"].isin([
            "Crítico",
            "Atenção",
        ])
    ].copy()

    unidades_repor = int(
        dados[
            "quantidade_recomendada"
        ].fillna(0).sum()
    )

    percentagem_alerta = (
        (len(alertas) / total_livros) * 100
        if total_livros
        else 0
    )

    livro_mais_urgente = None

    if not alertas.empty:
        alertas_ordenados = alertas.assign(
            prioridade=alertas[
                "nivel"
            ].map({
                "Crítico": 0,
                "Atenção": 1,
            }).fillna(2),
        ).sort_values(
            by=[
                "prioridade",
                "meses_cobertura",
                "stock_disponivel",
            ],
            na_position="last",
        )

        livro_mais_urgente = alertas_ordenados.iloc[0]

    livro_maior_procura = None

    dados_procura = stock_completo[
        stock_completo[
            "media_mensal_vendas"
        ].fillna(0) > 0
    ].copy()

    if not dados_procura.empty:
        livro_maior_procura = dados_procura.sort_values(
            by="media_mensal_vendas",
            ascending=False,
        ).iloc[0]

    media_procura_geral = (
        dados_procura[
            "media_mensal_vendas"
        ].mean()
        if not dados_procura.empty
        else 0
    )

    sem_procura_lista = stock_completo[
        stock_completo[
            "media_mensal_vendas"
        ].fillna(0) <= 0
    ].copy().head(4)

    top_procura = (
        dados_procura.sort_values(
            by=[
                "media_mensal_vendas",
                "meses_cobertura",
            ],
            ascending=[
                False,
                True,
            ],
            na_position="last",
        )
        .head(7)
        .copy()
    )

    def classificar_oportunidade_stock(linha):
        media = float(
            linha.get(
                "media_mensal_vendas",
                0,
            )
            or 0
        )

        stock = float(
            linha.get(
                "stock_disponivel",
                0,
            )
            or 0
        )

        cobertura = linha.get(
            "meses_cobertura"
        )

        if media <= 0:
            return (
                "Sem procura recente",
                "neutral",
            )

        if stock <= 1:
            return (
                "Repor urgente",
                "urgent",
            )

        if pd.isna(cobertura):
            return (
                "Monitorizar",
                "neutral",
            )

        cobertura = float(cobertura)

        if cobertura < 1:
            return (
                "Repor urgente",
                "urgent",
            )

        if cobertura < 2:
            return (
                "Aumentar stock",
                "increase",
            )

        if cobertura < 4:
            return (
                "Reforço preventivo",
                "preventive",
            )

        return (
            "Stock suficiente",
            "sufficient",
        )

    if not top_procura.empty:
        classificacoes = top_procura.apply(
            classificar_oportunidade_stock,
            axis=1,
        )

        top_procura[
            "sugestao_stock"
        ] = [
            item[0]
            for item in classificacoes
        ]

        top_procura[
            "classe_sugestao_stock"
        ] = [
            item[1]
            for item in classificacoes
        ]

    candidatos_reforco = (
        top_procura[
            top_procura[
                "sugestao_stock"
            ].isin([
                "Aumentar stock",
                "Reforço preventivo",
            ])
        ].copy()
        if not top_procura.empty
        else pd.DataFrame()
    )

    melhor_reforco = (
        candidatos_reforco.iloc[0]
        if not candidatos_reforco.empty
        else None
    )

    avisos = []

    for _, linha in criticos.head(4).iterrows():
        avisos.append({
            "classe": "warning-danger",
            "titulo": f"{linha['titulo']} necessita de reposição urgente.",
            "descricao": (
                f"Stock disponível: {int(linha['stock_disponivel']) if pd.notna(linha['stock_disponivel']) else 0} | "
                f"Cobertura: {formatar_numero_simples(linha['meses_cobertura'])} mês(es) | "
                f"Repor: {int(linha['quantidade_recomendada']) if pd.notna(linha['quantidade_recomendada']) else 0} unidade(s)."
            ),
        })

    for _, linha in atencao.head(3).iterrows():
        avisos.append({
            "classe": "warning-soft",
            "titulo": f"{linha['titulo']} está em nível de atenção.",
            "descricao": (
                f"Stock disponível: {int(linha['stock_disponivel']) if pd.notna(linha['stock_disponivel']) else 0} | "
                f"Cobertura: {formatar_numero_simples(linha['meses_cobertura'])} mês(es) | "
                f"Repor: {int(linha['quantidade_recomendada']) if pd.notna(linha['quantidade_recomendada']) else 0} unidade(s)."
            ),
        })

    if not avisos:
        avisos.append({
            "classe": "warning-info",
            "titulo": "Não existem avisos críticos neste momento.",
            "descricao": "O stock atual não apresenta livros em situação Crítica ou Atenção.",
        })

    informacoes = []

    informacoes.append({
        "titulo": "Situação Geral",
        "descricao": (
            f"{len(normais)} livro(s) estão em situação Normal e {len(sem_procura)} estão sem procura recente."
        ),
    })

    if livro_maior_procura is not None:
        informacoes.append({
            "titulo": "Maior Procura",
            "descricao": (
                f"{livro_maior_procura['titulo']} lidera a procura com média de "
                f"{formatar_numero_simples(livro_maior_procura['media_mensal_vendas'])} unidade(s) por mês."
            ),
        })

    if livro_mais_urgente is not None:
        informacoes.append({
            "titulo": "Maior Prioridade",
            "descricao": (
                f"{livro_mais_urgente['titulo']} é a reposição mais urgente, com cobertura de "
                f"{formatar_numero_simples(livro_mais_urgente['meses_cobertura'])} mês(es)."
            ),
        })

    informacoes.append({
        "titulo": "Reposição Recomendada",
        "descricao": f"O sistema recomenda a reposição total de {unidades_repor} unidade(s).",
    })

    recomendacoes = []

    if not criticos.empty:
        nomes_criticos = (
            criticos[
                "titulo"
            ]
            .dropna()
            .astype(str)
            .head(4)
            .tolist()
        )

        recomendacoes.append(
            "Repor imediatamente "
            + ", ".join(
                nomes_criticos
            )
            + "."
        )

    if melhor_reforco is not None:
        recomendacoes.append(
            f"Considerar aumentar o stock de {melhor_reforco['titulo']}: "
            f"tem procura média de {formatar_numero_simples(melhor_reforco['media_mensal_vendas'])} unidade(s)/mês "
            f"e cobertura de {formatar_numero_simples(melhor_reforco['meses_cobertura'])} mês(es)."
        )
    elif not atencao.empty:
        recomendacoes.append(
            "Acompanhar os livros em Atenção para evitar a passagem para o estado Crítico."
        )

    if livro_maior_procura is not None:
        maior_procura_classificacao = classificar_oportunidade_stock(
            livro_maior_procura
        )[0]

        if maior_procura_classificacao == "Stock suficiente":
            recomendacoes.append(
                f"Manter {livro_maior_procura['titulo']} sob monitorização: é o livro com maior procura, "
                "mas o stock atual é suficiente e não exige aumento imediato."
            )
        else:
            recomendacoes.append(
                f"Dar prioridade comercial a {livro_maior_procura['titulo']}, por apresentar a maior procura média mensal."
            )

    if not sem_procura_lista.empty:
        recomendacoes.append(
            "Evitar reforçar o stock dos livros sem procura recente antes de nova avaliação."
        )

    if not recomendacoes:
        recomendacoes.append(
            "O stock encontra-se equilibrado e não existem ações prioritárias neste momento."
        )

    resumo_cards = [
        {
            "titulo": "Críticos",
            "valor": str(len(criticos)),
            "descricao": "Livros com reposição urgente.",
            "classe": "danger",
        },
        {
            "titulo": "Alertas Ativos",
            "valor": (
                f"{percentagem_alerta:.1f}%"
                .replace(".", ",")
            ),
            "descricao": f"{len(alertas)} de {total_livros} livro(s) estão em Crítico ou Atenção.",
            "classe": "warning",
        },
        {
            "titulo": "Maior Procura",
            "valor": (
                livro_maior_procura["titulo"]
                if livro_maior_procura is not None
                else "—"
            ),
            "descricao": (
                f"Média de {formatar_numero_simples(livro_maior_procura['media_mensal_vendas'])} unidade(s)/mês."
                if livro_maior_procura is not None
                else "Sem dados suficientes."
            ),
            "classe": "success",
        },
        {
            "titulo": "Reposição Recomendada",
            "valor": str(unidades_repor),
            "descricao": "Total de unidades sugeridas para reposição.",
            "classe": "info",
        },
    ]

    alertas_tabela = alertas.copy()

    if not alertas_tabela.empty:
        alertas_tabela = alertas_tabela.assign(
            prioridade=alertas_tabela["nivel"].map({
                "Crítico": 0,
                "Atenção": 1,
            }).fillna(2)
        ).sort_values(
            by=[
                "prioridade",
                "meses_cobertura",
                "titulo",
            ],
            na_position="last",
        )

    resumo_cards = [
        {
            "titulo": "Críticos",
            "valor": str(len(criticos)),
            "subtexto": "reposições urgentes",
            "classe": "danger",
        },
        {
            "titulo": "Atenção",
            "valor": str(len(atencao)),
            "subtexto": "livros a acompanhar",
            "classe": "warning",
        },
        {
            "titulo": "Alertas",
            "valor": (
                f"{percentagem_alerta:.1f}%"
                .replace(".", ",")
            ),
            "subtexto": f"{len(alertas)} de {total_livros} livros",
            "classe": "info",
        },
        {
            "titulo": "Repor",
            "valor": str(unidades_repor),
            "subtexto": "unidades recomendadas",
            "classe": "success",
        },
    ]

    insights_compactos = [
        {
            "titulo": "Maior prioridade",
            "valor": (
                livro_mais_urgente["titulo"]
                if livro_mais_urgente is not None
                else "Sem prioridade crítica"
            ),
            "detalhe": (
                f"Cobertura de {formatar_numero_simples(livro_mais_urgente['meses_cobertura'])} mês(es)."
                if livro_mais_urgente is not None
                else "Não existem livros em Crítico ou Atenção."
            ),
            "classe": "danger",
        },
        {
            "titulo": "Maior procura",
            "valor": (
                livro_maior_procura["titulo"]
                if livro_maior_procura is not None
                else "Sem dados"
            ),
            "detalhe": (
                f"{formatar_numero_simples(livro_maior_procura['media_mensal_vendas'])} unidade(s) por mês."
                if livro_maior_procura is not None
                else "Não existem dados suficientes."
            ),
            "classe": "success",
        },
        {
            "titulo": "Melhor reforço",
            "valor": (
                melhor_reforco["titulo"]
                if melhor_reforco is not None
                else "Sem necessidade imediata"
            ),
            "detalhe": (
                f"Cobertura de {formatar_numero_simples(melhor_reforco['meses_cobertura'])} mês(es) com procura de "
                f"{formatar_numero_simples(melhor_reforco['media_mensal_vendas'])} unidade(s)/mês."
                if melhor_reforco is not None
                else "Nenhum livro de alta procura necessita de reforço preventivo neste momento."
            ),
            "classe": "warning",
        },
        {
            "titulo": "Situação geral",
            "valor": f"{len(normais)} normal / {len(sem_procura)} sem procura",
            "detalhe": "O reforço deve privilegiar procura elevada com cobertura baixa.",
            "classe": "neutral",
        },
    ]

    return html.Div(
        className="interpretation-page interpretation-page-v3",
        children=[
            html.Div(
                className="page-header interpretation-header-v3",
                children=[
                    html.Div(
                        children=[
                            html.H2("Interpretação do Stock"),
                            html.P(
                                "Resumo analítico dos alertas, procura e necessidades de reposição."
                            ),
                        ]
                    ),
                    html.Div(
                        className="interpretation-header-status",
                        children=[
                            html.Span(
                                className="interpretation-status-dot"
                            ),
                            html.Span(
                                "Dados atuais"
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="interpretation-kpi-row-v3",
                children=[
                    html.Div(
                        className=f"interpretation-kpi-v3 {card['classe']}",
                        children=[
                            html.Div(
                                className="interpretation-kpi-v3-head",
                                children=[
                                    html.Span(card["titulo"]),
                                    html.Strong(card["valor"]),
                                ],
                            ),
                            html.P(card["subtexto"]),
                        ],
                    )
                    for card in resumo_cards
                ],
            ),
            html.Div(
                className="interpretation-layout-v3",
                children=[
                    html.Div(
                        className="interpretation-main-column-v3",
                        children=[
                            html.Div(
                                className="interpretation-panel-v3",
                                children=[
                                    html.Div(
                                        className="interpretation-panel-title-v3",
                                        children=[
                                            html.Div(
                                                children=[
                                                    html.H3("Alertas Prioritários"),
                                                    html.P(
                                                        "Livros que exigem intervenção com base na cobertura disponível."
                                                    ),
                                                ]
                                            ),
                                            html.Span(
                                                f"{len(alertas)} ativos",
                                                className="interpretation-badge-v3",
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="interpretation-table-wrap-v3",
                                        children=[
                                            html.Table(
                                                className="interpretation-table-v3",
                                                children=[
                                                    html.Thead(
                                                        html.Tr([
                                                            html.Th("Livro"),
                                                            html.Th("Estado"),
                                                            html.Th("Stock"),
                                                            html.Th("Cobertura"),
                                                            html.Th("Repor"),
                                                        ])
                                                    ),
                                                    html.Tbody(
                                                        [
                                                            html.Tr([
                                                                html.Td(
                                                                    linha["titulo"],
                                                                    className="interpretation-book-v3",
                                                                ),
                                                                html.Td(
                                                                    html.Span(
                                                                        linha["nivel"],
                                                                        className=(
                                                                            "interpretation-level-v3 critical"
                                                                            if linha["nivel"] == "Crítico"
                                                                            else "interpretation-level-v3 warning"
                                                                        ),
                                                                    )
                                                                ),
                                                                html.Td(
                                                                    str(
                                                                        int(linha["stock_disponivel"])
                                                                        if pd.notna(linha["stock_disponivel"])
                                                                        else 0
                                                                    )
                                                                ),
                                                                html.Td(
                                                                    formatar_numero_simples(
                                                                        linha["meses_cobertura"]
                                                                    )
                                                                ),
                                                                html.Td(
                                                                    str(
                                                                        int(linha["quantidade_recomendada"])
                                                                        if pd.notna(linha["quantidade_recomendada"])
                                                                        else 0
                                                                    )
                                                                ),
                                                            ])
                                                            for _, linha in alertas_tabela.iterrows()
                                                        ]
                                                        if not alertas_tabela.empty
                                                        else [
                                                            html.Tr([
                                                                html.Td(
                                                                    "Não existem alertas ativos.",
                                                                    colSpan=5,
                                                                    className="interpretation-empty-v3",
                                                                )
                                                            ])
                                                        ]
                                                    ),
                                                ],
                                            )
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="interpretation-panel-v3",
                                children=[
                                    html.Div(
                                        className="interpretation-panel-title-v3",
                                        children=[
                                            html.Div(
                                                children=[
                                                    html.H3("Mais Vendidos e Oportunidades de Stock"),
                                                    html.P(
                                                        "Livros com maior procura recente e indicação automática sobre a necessidade de reforço."
                                                    ),
                                                ]
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="interpretation-table-wrap-v3 compact",
                                        children=[
                                            html.Table(
                                                className="interpretation-table-v3 performance",
                                                children=[
                                                    html.Thead(
                                                        html.Tr([
                                                            html.Th("Livro"),
                                                            html.Th("Média/mês"),
                                                            html.Th("Stock"),
                                                            html.Th("Cobertura"),
                                                            html.Th("Sugestão"),
                                                        ])
                                                    ),
                                                    html.Tbody(
                                                        [
                                                            html.Tr([
                                                                html.Td(
                                                                    linha["titulo"],
                                                                    className="interpretation-book-v3",
                                                                ),
                                                                html.Td(
                                                                    formatar_numero_simples(
                                                                        linha["media_mensal_vendas"]
                                                                    )
                                                                ),
                                                                html.Td(
                                                                    str(
                                                                        int(linha["stock_disponivel"])
                                                                        if pd.notna(linha["stock_disponivel"])
                                                                        else 0
                                                                    )
                                                                ),
                                                                html.Td(
                                                                    formatar_numero_simples(
                                                                        linha["meses_cobertura"]
                                                                    )
                                                                ),
                                                                html.Td(
                                                                    html.Span(
                                                                        linha["sugestao_stock"],
                                                                        className=(
                                                                            "interpretation-suggestion-v3 "
                                                                            + linha["classe_sugestao_stock"]
                                                                        ),
                                                                    )
                                                                ),
                                                            ])
                                                            for _, linha in top_procura.iterrows()
                                                        ]
                                                        if not top_procura.empty
                                                        else [
                                                            html.Tr([
                                                                html.Td(
                                                                    "Não existem dados suficientes de procura neste momento.",
                                                                    colSpan=5,
                                                                    className="interpretation-empty-v3",
                                                                )
                                                            ])
                                                        ]
                                                    ),
                                                ],
                                            )
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="interpretation-side-column-v3",
                        children=[
                            html.Div(
                                className="interpretation-panel-v3",
                                children=[
                                    html.Div(
                                        className="interpretation-panel-title-v3",
                                        children=[
                                            html.Div(
                                                children=[
                                                    html.H3("Diagnóstico Rápido"),
                                                    html.P(
                                                        "Leitura direta da situação atual do stock."
                                                    ),
                                                ]
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="interpretation-diagnostic-list-v3",
                                        children=[
                                            html.Div(
                                                className=f"interpretation-diagnostic-v3 {item['classe']}",
                                                children=[
                                                    html.Div(
                                                        className="interpretation-diagnostic-main-v3",
                                                        children=[
                                                            html.Span(item["titulo"]),
                                                            html.Strong(item["valor"]),
                                                        ],
                                                    ),
                                                    html.P(item["detalhe"]),
                                                ],
                                            )
                                            for item in insights_compactos
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="interpretation-panel-v3",
                                children=[
                                    html.Div(
                                        className="interpretation-panel-title-v3",
                                        children=[
                                            html.Div(
                                                children=[
                                                    html.H3("Ações Sugeridas"),
                                                    html.P(
                                                        "Recomendações automáticas com base nos indicadores."
                                                    ),
                                                ]
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="interpretation-actions-v3",
                                        children=[
                                            html.Div(
                                                className="interpretation-action-v3",
                                                children=[
                                                    html.Span(
                                                        str(indice),
                                                        className="interpretation-action-index-v3",
                                                    ),
                                                    html.P(recomendacao),
                                                ],
                                            )
                                            for indice, recomendacao in enumerate(
                                                recomendacoes,
                                                start=1,
                                            )
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def pagina_interpretacao_stock():
    expirar_reservas()
    dados = carregar_alertas_stock()
    stock_completo = carregar_stock_completo()

    return criar_interpretacao_stock(
        dados,
        stock_completo,
    )


def pagina_stock():
    expirar_reservas()
    dados = carregar_alertas_stock()
    stock_completo = carregar_stock_completo()

    total_livros = len(stock_completo)

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
                        "Monitorização do stock disponível e das necessidades de reposição"
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
                        className="chart-panel stock-chart-panel",
                        children=[
                            html.H3(
                                "Procura Mensal vs Stock Disponível"
                            ),
                            dcc.Graph(
                                figure=figura,
                                config={
                                    "displayModeBar": False,
                                },
                                className="stock-chart-graph",
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
                                                "1 unidade disponível ou cobertura inferior a 1 mês"
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
            html.Div(
                className="stock-alert-panel stock-all-panel",
                children=[
                    html.Div(
                        className="panel-heading-row",
                        children=[
                            html.Div(
                                children=[
                                    html.H3("Stock de Todos os Livros"),
                                    html.P(
                                        "O stock físico inclui as unidades reservadas. O disponível corresponde ao que pode ser vendido de imediato.",
                                        className="form-help",
                                    ),
                                ]
                            ),
                        ],
                    ),
                    criar_tabela_stock_completo(
                        stock_completo
                    ),
                ],
            ),
        ]
    )


# Página Exportações

def pagina_exportacoes():
    return html.Div(
        className="export-page",
        children=[
            html.Div(
                className="page-header",
                children=[
                    html.H2("Exportações"),
                    html.P(
                        "Exporta dados do SABIN ou abre o projeto de análise no Power BI."
                    ),
                ],
            ),
            dcc.Download(
                id="download-excel"
            ),
            dcc.Download(
                id="download-pdf"
            ),
            html.Div(
                className="export-actions-grid",
                children=[
                    html.Div(
                        className="export-action-card",
                        children=[
                            html.Div(
                                className="export-action-content",
                                children=[
                                    html.H3(
                                        "Excel"
                                    ),
                                    html.P(
                                        "Exporta os principais dados do sistema para um ficheiro Excel com folhas de resumo, vendas, livros, clientes, stock e previsões."
                                    ),
                                ],
                            ),
                            html.Button(
                                "Exportar Excel",
                                id="export-excel-button",
                                className="export-action-button",
                                n_clicks=0,
                            ),
                        ],
                    ),
                    html.Div(
                        className="export-action-card",
                        children=[
                            html.Div(
                                className="export-action-content",
                                children=[
                                    html.H3(
                                        "Relatório PDF"
                                    ),
                                    html.P(
                                        "Gera um relatório de gestão com os principais indicadores, vendas, stock, reposição e previsão."
                                    ),
                                ],
                            ),
                            html.Button(
                                "Gerar Relatório PDF",
                                id="export-pdf-button",
                                className="export-action-button",
                                n_clicks=0,
                            ),
                        ],
                    ),
                    html.Div(
                        className="export-action-card",
                        children=[
                            html.Div(
                                className="export-action-content",
                                children=[
                                    html.H3(
                                        "Power BI"
                                    ),
                                    html.P(
                                        "Abre o ficheiro do projeto SABIN no Power BI Desktop para consultar os dashboards analíticos."
                                    ),
                                ],
                            ),
                            html.Button(
                                "Abrir Power BI",
                                id="export-powerbi-button",
                                className="export-action-button",
                                n_clicks=0,
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                id="export-message",
                className="export-message",
            ),
        ],
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
        dcc.Store(
            id="current-page-store",
            storage_type="local",
            data="visao-geral",
        ),
        html.Main(
            id="page-content",
            className="content",
            children=html.Div(),
        ),
    ],
)


@app.callback(
    Output(
        "overview-revenue-total",
        "children",
    ),
    Output(
        "overview-sales-count",
        "children",
    ),
    Output(
        "overview-units-count",
        "children",
    ),
    Output(
        "overview-ticket-average",
        "children",
    ),
    Output(
        "overview-revenue-chart",
        "figure",
    ),
    Output(
        "overview-top-chart",
        "figure",
    ),
    Output(
        "overview-last-month",
        "children",
    ),
    Output(
        "overview-last-revenue",
        "children",
    ),
    Output(
        "overview-next-period",
        "children",
    ),
    Output(
        "overview-forecast-revenue",
        "children",
    ),
    Output(
        "overview-forecast-variation",
        "children",
    ),
    Output(
        "overview-forecast-variation",
        "className",
    ),
    Output(
        "overview-stock-critical",
        "children",
    ),
    Output(
        "overview-stock-warning",
        "children",
    ),
    Output(
        "overview-forecast-alert",
        "children",
    ),
    Input(
        "overview-refresh-interval",
        "n_intervals",
    ),
    prevent_initial_call=True,
)
def atualizar_visao_geral_automaticamente(
    n_intervals,
):
    try:
        kpis = carregar_kpis()

        receita_mensal = (
            carregar_receita_mensal()
        )

        top_livros = (
            carregar_top_livros()
        )

        grafico_receita = (
            criar_grafico_receita_mensal(
                receita_mensal
            )
        )

        grafico_top = (
            criar_grafico_top_livros(
                top_livros
            )
        )

        metricas = (
            carregar_metricas_previsao()
            or {}
        )

        stock = (
            carregar_alertas_stock()
        )

        alertas_previsao = (
            carregar_alertas_previsao()
        )

        criticos_stock = len(
            stock[
                stock["nivel"]
                == "Crítico"
            ]
        )

        atencao_stock = len(
            stock[
                stock["nivel"]
                == "Atenção"
            ]
        )

        alerta_critico = (
            alertas_previsao[
                alertas_previsao[
                    "nivel"
                ]
                == "Crítico"
            ]
        )

        mensagem_previsao = (
            "Sem alertas críticos."
        )

        if not alerta_critico.empty:
            mensagem_previsao = (
                alerta_critico
                .iloc[0]["mensagem"]
            )

        variacao = metricas.get(
            "variacao_prevista_percent"
        )

        try:
            variacao_numero = float(
                variacao
            )
        except (
            TypeError,
            ValueError,
        ):
            variacao_numero = 0.0

        classe_variacao = (
            "value-negative"
            if variacao_numero < 0
            else "value-positive"
        )

        return (
            formatar_euro(
                kpis["receita_total"]
            ),
            formatar_inteiro(
                kpis["numero_vendas"]
            ),
            formatar_inteiro(
                kpis[
                    "unidades_vendidas"
                ]
            ),
            formatar_euro(
                kpis["ticket_medio"]
            ),
            grafico_receita,
            grafico_top,
            formatar_mes(
                metricas.get(
                    "ultimo_mes_real"
                )
            ),
            formatar_euro(
                metricas.get(
                    "ultima_receita_real",
                    0,
                )
            ),
            formatar_mes(
                metricas.get(
                    "proximo_mes"
                )
            ),
            formatar_euro(
                metricas.get(
                    "receita_prevista_proximo_mes",
                    0,
                )
            ),
            formatar_percentagem(
                variacao_numero
            ),
            classe_variacao,
            (
                f"{criticos_stock} "
                "livro(s)"
            ),
            (
                f"{atencao_stock} "
                "livro(s)"
            ),
            mensagem_previsao,
        )

    except Exception as erro:
        print(
            "Erro na atualização automática "
            "da Visão Geral:",
            erro,
        )

        return (
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
        )


# Controlos de quantidade

def _ajustar_quantidade(valor_atual, acao, minimo=1):
    try:
        valor = int(valor_atual)
    except (TypeError, ValueError):
        valor = minimo

    if acao and acao.endswith("-minus"):
        valor = max(minimo, valor - 1)
    elif acao and acao.endswith("-plus"):
        valor = valor + 1

    return str(valor)


@app.callback(
    Output("sale-quantity", "value"),
    Input("sale-quantity-minus", "n_clicks"),
    Input("sale-quantity-plus", "n_clicks"),
    State("sale-quantity", "value"),
    prevent_initial_call=True,
)
def alterar_quantidade_venda(menos, mais, valor_atual):
    return _ajustar_quantidade(
        valor_atual,
        ctx.triggered_id,
        minimo=1,
    )


@app.callback(
    Output("management-stock-quantity", "value"),
    Input("management-stock-minus", "n_clicks"),
    Input("management-stock-plus", "n_clicks"),
    State("management-stock-quantity", "value"),
    prevent_initial_call=True,
)
def alterar_quantidade_reposicao(menos, mais, valor_atual):
    return _ajustar_quantidade(
        valor_atual,
        ctx.triggered_id,
        minimo=1,
    )


@app.callback(
    Output("reservation-quantity", "value"),
    Input("reservation-quantity-minus", "n_clicks"),
    Input("reservation-quantity-plus", "n_clicks"),
    State("reservation-quantity", "value"),
    prevent_initial_call=True,
)
def alterar_quantidade_reserva(menos, mais, valor_atual):
    return _ajustar_quantidade(
        valor_atual,
        ctx.triggered_id,
        minimo=1,
    )


@app.callback(
    Output("new-book-stock", "value"),
    Input("new-book-stock-minus", "n_clicks"),
    Input("new-book-stock-plus", "n_clicks"),
    State("new-book-stock", "value"),
    prevent_initial_call=True,
)
def alterar_stock_inicial(menos, mais, valor_atual):
    return _ajustar_quantidade(
        valor_atual,
        ctx.triggered_id,
        minimo=0,
    )


# Navegação

@app.callback(
    Output("submenu-operacoes", "className"),
    Output("operacoes-arrow", "children"),
    Input("toggle-operacoes", "n_clicks"),
    State("submenu-operacoes", "className"),
    prevent_initial_call=True,
)
def alternar_menu_operacoes(
    n_clicks,
    classe_atual,
):
    if classe_atual == "submenu":
        return (
            "submenu collapsed",
            "▾",
        )

    return (
        "submenu",
        "▴",
    )


@app.callback(
    Output("submenu-analises", "className"),
    Output("analises-arrow", "children"),
    Input("toggle-analises", "n_clicks"),
    State("submenu-analises", "className"),
    prevent_initial_call=True,
)
def alternar_menu_analises(
    n_clicks,
    classe_atual,
):
    if classe_atual == "submenu":
        return (
            "submenu collapsed",
            "▾",
        )

    return (
        "submenu",
        "▴",
    )


@app.callback(
    Output("current-page-store", "data"),
    Input("btn-visao-geral", "n_clicks"),
    Input("btn-venda", "n_clicks"),
    Input("btn-reservas", "n_clicks"),
    Input("btn-gestao-catalogo", "n_clicks"),
    Input("btn-catalogo", "n_clicks"),
    Input("btn-previsoes", "n_clicks"),
    Input("btn-stock", "n_clicks"),
    Input("btn-interpretacao-stock", "n_clicks"),
    Input("btn-exportacoes", "n_clicks"),
    prevent_initial_call=True,
)
def guardar_pagina_atual(
    visao,
    venda,
    reservas,
    gestao_catalogo,
    catalogo,
    previsoes,
    stock,
    interpretacao_stock,
    exportacoes,
):
    paginas_por_botao = {
        "btn-visao-geral": "visao-geral",
        "btn-venda": "venda",
        "btn-reservas": "reservas",
        "btn-gestao-catalogo": "gestao-catalogo",
        "btn-catalogo": "catalogo",
        "btn-previsoes": "previsoes",
        "btn-stock": "stock",
        "btn-interpretacao-stock": "interpretacao-stock",
        "btn-exportacoes": "exportacoes",
    }

    return paginas_por_botao.get(
        ctx.triggered_id,
        no_update,
    )


@app.callback(
    Output("page-content", "children"),
    Output("btn-visao-geral", "className"),
    Output("btn-venda", "className"),
    Output("btn-reservas", "className"),
    Output("btn-gestao-catalogo", "className"),
    Output("btn-catalogo", "className"),
    Output("btn-previsoes", "className"),
    Output("btn-stock", "className"),
    Output("btn-interpretacao-stock", "className"),
    Output("btn-exportacoes", "className"),
    Input("current-page-store", "data"),
)
def navegar(
    pagina_atual,
):
    visao_normal = "menu-button"
    visao_ativo = "menu-button active"
    submenu_normal = "submenu-button"
    submenu_ativo = "submenu-button active"

    if pagina_atual == "venda":
        return (
            pagina_registar_venda(),
            visao_normal,
            submenu_ativo,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
        )

    if pagina_atual == "reservas":
        return (
            pagina_reservas(),
            visao_normal,
            submenu_normal,
            submenu_ativo,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
        )

    if pagina_atual == "gestao-catalogo":
        return (
            pagina_gestao_catalogo(),
            visao_normal,
            submenu_normal,
            submenu_normal,
            submenu_ativo,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
        )

    if pagina_atual == "catalogo":
        return (
            pagina_catalogo(),
            visao_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_ativo,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
        )

    if pagina_atual == "previsoes":
        return (
            pagina_previsoes(),
            visao_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_ativo,
            submenu_normal,
            submenu_normal,
            submenu_normal,
        )

    if pagina_atual == "stock":
        return (
            pagina_stock(),
            visao_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_ativo,
            submenu_normal,
            submenu_normal,
        )

    if pagina_atual == "interpretacao-stock":
        return (
            pagina_interpretacao_stock(),
            visao_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_ativo,
            submenu_normal,
        )

    if pagina_atual == "exportacoes":
        return (
            pagina_exportacoes(),
            visao_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_normal,
            submenu_ativo,
        )

    return (
        pagina_visao_geral(),
        visao_ativo,
        submenu_normal,
        submenu_normal,
        submenu_normal,
        submenu_normal,
        submenu_normal,
        submenu_normal,
        submenu_normal,
        submenu_normal,
    )


# Exportações

@app.callback(
    Output("download-excel", "data"),
    Output("download-pdf", "data"),
    Output("export-message", "children"),
    Input("export-excel-button", "n_clicks"),
    Input("export-pdf-button", "n_clicks"),
    Input("export-powerbi-button", "n_clicks"),
    prevent_initial_call=True,
)
def processar_exportacoes(
    excel_clicks,
    pdf_clicks,
    powerbi_clicks,
):
    acao = ctx.triggered_id

    try:
        if acao == "export-excel-button":
            caminho = gerar_excel()

            return (
                dcc.send_file(str(caminho)),
                no_update,
                html.Div(
                    "Excel gerado com sucesso.",
                    className="sale-success-message",
                ),
            )

        if acao == "export-pdf-button":
            caminho = gerar_pdf()

            return (
                no_update,
                dcc.send_file(str(caminho)),
                html.Div(
                    "Relatório PDF gerado com sucesso.",
                    className="sale-success-message",
                ),
            )

        if acao == "export-powerbi-button":
            caminho = abrir_power_bi()

            return (
                no_update,
                no_update,
                html.Div(
                    f"Power BI aberto: {caminho.name}",
                    className="sale-success-message",
                ),
            )

    except Exception as erro:
        print(
            "Erro na área de exportações:",
            erro,
        )

        return (
            no_update,
            no_update,
            html.Div(
                str(erro),
                className="sale-error-message",
            ),
        )

    return (
        no_update,
        no_update,
        no_update,
    )


# Quantidade da venda

@app.callback(
    Output("reservation-message", "children"),
    Output("reservation-refresh-store", "data"),
    Input("reservation-submit", "n_clicks"),
    Input("reservation-cancel", "n_clicks"),
    State("reservation-client", "value"),
    State("reservation-book", "value"),
    State("reservation-quantity", "value"),
    State("reservation-limit-date", "date"),
    State("reservation-active", "value"),
    State("reservation-refresh-store", "data"),
    prevent_initial_call=True,
)
def gerir_reserva(
    criar_click,
    cancelar_click,
    cliente_id,
    livro_id,
    quantidade,
    data_limite,
    reserva_id,
    refresh,
):
    acao = ctx.triggered_id
    refresh = int(refresh or 0)

    try:
        if acao == "reservation-submit":
            criar_reserva(
                cliente_id,
                livro_id,
                quantidade,
                data_limite,
            )
            mensagem = "Reserva criada com sucesso."

        elif acao == "reservation-cancel":
            if not reserva_id:
                raise ValueError(
                    "Seleciona uma reserva pendente."
                )

            atualizar_status_reserva(
                reserva_id,
                "Cancelada",
            )
            mensagem = "Reserva cancelada com sucesso."

        else:
            return "", refresh

    except ValueError as erro:
        return (
            html.Div(
                str(erro),
                className="sale-error-message",
            ),
            refresh,
        )
    except Exception as erro:
        print("Erro ao gerir reserva:", erro)
        return (
            html.Div(
                "Não foi possível concluir a operação.",
                className="sale-error-message",
            ),
            refresh,
        )

    solicitar_atualizacao_analitica()

    return (
        html.Div(
            mensagem,
            className="sale-success-message",
        ),
        refresh + 1,
    )


@app.callback(
    Output("reservation-client", "options"),
    Output("reservation-book", "options"),
    Output("reservation-active", "options"),
    Output("reservation-table-container", "children"),
    Input("reservation-refresh-store", "data"),
)
def atualizar_pagina_reservas(refresh):
    reservas = carregar_reservas()
    clientes = carregar_clientes_reserva()
    livros = carregar_livros_reserva()

    opcoes_clientes = [
        {
            "label": f"{c['nome_completo']} — NIF {c['nif']}",
            "value": c["id"],
        }
        for c in clientes
    ]

    opcoes_livros = [
        {
            "label": (
                f"{l['titulo']} — ISBN {l['isbn']} — "
                f"{l['stock_disponivel']} disponíveis"
            ),
            "value": l["id"],
        }
        for l in livros
        if int(l["stock_disponivel"]) > 0
    ]

    opcoes_pendentes = [
        {
            "label": (
                f"#{r['id']} — {r['cliente']} — {r['livro']}"
            ),
            "value": r["id"],
        }
        for r in reservas
        if r["status"] == "Pendente"
    ]

    return (
        opcoes_clientes,
        opcoes_livros,
        opcoes_pendentes,
        criar_tabela_reservas(reservas),
    )


def _normalizar_genero_texto(valor):
    texto = unicodedata.normalize(
        "NFKD",
        str(valor or "").lower(),
    )
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def inferir_generos_api(assuntos):
    if not assuntos:
        return []

    texto_assuntos = " | ".join(
        _normalizar_genero_texto(assunto)
        for assunto in assuntos
        if assunto
    )

    palavras_por_genero = {
        "Ficção": [
            "fiction",
            "novel",
            "romans nouvelles",
            "ficcao",
            "literatura ficcional",
        ],
        "Distopia": [
            "dystopia",
            "dystopian",
            "distopia",
        ],
        "Romance": [
            "romance",
            "love stories",
            "love romance",
            "love fiction",
            "historia de amor",
        ],
        "Policial": [
            "detective",
            "mystery",
            "crime",
            "investigation",
            "police",
            "policial",
            "misterio",
            "investigacao",
        ],
        "Poesia": [
            "poetry",
            "poems",
            "poesia",
            "poemas",
        ],
        "Fantasia": [
            "fantasy",
            "magic",
            "fairies",
            "faerie",
            "fantastique",
            "fantasia",
            "magia",
        ],
        "Terror": [
            "horror",
            "ghost",
            "supernatural",
            "occult",
            "terror",
            "fantasmas",
            "sobrenatural",
        ],
        "Ficção Científica": [
            "science fiction",
            "sci fi",
            "space opera",
            "ficcao cientifica",
        ],
        "Suspense": [
            "thriller",
            "suspense",
        ],
        "Autoajuda": [
            "self help",
            "personal development",
            "self improvement",
            "autoajuda",
            "desenvolvimento pessoal",
        ],
        "Biografia": [
            "biography",
            "autobiography",
            "memoir",
            "biografia",
            "autobiografia",
            "memorias",
        ],
        "Infantil": [
            "children s fiction",
            "children fiction",
            "juvenile works",
            "infantil",
            "ficcao infantil",
            "literatura infantil",
            "juvenil",
            "literatura juvenil",
        ],
        "Aventura": [
            "adventure",
            "action adventure",
            "aventura",
            "aventuras",
        ],
        "Realismo Mágico": [
            "magical realism",
            "magic realism",
            "realismo magico",
        ],
    }

    generos_disponiveis = carregar_generos_gestao()
    ids_por_nome = {
        genero["nome"]: genero["id"]
        for genero in generos_disponiveis
    }

    encontrados = []

    for nome_genero, palavras in palavras_por_genero.items():
        if nome_genero not in ids_por_nome:
            continue

        if any(
            _normalizar_genero_texto(palavra) in texto_assuntos
            for palavra in palavras
        ):
            encontrados.append(ids_por_nome[nome_genero])

    return encontrados


def normalizar_data_api(valor):
    if not valor:
        return None

    texto = str(valor).strip()

    if re.fullmatch(r"\d{4}", texto):
        return f"{texto}-01-01"

    data_convertida = pd.to_datetime(
        texto,
        errors="coerce",
    )

    if pd.isna(data_convertida):
        return None

    return data_convertida.strftime("%Y-%m-%d")


@app.callback(
    Output("new-book-title", "value"),
    Output("new-book-authors", "value"),
    Output("new-book-publisher", "value"),
    Output("new-book-date", "date"),
    Output("new-book-genres", "value"),
    Output("new-book-api-message", "children"),
    Input("new-book-isbn", "value"),
    prevent_initial_call=True,
)
def preencher_novo_livro_por_isbn(isbn):
    isbn_limpo = re.sub(
        r"[^0-9Xx]",
        "",
        str(isbn or ""),
    ).upper()

    # Enquanto o ISBN ainda está incompleto, limpa os dados do livro anterior.
    if len(isbn_limpo) not in (10, 13):
        return (
            "",
            "",
            "",
            None,
            [],
            "",
        )

    try:
        resultado = procurar_livro(
            isbn_limpo
        )
    except Exception as erro:
        print(
            "Erro ao consultar ISBN:",
            erro,
        )

        return (
            "",
            "",
            "",
            None,
            [],
            html.Div(
                "Não foi possível consultar o ISBN agora. Podes preencher os dados manualmente.",
                className="sale-neutral-message compact-message",
            ),
        )

    if not resultado.get("sucesso"):
        return (
            "",
            "",
            "",
            None,
            [],
            html.Div(
                "ISBN não encontrado. Podes preencher os dados manualmente.",
                className="sale-neutral-message compact-message",
            ),
        )

    origem = resultado.get("origem")

    autores = resultado.get("autores") or []

    if isinstance(autores, str):
        autores_texto = autores.strip()
    else:
        autores_texto = ", ".join(
            str(autor).strip()
            for autor in autores
            if autor
        )

    genero_ids = inferir_generos_api(
        resultado.get("generos") or []
    )

    titulo = (
        str(
            resultado.get("titulo")
            or ""
        ).strip()
    )

    editora = (
        str(
            resultado.get("editora")
            or ""
        ).strip()
    )

    data_publicacao = normalizar_data_api(
        resultado.get("data_publicacao")
    )

    if origem == "Base de Dados Local":
        return (
            titulo,
            autores_texto,
            editora,
            data_publicacao,
            genero_ids,
            html.Div(
                "Este ISBN já existe no catálogo.",
                className="sale-error-message compact-message",
            ),
        )

    nome_origem = origem or "fonte externa"

    campos_em_falta = []

    if not titulo:
        campos_em_falta.append("Título")

    if not autores_texto:
        campos_em_falta.append("Autor(es)")

    if not editora:
        campos_em_falta.append("Editora")

    if not data_publicacao:
        campos_em_falta.append("Data de publicação")

    if not genero_ids:
        campos_em_falta.append("Género(s)")

    if campos_em_falta:
        mensagem = (
            f"Dados parcialmente encontrados em {nome_origem}. "
            f"Em falta: {', '.join(campos_em_falta)}. "
            "Preenche ou confirma os campos antes de adicionar o livro."
        )
        classe_mensagem = (
            "sale-neutral-message compact-message"
        )
    else:
        mensagem = (
            f"Dados encontrados em {nome_origem} "
            "e preenchidos automaticamente."
        )
        classe_mensagem = (
            "sale-success-message compact-message"
        )

    # Importante: devolve valores vazios quando a fonte não encontrou
    # um campo. Não usa no_update, para não manter dados do ISBN anterior.
    return (
        titulo,
        autores_texto,
        editora,
        data_publicacao,
        genero_ids,
        html.Div(
            mensagem,
            className=classe_mensagem,
        ),
    )


# Gestão de Catálogo

@app.callback(
    Output("management-book", "options"),
    Input("management-refresh-store", "data"),
    Input("management-edit-refresh-store", "data"),
)
def atualizar_opcoes_livros_gestao(refresh, edit_refresh):
    livros = carregar_livros_gestao()

    return [
        {
            "label": (
                f"{livro['titulo']} — "
                f"{livro['isbn']}"
            ),
            "value": livro["id"],
        }
        for livro in livros
    ]


@app.callback(
    Output("management-book-info", "children"),
    Output("management-stock-history", "children"),
    Output("management-price-history", "children"),
    Input("management-book", "value"),
    Input("management-refresh-store", "data"),
    Input("management-edit-refresh-store", "data"),
)
def atualizar_gestao_catalogo(
    livro_id,
    refresh,
    edit_refresh,
):
    if not livro_id:
        vazio_stock = html.Div(
            "Seleciona um livro para consultar o histórico.",
            className="empty-cart",
        )

        vazio_preco = html.Div(
            "Seleciona um livro para consultar o histórico.",
            className="empty-cart",
        )

        return (
            "",
            vazio_stock,
            vazio_preco,
        )

    livro = obter_livro_gestao(
        livro_id
    )

    if not livro:
        erro = html.Div(
            "Livro não encontrado.",
            className="sale-error-message",
        )

        return (
            erro,
            "",
            "",
        )

    info = html.Div(
        children=[
            html.Div(
                className="sale-book-summary management-summary",
                children=[
                    html.Div(
                        children=[
                            html.Span("Preço atual"),
                            html.Strong(
                                formatar_euro(
                                    livro["preco_venda"]
                                )
                            ),
                        ]
                    ),
                    html.Div(
                        children=[
                            html.Span("Stock físico"),
                            html.Strong(
                                str(livro["estoque_atual"])
                            ),
                        ]
                    ),
                    html.Div(
                        children=[
                            html.Span("Reservado"),
                            html.Strong(
                                str(livro["qtd_reservada"])
                            ),
                        ]
                    ),
                    html.Div(
                        children=[
                            html.Span("Disponível p/ venda"),
                            html.Strong(
                                str(livro["stock_disponivel"])
                            ),
                        ]
                    ),
                    html.Div(
                        children=[
                            html.Span("ISBN"),
                            html.Strong(livro["isbn"]),
                        ]
                    ),
                    html.Div(
                        children=[
                            html.Span("Editora"),
                            html.Strong(
                                livro["editora"] or "—"
                            ),
                        ]
                    ),
                ],
            ),
            html.P(
                "Disponível para venda = stock físico − unidades reservadas.",
                className="stock-explanation",
            ),
        ]
    )

    movimentos = consultar_movimentos_stock(
        livro_id,
        limite=10,
    )

    historico = consultar_historico_precos(
        livro_id,
        limite=10,
    )

    return (
        info,
        criar_tabela_movimentos_stock(
            movimentos
        ),
        criar_tabela_historico_precos(
            historico
        ),
    )


@app.callback(
    Output("management-edit-title", "value"),
    Output("management-edit-isbn", "value"),
    Output("management-edit-publisher", "value"),
    Output("management-edit-date", "date"),
    Output("management-edit-authors", "value"),
    Output("management-edit-genres", "value"),
    Input("management-book", "value"),
    Input("management-edit-refresh-store", "data"),
)
def preencher_formulario_edicao(livro_id, edit_refresh):
    if not livro_id:
        return "", "", "", None, "", []

    livro = obter_livro_gestao(livro_id)

    if not livro:
        return "", "", "", None, "", []

    return (
        livro["titulo"],
        livro["isbn"],
        livro["editora"] or "",
        livro["data_publicacao"],
        livro.get("autores_texto") or "",
        livro.get("genero_ids") or [],
    )


@app.callback(
    Output("management-edit-message", "children"),
    Output("management-edit-refresh-store", "data"),
    Input("management-edit-submit", "n_clicks"),
    State("management-book", "value"),
    State("management-edit-title", "value"),
    State("management-edit-isbn", "value"),
    State("management-edit-publisher", "value"),
    State("management-edit-date", "date"),
    State("management-edit-authors", "value"),
    State("management-edit-genres", "value"),
    State("management-edit-refresh-store", "data"),
    prevent_initial_call=True,
)
def guardar_edicao_livro(
    n_clicks,
    livro_id,
    titulo,
    isbn,
    editora,
    data_publicacao,
    autores,
    genero_ids,
    refresh,
):
    if not livro_id:
        return (
            html.Div(
                "Seleciona primeiro um livro.",
                className="sale-error-message",
            ),
            int(refresh or 0),
        )

    try:
        atualizar_livro(
            livro_id=livro_id,
            titulo=titulo,
            isbn=isbn,
            editora=editora,
            data_publicacao=data_publicacao,
            autores_texto=autores,
            genero_ids=genero_ids,
        )
    except ValueError as erro:
        return (
            html.Div(
                str(erro),
                className="sale-error-message",
            ),
            int(refresh or 0),
        )
    except Exception as erro:
        print("Erro ao editar livro:", erro)
        return (
            html.Div(
                "Não foi possível guardar as alterações.",
                className="sale-error-message",
            ),
            int(refresh or 0),
        )

    try:
        solicitar_atualizacao_analitica()
    except Exception as erro:
        print(
            "Erro ao atualizar análises após editar livro:",
            erro,
        )

    return (
        html.Div(
            "Informações atualizadas com sucesso.",
            className="sale-success-message",
        ),
        int(refresh or 0) + 1,
    )


@app.callback(
    Output("management-stock-message", "children"),
    Output("management-price-message", "children"),
    Output("management-add-message", "children"),
    Output("management-refresh-store", "data"),
    Output("management-book", "value"),
    Input("management-stock-submit", "n_clicks"),
    Input("management-price-submit", "n_clicks"),
    Input("management-add-book-submit", "n_clicks"),
    State("management-book", "value"),
    State("management-stock-quantity", "value"),
    State("management-stock-observation", "value"),
    State("management-price-input", "value"),
    State("new-book-title", "value"),
    State("new-book-isbn", "value"),
    State("new-book-price", "value"),
    State("new-book-stock", "value"),
    State("new-book-publisher", "value"),
    State("new-book-date", "date"),
    State("new-book-authors", "value"),
    State("new-book-genres", "value"),
    State("management-refresh-store", "data"),
    prevent_initial_call=True,
)
def gerir_catalogo_operacional(
    repor,
    atualizar_preco_click,
    adicionar_click,
    livro_id,
    quantidade,
    observacao,
    novo_preco,
    novo_titulo,
    novo_isbn,
    novo_livro_preco,
    novo_stock,
    nova_editora,
    nova_data,
    novos_autores,
    novos_generos,
    refresh,
):
    acao = ctx.triggered_id
    refresh = int(refresh or 0)

    if acao == "management-stock-submit":
        if not livro_id:
            return (
                html.Div(
                    "Seleciona primeiro um livro.",
                    className="sale-error-message",
                ),
                "",
                "",
                refresh,
                livro_id,
            )

        try:
            repor_stock(
                livro_id,
                quantidade,
                observacao,
            )
        except ValueError as erro:
            return (
                html.Div(
                    str(erro),
                    className="sale-error-message",
                ),
                "",
                "",
                refresh,
                livro_id,
            )
        except Exception as erro:
            print(
                "Erro ao repor stock:",
                erro,
            )
            return (
                html.Div(
                    "Não foi possível repor o stock.",
                    className="sale-error-message",
                ),
                "",
                "",
                refresh,
                livro_id,
            )

        try:
            solicitar_atualizacao_analitica()
        except Exception as erro:
            print(
                "Erro ao atualizar análises após reposição:",
                erro,
            )

        return (
            html.Div(
                "Stock reposto com sucesso.",
                className="sale-success-message",
            ),
            "",
            "",
            refresh + 1,
            livro_id,
        )

    if acao == "management-price-submit":
        if not livro_id:
            return (
                "",
                html.Div(
                    "Seleciona primeiro um livro.",
                    className="sale-error-message",
                ),
                "",
                refresh,
                livro_id,
            )

        try:
            alterar_preco(
                livro_id,
                novo_preco,
            )
        except ValueError as erro:
            return (
                "",
                html.Div(
                    str(erro),
                    className="sale-error-message",
                ),
                "",
                refresh,
                livro_id,
            )
        except Exception as erro:
            print(
                "Erro ao alterar preço:",
                erro,
            )
            return (
                "",
                html.Div(
                    "Não foi possível alterar o preço.",
                    className="sale-error-message",
                ),
                "",
                refresh,
                livro_id,
            )

        try:
            solicitar_atualizacao_analitica()
        except Exception as erro:
            print(
                "Erro ao atualizar análises após alteração de preço:",
                erro,
            )

        return (
            "",
            html.Div(
                "Preço atualizado com sucesso.",
                className="sale-success-message",
            ),
            "",
            refresh + 1,
            livro_id,
        )

    if acao == "management-add-book-submit":
        try:
            resultado = adicionar_livro(
                titulo=novo_titulo,
                isbn=novo_isbn,
                preco_venda=novo_livro_preco,
                estoque_inicial=novo_stock,
                editora=nova_editora,
                data_publicacao=nova_data,
                autores_texto=novos_autores,
                genero_ids=novos_generos,
            )
        except ValueError as erro:
            return (
                "",
                "",
                html.Div(
                    str(erro),
                    className="sale-error-message",
                ),
                refresh,
                livro_id,
            )
        except Exception as erro:
            print(
                "Erro ao adicionar livro:",
                erro,
            )
            return (
                "",
                "",
                html.Div(
                    "Não foi possível adicionar o livro.",
                    className="sale-error-message",
                ),
                refresh,
                livro_id,
            )

        try:
            solicitar_atualizacao_analitica()
        except Exception as erro:
            print(
                "Erro ao atualizar análises após adicionar livro:",
                erro,
            )

        return (
            "",
            "",
            html.Div(
                "Livro adicionado com sucesso.",
                className="sale-success-message",
            ),
            refresh + 1,
            resultado["livro_id"],
        )

    return (
        "",
        "",
        "",
        refresh,
        livro_id,
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

            if origem != "Base de Dados Local":
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
                    "ISBN não encontrado no catálogo local nem nas fontes externas.",
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


# Novo cliente na venda

@app.callback(
    Output("sale-new-client-form", "className"),
    Input("sale-client", "value"),
)
def mostrar_formulario_novo_cliente(cliente_id):
    if cliente_id == "novo_cliente":
        return "new-client-form"

    return "new-client-form hidden"


@app.callback(
    Output("sale-client", "options"),
    Output("sale-client", "value"),
    Output("sale-new-client-message", "children"),
    Input("sale-new-client-submit", "n_clicks"),
    State("sale-new-client-name", "value"),
    State("sale-new-client-nif", "value"),
    State("sale-new-client-phone", "value"),
    State("sale-new-client-email", "value"),
    State("sale-client", "options"),
    prevent_initial_call=True,
)
def criar_cliente_na_venda(
    n_clicks,
    nome,
    nif,
    telemovel,
    email,
    opcoes_atuais,
):
    try:
        resultado = adicionar_cliente(
            nome,
            nif,
            telemovel,
            email,
        )
    except ValueError as erro:
        return (
            opcoes_atuais,
            "novo_cliente",
            html.Div(
                str(erro),
                className="sale-error-message",
            ),
        )
    except Exception as erro:
        print("Erro ao adicionar cliente:", erro)
        return (
            opcoes_atuais,
            "novo_cliente",
            html.Div(
                "Não foi possível adicionar o cliente.",
                className="sale-error-message",
            ),
        )

    return (
        criar_opcoes_clientes_venda(),
        resultado["cliente_id"],
        html.Div(
            "Cliente adicionado com sucesso.",
            className="sale-success-message",
        ),
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

        if cliente_id == "novo_cliente":
            return (
                carrinho,
                "",
                html.Div(
                    "Guarda primeiro os dados do novo cliente.",
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
            print(
                "Erro ao registar venda:",
                erro,
            )
            return (
                carrinho,
                "",
                html.Div(
                    "Não foi possível registar a venda.",
                    className="sale-error-message",
                ),
            )

        try:
            solicitar_atualizacao_analitica()
        except Exception as erro:
            print(
                "Erro ao atualizar análises após venda:",
                erro,
            )

        mensagem_final = html.Div(
            className="sale-final-success",
            children=[
                html.Strong(
                    "Venda registada com sucesso."
                ),
                html.Span(
                    f"Total: {formatar_euro(resultado['total'])}"
                ),
            ],
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
        debug=False
    )
