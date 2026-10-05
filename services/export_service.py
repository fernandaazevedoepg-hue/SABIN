from datetime import datetime
from pathlib import Path
import os
import subprocess
import sys

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table as ExcelTable
from openpyxl.worksheet.table import TableStyleInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
EXPORTS_DIR = BASE_DIR / "exports"
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL não encontrada no ficheiro .env"
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

AZUL_ESCURO = "1F3A5F"
AZUL_CLARO = "EAF1FF"
CINZA_CLARO = "F4F7FB"
CINZA_BORDA = "D8E0EA"
TEXTO = "172033"

BORDA = Side(
    style="thin",
    color=CINZA_BORDA,
)


def ler_df(sql):
    with engine.connect() as connection:
        return pd.read_sql(
            text(sql),
            connection,
        )


def carregar_kpis():
    linha = ler_df(
        """
        SELECT
            COALESCE(SUM(iv.subtotal), 0) AS receita_total,
            COUNT(DISTINCT v.id) AS numero_vendas,
            COALESCE(SUM(iv.quantidade), 0) AS unidades_vendidas
        FROM public.vendas v
        JOIN public.itens_venda iv
            ON iv.venda_id = v.id
        WHERE v.status = 'Concluída';
        """
    ).iloc[0]

    receita = float(
        linha["receita_total"]
    )

    vendas = int(
        linha["numero_vendas"]
    )

    unidades = int(
        linha["unidades_vendidas"]
    )

    return {
        "receita_total": receita,
        "numero_vendas": vendas,
        "unidades_vendidas": unidades,
        "ticket_medio": (
            receita / vendas
            if vendas
            else 0
        ),
    }


def carregar_metricas():
    try:
        dados = ler_df(
            """
            SELECT *
            FROM dw.metricas_previsao
            LIMIT 1;
            """
        )

        if dados.empty:
            return {}

        linha = dados.iloc[0]

        return {
            coluna: linha[coluna]
            for coluna in dados.columns
            if pd.notna(
                linha[coluna]
            )
        }

    except Exception as erro:
        print(
            "Erro ao carregar métricas:",
            erro,
        )

        return {}


def carregar_vendas():
    return ler_df(
        """
        SELECT
            v.data_venda AS data,
            v.id AS venda_id,
            iv.id AS item_venda_id,
            COALESCE(
                c.nome_completo,
                'Cliente não identificado'
            ) AS cliente,
            l.titulo AS livro,
            l.isbn,
            v.metodo_pagamento,
            iv.quantidade,
            iv.preco_unitario,
            iv.subtotal
        FROM public.vendas v
        JOIN public.itens_venda iv
            ON iv.venda_id = v.id
        JOIN public.livros l
            ON l.id = iv.livro_id
        LEFT JOIN public.clientes c
            ON c.id = v.cliente_id
        WHERE v.status = 'Concluída'
        ORDER BY
            v.data_venda,
            v.id,
            iv.id;
        """
    )


def carregar_livros():
    return ler_df(
        """
        SELECT
            l.id,
            l.titulo,
            l.isbn,
            l.editora,
            l.data_publicacao,
            l.preco_venda,
            l.estoque_atual AS stock_fisico,
            l.qtd_reservada AS reservado,
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
                ''
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
                ''
            ) AS generos

        FROM public.livros l
        ORDER BY l.titulo;
        """
    )


def carregar_clientes():
    return ler_df(
        """
        SELECT
            id,
            nome_completo,
            nif,
            telemovel,
            email,
            data_registo,
            total_compras_valor,
            total_compras_qtd
        FROM public.clientes
        ORDER BY nome_completo;
        """
    )


def carregar_stock():
    return ler_df(
        """
        SELECT
            titulo,
            estoque_atual AS stock_fisico,
            qtd_reservada AS reservado,
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
                WHEN nivel = 'Crítico'
                    THEN 1

                WHEN nivel = 'Atenção'
                    THEN 2

                WHEN nivel = 'Normal'
                    THEN 3

                ELSE 4
            END,
            meses_cobertura NULLS LAST,
            titulo;
        """
    )


def carregar_previsoes():
    return ler_df(
        """
        SELECT
            mes,
            receita_real,
            receita_prevista,
            tipo
        FROM dw.previsao_receita
        ORDER BY mes;
        """
    )


def dados_exportacao():
    return {
        "kpis": carregar_kpis(),
        "metricas": carregar_metricas(),
        "Vendas": carregar_vendas(),
        "Livros": carregar_livros(),
        "Clientes": carregar_clientes(),
        "Stock": carregar_stock(),
        "Previsoes": carregar_previsoes(),
    }


def valor_excel(valor):
    if valor is None:
        return None

    if pd.isna(valor):
        return None

    if isinstance(
        valor,
        pd.Timestamp,
    ):
        valor = valor.to_pydatetime()

    if (
        isinstance(valor, datetime)
        and valor.tzinfo is not None
    ):
        valor = valor.replace(
            tzinfo=None
        )

    return valor


def aplicar_borda(celula):
    celula.border = Border(
        left=BORDA,
        right=BORDA,
        top=BORDA,
        bottom=BORDA,
    )


def titulo_folha(
    folha,
    ultima_coluna,
    titulo,
    descricao,
):
    folha.merge_cells(
        start_row=1,
        start_column=1,
        end_row=1,
        end_column=ultima_coluna,
    )

    folha["A1"] = titulo

    folha["A1"].font = Font(
        bold=True,
        size=18,
        color="FFFFFF",
    )

    folha["A1"].fill = PatternFill(
        "solid",
        fgColor=AZUL_ESCURO,
    )

    folha["A1"].alignment = Alignment(
        vertical="center",
    )

    folha.row_dimensions[1].height = 30

    folha.merge_cells(
        start_row=2,
        start_column=1,
        end_row=2,
        end_column=ultima_coluna,
    )

    folha["A2"] = (
        f"{descricao} | "
        f"Gerado em "
        f"{datetime.now().strftime('%d/%m/%Y às %H:%M')}"
    )

    folha["A2"].font = Font(
        italic=True,
        size=10,
        color="58677C",
    )


def criar_resumo_excel(
    workbook,
    dados,
):
    folha = workbook.active

    folha.title = "Resumo"

    folha.sheet_view.showGridLines = False

    titulo_folha(
        folha,
        4,
        "SABIN — Relatório de Gestão",
        "Resumo executivo da Bookmarked",
    )

    kpis = dados["kpis"]
    metricas = dados["metricas"]
    stock = dados["Stock"]

    folha["A4"] = "Indicadores principais"

    folha["A4"].font = Font(
        bold=True,
        size=13,
        color=TEXTO,
    )

    cards = [
        (
            1,
            "Receita Total",
            kpis["receita_total"],
            '#,##0.00 [$€-pt-PT]',
        ),
        (
            2,
            "Número de Vendas",
            kpis["numero_vendas"],
            "#,##0",
        ),
        (
            3,
            "Unidades Vendidas",
            kpis["unidades_vendidas"],
            "#,##0",
        ),
        (
            4,
            "Ticket Médio",
            kpis["ticket_medio"],
            '#,##0.00 [$€-pt-PT]',
        ),
    ]

    for (
        coluna,
        titulo,
        valor,
        formato,
    ) in cards:

        titulo_cell = folha.cell(
            5,
            coluna,
            titulo,
        )

        valor_cell = folha.cell(
            6,
            coluna,
            valor,
        )

        for celula in (
            titulo_cell,
            valor_cell,
        ):
            celula.fill = PatternFill(
                "solid",
                fgColor=CINZA_CLARO,
            )

            celula.alignment = Alignment(
                horizontal="center",
                vertical="center",
            )

            aplicar_borda(
                celula
            )

        titulo_cell.font = Font(
            bold=True,
            size=9,
            color="5C6B80",
        )

        valor_cell.font = Font(
            bold=True,
            size=14,
            color=AZUL_ESCURO,
        )

        valor_cell.number_format = (
            formato
        )

    folha.row_dimensions[5].height = 24
    folha.row_dimensions[6].height = 32

    folha["A9"] = (
        "Previsão e qualidade do modelo"
    )

    folha["A9"].font = Font(
        bold=True,
        size=13,
        color=TEXTO,
    )

    previsao = [
        (
            "Próximo Período",
            metricas.get(
                "proximo_mes"
            ),
            "mm/yyyy",
        ),
        (
            "Receita Prevista",
            metricas.get(
                "receita_prevista_proximo_mes"
            ),
            '#,##0.00 [$€-pt-PT]',
        ),
        (
            "Variação Prevista",
            metricas.get(
                "variacao_prevista_percent"
            ),
            '0.00"%"',
        ),
        (
            "Tendência",
            metricas.get(
                "tendencia"
            ),
            "General",
        ),
        (
            "Modelo",
            metricas.get(
                "modelo"
            ),
            "General",
        ),
        (
            "MAE",
            metricas.get(
                "mae"
            ),
            '#,##0.00 [$€-pt-PT]',
        ),
        (
            "RMSE",
            metricas.get(
                "rmse"
            ),
            '#,##0.00 [$€-pt-PT]',
        ),
        (
            "R²",
            metricas.get(
                "r2"
            ),
            "0.0000",
        ),
    ]

    for indice, (
        titulo,
        valor,
        formato,
    ) in enumerate(previsao):

        if indice < 4:
            coluna = 1
            linha = 10 + indice
        else:
            coluna = 3
            linha = 10 + (
                indice - 4
            )

        titulo_cell = folha.cell(
            linha,
            coluna,
            titulo,
        )

        valor_cell = folha.cell(
            linha,
            coluna + 1,
            valor_excel(valor),
        )

        titulo_cell.font = Font(
            bold=True,
            color=TEXTO,
        )

        titulo_cell.fill = PatternFill(
            "solid",
            fgColor=AZUL_CLARO,
        )

        valor_cell.fill = PatternFill(
            "solid",
            fgColor="FFFFFF",
        )

        valor_cell.number_format = (
            formato
        )

        aplicar_borda(
            titulo_cell
        )

        aplicar_borda(
            valor_cell
        )

    folha["A16"] = (
        "Stock e reposição"
    )

    folha["A16"].font = Font(
        bold=True,
        size=13,
        color=TEXTO,
    )

    if stock.empty:
        criticos = 0
        atencao = 0
        repor = 0

    else:
        criticos = int(
            (
                stock["nivel"]
                == "Crítico"
            ).sum()
        )

        atencao = int(
            (
                stock["nivel"]
                == "Atenção"
            ).sum()
        )

        repor = int(
            stock[
                "quantidade_recomendada"
            ]
            .fillna(0)
            .sum()
        )

    stock_cards = [
        (
            1,
            "Livros Analisados",
            len(stock),
        ),
        (
            2,
            "Críticos",
            criticos,
        ),
        (
            3,
            "Em Atenção",
            atencao,
        ),
        (
            4,
            "Unidades a Repor",
            repor,
        ),
    ]

    for (
        coluna,
        titulo,
        valor,
    ) in stock_cards:

        titulo_cell = folha.cell(
            17,
            coluna,
            titulo,
        )

        valor_cell = folha.cell(
            18,
            coluna,
            valor,
        )

        for celula in (
            titulo_cell,
            valor_cell,
        ):
            celula.fill = PatternFill(
                "solid",
                fgColor=CINZA_CLARO,
            )

            celula.alignment = Alignment(
                horizontal="center",
            )

            aplicar_borda(
                celula
            )

        titulo_cell.font = Font(
            bold=True,
            size=9,
            color="5C6B80",
        )

        valor_cell.font = Font(
            bold=True,
            size=14,
            color=AZUL_ESCURO,
        )

    for coluna in (
        "A",
        "B",
        "C",
        "D",
    ):
        folha.column_dimensions[
            coluna
        ].width = 24

    folha.freeze_panes = "A4"


def criar_folha_dados(
    workbook,
    nome,
    dataframe,
    mapa,
    titulo,
    descricao,
):
    folha = workbook.create_sheet(
        nome
    )

    folha.sheet_view.showGridLines = (
        False
    )

    dados = dataframe.rename(
        columns=mapa
    ).copy()

    cabecalhos = list(
        dados.columns
    )

    ultima_coluna = max(
        1,
        len(cabecalhos),
    )

    titulo_folha(
        folha,
        ultima_coluna,
        titulo,
        descricao,
    )

    for coluna, cabecalho in enumerate(
        cabecalhos,
        1,
    ):
        celula = folha.cell(
            4,
            coluna,
            cabecalho,
        )

        celula.font = Font(
            bold=True,
            color="FFFFFF",
        )

        celula.fill = PatternFill(
            "solid",
            fgColor=AZUL_ESCURO,
        )

        celula.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

        aplicar_borda(
            celula
        )

    for linha_excel, (
        _,
        linha,
    ) in enumerate(
        dados.iterrows(),
        5,
    ):

        for (
            coluna_excel,
            valor,
        ) in enumerate(
            linha,
            1,
        ):
            celula = folha.cell(
                linha_excel,
                coluna_excel,
                valor_excel(valor),
            )

            celula.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

            aplicar_borda(
                celula
            )

    if not dados.empty:
        referencia = (
            f"A4:"
            f"{get_column_letter(ultima_coluna)}"
            f"{folha.max_row}"
        )

        tabela = ExcelTable(
            displayName=(
                f"Tabela{nome}"
            ),
            ref=referencia,
        )

        tabela.tableStyleInfo = (
            TableStyleInfo(
                name="TableStyleMedium2",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )
        )

        folha.add_table(
            tabela
        )

    formatos = {
        "Data":
            "dd/mm/yyyy",

        "Data de Publicação":
            "dd/mm/yyyy",

        "Data de Registo":
            "dd/mm/yyyy",

        "Período":
            "mm/yyyy",

        "Preço Unitário (€)":
            '#,##0.00 [$€-pt-PT]',

        "Subtotal (€)":
            '#,##0.00 [$€-pt-PT]',

        "Preço de Venda (€)":
            '#,##0.00 [$€-pt-PT]',

        "Total Compras (€)":
            '#,##0.00 [$€-pt-PT]',

        "Receita Real (€)":
            '#,##0.00 [$€-pt-PT]',

        "Receita Prevista (€)":
            '#,##0.00 [$€-pt-PT]',

        "Média Mensal de Vendas":
            "0.00",

        "Cobertura (Meses)":
            "0.00",
    }

    for indice, cabecalho in enumerate(
        cabecalhos,
        1,
    ):
        if cabecalho in formatos:
            for linha in range(
                5,
                folha.max_row + 1,
            ):
                folha.cell(
                    linha,
                    indice,
                ).number_format = (
                    formatos[
                        cabecalho
                    ]
                )

        maior = len(
            cabecalho
        )

        for linha in range(
            5,
            folha.max_row + 1,
        ):
            valor = folha.cell(
                linha,
                indice,
            ).value

            if valor is not None:
                maior = max(
                    maior,
                    len(
                        str(valor)
                    ),
                )

        folha.column_dimensions[
            get_column_letter(indice)
        ].width = min(
            max(
                maior + 2,
                12,
            ),
            42,
        )

    folha.freeze_panes = "A5"


def gerar_excel():
    EXPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    dados = dados_exportacao()

    timestamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    caminho = (
        EXPORTS_DIR
        / (
            "SABIN_Relatorio_Gestao_"
            f"{timestamp}.xlsx"
        )
    )

    workbook = Workbook()

    criar_resumo_excel(
        workbook,
        dados,
    )

    configuracoes = {
        "Vendas": (
            {
                "data":
                    "Data",

                "venda_id":
                    "ID Venda",

                "item_venda_id":
                    "ID Item",

                "cliente":
                    "Cliente",

                "livro":
                    "Livro",

                "isbn":
                    "ISBN",

                "metodo_pagamento":
                    "Método de Pagamento",

                "quantidade":
                    "Quantidade",

                "preco_unitario":
                    "Preço Unitário (€)",

                "subtotal":
                    "Subtotal (€)",
            },
            "Vendas Concluídas",
            (
                "Detalhe dos itens "
                "pertencentes às vendas "
                "concluídas."
            ),
        ),

        "Livros": (
            {
                "id":
                    "ID",

                "titulo":
                    "Título",

                "isbn":
                    "ISBN",

                "editora":
                    "Editora",

                "data_publicacao":
                    "Data de Publicação",

                "preco_venda":
                    "Preço de Venda (€)",

                "stock_fisico":
                    "Stock Físico",

                "reservado":
                    "Reservado",

                "stock_disponivel":
                    "Stock Disponível",

                "autores":
                    "Autores",

                "generos":
                    "Géneros",
            },
            "Catálogo de Livros",
            (
                "Informação atual do catálogo "
                "e da disponibilidade de stock."
            ),
        ),

        "Clientes": (
            {
                "id":
                    "ID",

                "nome_completo":
                    "Nome",

                "nif":
                    "NIF",

                "telemovel":
                    "Telemóvel",

                "email":
                    "Email",

                "data_registo":
                    "Data de Registo",

                "total_compras_valor":
                    "Total Compras (€)",

                "total_compras_qtd":
                    "Quantidade de Compras",
            },
            "Clientes",
            (
                "Informação dos clientes "
                "registados na Bookmarked."
            ),
        ),

        "Stock": (
            {
                "titulo":
                    "Livro",

                "stock_fisico":
                    "Stock Físico",

                "reservado":
                    "Reservado",

                "stock_disponivel":
                    "Stock Disponível",

                "unidades_ultimos_3_meses":
                    "Unidades Últimos 3 Meses",

                "media_mensal_vendas":
                    "Média Mensal de Vendas",

                "meses_cobertura":
                    "Cobertura (Meses)",

                "quantidade_recomendada":
                    "Quantidade a Repor",

                "nivel":
                    "Nível",

                "recomendacao":
                    "Recomendação",
            },
            "Stock e Reposição",
            (
                "Indicadores utilizados "
                "para análise de cobertura "
                "e reposição."
            ),
        ),

        "Previsoes": (
            {
                "mes":
                    "Período",

                "receita_real":
                    "Receita Real (€)",

                "receita_prevista":
                    "Receita Prevista (€)",

                "tipo":
                    "Tipo",
            },
            "Previsões de Receita",
            (
                "Histórico observado e "
                "estimativas produzidas "
                "pelo modelo preditivo."
            ),
        ),
    }

    for nome, (
        mapa,
        titulo,
        descricao,
    ) in configuracoes.items():

        criar_folha_dados(
            workbook,
            nome,
            dados[nome],
            mapa,
            titulo,
            descricao,
        )

    workbook.save(
        caminho
    )

    return caminho


def euro(valor):
    if (
        valor is None
        or pd.isna(valor)
    ):
        return "—"

    return (
        f"{float(valor):,.2f} €"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", " ")
    )


def numero(valor):
    if (
        valor is None
        or pd.isna(valor)
    ):
        return "—"

    return (
        f"{int(valor):,}"
        .replace(",", " ")
    )


def decimal(
    valor,
    casas=2,
):
    if (
        valor is None
        or pd.isna(valor)
    ):
        return "—"

    return (
        f"{float(valor):.{casas}f}"
        .replace(".", ",")
    )


def mes(valor):
    if (
        valor is None
        or pd.isna(valor)
    ):
        return "—"

    return (
        pd.to_datetime(valor)
        .strftime("%m/%Y")
    )


def estilo_tabela_pdf():
    return TableStyle(
        [
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor(
                    "#1F3A5F"
                ),
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white,
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold",
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.35,
                colors.HexColor(
                    "#D8E0EA"
                ),
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                6,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                6,
            ),
        ]
    )


def rodape_pdf(
    canvas,
    documento,
):
    canvas.saveState()

    canvas.setStrokeColor(
        colors.HexColor(
            "#D8E0EA"
        )
    )

    canvas.line(
        documento.leftMargin,
        12 * mm,
        A4[0]
        - documento.rightMargin,
        12 * mm,
    )

    canvas.setFont(
        "Helvetica",
        8,
    )

    canvas.setFillColor(
        colors.HexColor(
            "#6B778C"
        )
    )

    canvas.drawString(
        documento.leftMargin,
        7.5 * mm,
        "SABIN — Business Intelligence",
    )

    canvas.drawRightString(
        A4[0]
        - documento.rightMargin,
        7.5 * mm,
        f"Página {documento.page}",
    )

    canvas.restoreState()


def gerar_pdf():
    EXPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    dados = dados_exportacao()

    kpis = dados["kpis"]
    metricas = dados["metricas"]
    stock = dados["Stock"]
    vendas = dados["Vendas"]

    timestamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    caminho = (
        EXPORTS_DIR
        / (
            "SABIN_Relatorio_Gestao_"
            f"{timestamp}.pdf"
        )
    )

    documento = SimpleDocTemplate(
        str(caminho),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=(
            "SABIN - Relatório de Gestão"
        ),
        author="SABIN",
    )

    estilos = (
        getSampleStyleSheet()
    )

    titulo = ParagraphStyle(
        "Titulo",
        parent=estilos["Title"],
        alignment=TA_CENTER,
        fontSize=21,
        leading=24,
        textColor=colors.HexColor(
            "#172033"
        ),
        spaceAfter=2 * mm,
    )

    centro = ParagraphStyle(
        "Centro",
        parent=estilos["BodyText"],
        alignment=TA_CENTER,
        fontSize=9.5,
        textColor=colors.HexColor(
            "#5C6B80"
        ),
    )

    secao = ParagraphStyle(
        "Secao",
        parent=estilos["Heading2"],
        fontSize=12.5,
        leading=15,
        textColor=colors.HexColor(
            "#172033"
        ),
        spaceBefore=5 * mm,
        spaceAfter=2.5 * mm,
    )

    normal = ParagraphStyle(
        "Normal",
        parent=estilos["BodyText"],
        fontSize=8.8,
        leading=12,
        textColor=colors.HexColor(
            "#243044"
        ),
    )

    label = ParagraphStyle(
        "Label",
        parent=normal,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=7.5,
        textColor=colors.HexColor(
            "#5C6B80"
        ),
    )

    valor = ParagraphStyle(
        "Valor",
        parent=normal,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=12.5,
        textColor=colors.HexColor(
            "#1F3A5F"
        ),
    )

    elementos = [
        Paragraph(
            "SABIN",
            titulo,
        ),
        Paragraph(
            "Relatório de Gestão da Bookmarked",
            centro,
        ),
        Paragraph(
            (
                "Gerado em "
                + datetime.now().strftime(
                    "%d/%m/%Y às %H:%M"
                )
            ),
            centro,
        ),
        Spacer(
            1,
            5 * mm,
        ),
        Paragraph(
            "Indicadores principais",
            secao,
        ),
    ]

    cards = Table(
        [
            [
                Paragraph(
                    "Receita Total",
                    label,
                ),
                Paragraph(
                    "Número de Vendas",
                    label,
                ),
                Paragraph(
                    "Unidades Vendidas",
                    label,
                ),
                Paragraph(
                    "Ticket Médio",
                    label,
                ),
            ],
            [
                Paragraph(
                    euro(
                        kpis[
                            "receita_total"
                        ]
                    ),
                    valor,
                ),
                Paragraph(
                    numero(
                        kpis[
                            "numero_vendas"
                        ]
                    ),
                    valor,
                ),
                Paragraph(
                    numero(
                        kpis[
                            "unidades_vendidas"
                        ]
                    ),
                    valor,
                ),
                Paragraph(
                    euro(
                        kpis[
                            "ticket_medio"
                        ]
                    ),
                    valor,
                ),
            ],
        ],
        colWidths=[
            44 * mm,
            44 * mm,
            44 * mm,
            44 * mm,
        ],
        rowHeights=[
            10 * mm,
            13 * mm,
        ],
    )

    cards.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor(
                        "#F4F7FB"
                    ),
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor(
                        "#D8E0EA"
                    ),
                ),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor(
                        "#D8E0EA"
                    ),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
            ]
        )
    )

    elementos.append(
        cards
    )

    elementos.append(
        Paragraph(
            "Previsão",
            secao,
        )
    )

    linhas_previsao = [
        [
            "Indicador",
            "Valor",
        ],
        [
            "Próximo período",
            mes(
                metricas.get(
                    "proximo_mes"
                )
            ),
        ],
        [
            "Receita prevista",
            euro(
                metricas.get(
                    "receita_prevista_proximo_mes"
                )
            ),
        ],
        [
            "Variação prevista",
            (
                f"{decimal(
                    metricas.get(
                        'variacao_prevista_percent'
                    )
                )}%"
            ),
        ],
        [
            "Tendência",
            str(
                metricas.get(
                    "tendencia",
                    "—",
                )
            ),
        ],
        [
            "Modelo",
            str(
                metricas.get(
                    "modelo",
                    "—",
                )
            ),
        ],
        [
            "MAE",
            euro(
                metricas.get(
                    "mae"
                )
            ),
        ],
        [
            "RMSE",
            euro(
                metricas.get(
                    "rmse"
                )
            ),
        ],
        [
            "R²",
            decimal(
                metricas.get(
                    "r2"
                ),
                4,
            ),
        ],
    ]

    tabela_previsao = Table(
        linhas_previsao,
        colWidths=[
            85 * mm,
            91 * mm,
        ],
        repeatRows=1,
    )

    tabela_previsao.setStyle(
        estilo_tabela_pdf()
    )

    elementos.append(
        tabela_previsao
    )

    elementos.append(
        Paragraph(
            "Stock e reposição",
            secao,
        )
    )

    if stock.empty:
        elementos.append(
            Paragraph(
                (
                    "Não existem dados "
                    "de stock disponíveis."
                ),
                normal,
            )
        )

    else:
        criticos = stock[
            stock["nivel"]
            == "Crítico"
        ]

        atencao = stock[
            stock["nivel"]
            == "Atenção"
        ]

        total_repor = int(
            stock[
                "quantidade_recomendada"
            ]
            .fillna(0)
            .sum()
        )

        elementos.append(
            Paragraph(
                (
                    f"Foram analisados "
                    f"<b>{len(stock)}</b> livros. "
                    f"Existem "
                    f"<b>{len(criticos)}</b> "
                    f"livro(s) em estado crítico, "
                    f"<b>{len(atencao)}</b> "
                    f"em atenção e uma recomendação "
                    f"total de reposição de "
                    f"<b>{total_repor}</b> unidade(s)."
                ),
                normal,
            )
        )

        alertas = stock[
            stock["nivel"].isin(
                [
                    "Crítico",
                    "Atenção",
                ]
            )
        ].head(12)

        if not alertas.empty:
            linhas = [
                [
                    "Livro",
                    "Nível",
                    "Stock",
                    "Cobertura",
                    "Repor",
                ]
            ]

            for _, linha in (
                alertas.iterrows()
            ):
                linhas.append(
                    [
                        str(
                            linha[
                                "titulo"
                            ]
                        ),
                        str(
                            linha[
                                "nivel"
                            ]
                        ),
                        numero(
                            linha[
                                "stock_disponivel"
                            ]
                        ),
                        decimal(
                            linha[
                                "meses_cobertura"
                            ]
                        ),
                        numero(
                            linha[
                                "quantidade_recomendada"
                            ]
                        ),
                    ]
                )

            tabela = Table(
                linhas,
                colWidths=[
                    78 * mm,
                    25 * mm,
                    20 * mm,
                    28 * mm,
                    24 * mm,
                ],
                repeatRows=1,
            )

            tabela.setStyle(
                estilo_tabela_pdf()
            )

            elementos.append(
                Spacer(
                    1,
                    2.5 * mm,
                )
            )

            elementos.append(
                tabela
            )

    elementos.append(
        Paragraph(
            "Top 5 livros mais vendidos",
            secao,
        )
    )

    if vendas.empty:
        elementos.append(
            Paragraph(
                "Não existem vendas disponíveis.",
                normal,
            )
        )

    else:
        top = (
            vendas
            .groupby(
                "livro",
                as_index=False,
            )["quantidade"]
            .sum()
            .sort_values(
                "quantidade",
                ascending=False,
            )
            .head(5)
        )

        linhas = [
            [
                "Livro",
                "Unidades Vendidas",
            ]
        ]

        for _, linha in (
            top.iterrows()
        ):
            linhas.append(
                [
                    str(
                        linha["livro"]
                    ),
                    numero(
                        linha[
                            "quantidade"
                        ]
                    ),
                ]
            )

        tabela = Table(
            linhas,
            colWidths=[
                136 * mm,
                40 * mm,
            ],
            repeatRows=1,
        )

        tabela.setStyle(
            estilo_tabela_pdf()
        )

        elementos.append(
            tabela
        )

    elementos.extend(
        [
            Spacer(
                1,
                4 * mm,
            ),
            Paragraph(
                (
                    "Relatório gerado automaticamente "
                    "pelo SABIN. Os indicadores de "
                    "vendas refletem as vendas concluídas "
                    "no momento da exportação. "
                    "As previsões devem ser interpretadas "
                    "como informação de apoio à decisão."
                ),
                normal,
            ),
        ]
    )

    documento.build(
        elementos,
        onFirstPage=rodape_pdf,
        onLaterPages=rodape_pdf,
    )

    return caminho


def encontrar_ficheiro_power_bi():
    caminho_env = os.getenv(
        "POWER_BI_FILE"
    )

    if caminho_env:
        caminho = Path(
            caminho_env
        )

        if not caminho.is_absolute():
            caminho = (
                BASE_DIR
                / caminho
            )

        if (
            caminho.exists()
            and caminho.suffix.lower()
            == ".pbix"
        ):
            return caminho

    caminho_sabin = (
        BASE_DIR
        / "powerbi"
        / "sabin.pbix"
    )

    if caminho_sabin.exists():
        return caminho_sabin

    candidatos = []

    pasta_power_bi = (
        BASE_DIR
        / "powerbi"
    )

    if pasta_power_bi.exists():
        candidatos.extend(
            arquivo
            for arquivo
            in pasta_power_bi.iterdir()
            if (
                arquivo.is_file()
                and arquivo.suffix.lower()
                == ".pbix"
            )
        )

    candidatos.extend(
        arquivo
        for arquivo
        in BASE_DIR.iterdir()
        if (
            arquivo.is_file()
            and arquivo.suffix.lower()
            == ".pbix"
        )
    )

    if not candidatos:
        raise FileNotFoundError(
            "Não foi encontrado nenhum ficheiro "
            "Power BI (.pbix). Confirma se existe "
            "SABIN/powerbi/sabin.pbix."
        )

    return sorted(
        candidatos,
        key=lambda item: (
            item.name.lower()
        ),
    )[0]


def abrir_power_bi():
    caminho = (
        encontrar_ficheiro_power_bi()
    )

    if sys.platform.startswith(
        "win"
    ):
        os.startfile(
            str(caminho)
        )

    elif sys.platform == "darwin":
        subprocess.Popen(
            [
                "open",
                str(caminho),
            ]
        )

    else:
        subprocess.Popen(
            [
                "xdg-open",
                str(caminho),
            ]
        )

    return caminho