from sqlalchemy import text

from etl.extract import engine
from services.books_api import (
    limpar_isbn,
    isbn_valido,
    procurar_livro_por_isbn,
)


def procurar_livro_na_base(isbn):
    # Procura o livro na base da Bookmarked
    query = text(
        """
        SELECT
            id,
            titulo,
            isbn,
            editora,
            data_publicacao
        FROM public.livros
        WHERE REPLACE(
            REPLACE(isbn, '-', ''),
            ' ',
            ''
        ) = :isbn
        LIMIT 1;
        """
    )

    with engine.connect() as conn:
        resultado = conn.execute(
            query,
            {"isbn": isbn},
        ).mappings().first()

    if resultado is None:
        return None

    return {
        "sucesso": True,
        "origem": "Base de dados Bookmarked",
        "id": resultado["id"],
        "isbn": resultado["isbn"],
        "titulo": resultado["titulo"],
        "editora": resultado["editora"],
        "data_publicacao": resultado["data_publicacao"],
    }


def procurar_livro(isbn):
    # Limpa o ISBN
    isbn = limpar_isbn(isbn)

    # Valida o ISBN
    if not isbn_valido(isbn):
        return {
            "sucesso": False,
            "erro": "ISBN inválido.",
        }

    # Procura primeiro na Bookmarked
    livro_local = procurar_livro_na_base(isbn)

    if livro_local is not None:
        return livro_local

    # Se não existir localmente, consulta a Open Library
    livro_api = procurar_livro_por_isbn(isbn)

    if not livro_api["sucesso"]:
        return livro_api

    livro_api["origem"] = "Open Library API"

    return livro_api


def mostrar_resultado(livro):
    # Mostra erro caso a pesquisa falhe
    if not livro["sucesso"]:
        print(livro["erro"])
        return

    print()
    print("Livro encontrado:")
    print(f"Origem: {livro['origem']}")
    print(f"ISBN: {livro['isbn']}")
    print(f"Título: {livro['titulo']}")

    if livro["origem"] == "Base de dados Bookmarked":
        print(
            f"Data de publicação original: "
            f"{livro['data_publicacao'] or 'não disponível'}"
        )

    else:
        if livro["autores"]:
            print(
                f"Autor(es): {', '.join(livro['autores'])}"
            )
        else:
            print("Autor(es): não disponível")

        print(
            f"Data da edição: "
            f"{livro['data_publicacao'] or 'não disponível'}"
        )

    print(
        f"Editora: "
        f"{livro['editora'] or 'não disponível'}"
    )


def main():
    print("SABIN - PESQUISA DE CATÁLOGO")

    isbn = input("Introduza o ISBN: ")

    livro = procurar_livro(isbn)

    mostrar_resultado(livro)


if __name__ == "__main__":
    main()