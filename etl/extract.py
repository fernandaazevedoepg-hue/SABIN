import os
import re

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine


# Carrega as configurações da ligação à base de dados.
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não foi encontrada no ficheiro .env"
    )


# Esquema do Data Warehouse. Por omissão é o dw; pode apontar-se para um
# esquema de teste (ex.: DW_SCHEMA=dw_teste) sem alterar o código.
DW_SCHEMA = os.getenv("DW_SCHEMA", "dw")

if not re.fullmatch(r"[a-z_][a-z0-9_]*", DW_SCHEMA):
    raise RuntimeError(
        f"DW_SCHEMA inválido: {DW_SCHEMA!r}"
    )


# Ligação usada pelas etapas de extração e carga.
engine = create_engine(DATABASE_URL)


def extrair_tabela(nome_tabela):
    """Devolve os registos de uma tabela operacional num DataFrame."""

    query = f"SELECT * FROM public.{nome_tabela};"

    df = pd.read_sql(query, engine)

    return df


def main():

    tabelas = [
        "vendas",
        "itens_venda",
        "livros",
        "clientes",
        "autores",
        "generos",
        "livro_autores",
        "livro_generos",
    ]

    print("SABIN - ETL | EXTRAÇÃO")

    dados = {}

    for tabela in tabelas:
        df = extrair_tabela(tabela)

        dados[tabela] = df

        print(
            f"{tabela:<12} -> {len(df)} linha(s)"
        )

    # Verifica a estrutura e a qualidade dos dados extraídos.

    vendas = dados["vendas"]
    itens_venda = dados["itens_venda"]


    print("\nPrimeiras vendas:")
    print(vendas.head())


    print("\nTipos de dados de vendas:")
    print(vendas.dtypes)


    print("\nVendas por status:")
    print(vendas["status"].value_counts(dropna=False))


    print("\nVendas sem cliente identificado:")
    print(vendas["cliente_id"].isna().sum())


    print("\nValores nulos em itens_venda:")
    print(itens_venda.isna().sum())


if __name__ == "__main__":
    main()