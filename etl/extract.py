import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine


# Carrega as variáveis existentes no ficheiro .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não foi encontrada no ficheiro .env"
    )


# Cria a ligação ao PostgreSQL
engine = create_engine(DATABASE_URL)


def extrair_tabela(nome_tabela):

    # Extrai uma tabela do schema public e devolve os dados num DataFrame Pandas.

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

    # INSPEÇÃO DOS DADOS

    vendas = dados["vendas"]
    itens_venda = dados["itens_venda"]
    livros = dados["livros"]
    clientes = dados["clientes"]


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