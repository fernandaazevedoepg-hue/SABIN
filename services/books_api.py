import requests


def limpar_isbn(isbn):
    # Remove espaços e hífenes
    return isbn.replace("-", "").replace(" ", "").strip()


def isbn_valido(isbn):
    # Valida ISBN-13
    if len(isbn) == 13:
        if not isbn.isdigit():
            return False

        # ISBN-13 utiliza os prefixos 978 ou 979
        if not isbn.startswith(("978", "979")):
            return False

        soma = 0

        for i, numero in enumerate(isbn[:12]):
            if i % 2 == 0:
                soma += int(numero)
            else:
                soma += int(numero) * 3

        digito_controlo = (10 - soma % 10) % 10

        return digito_controlo == int(isbn[-1])

    # Valida ISBN-10
    if len(isbn) == 10:
        if not isbn[:9].isdigit():
            return False

        ultimo = isbn[-1].upper()

        if not (ultimo.isdigit() or ultimo == "X"):
            return False

        valores = [int(numero) for numero in isbn[:9]]
        valores.append(10 if ultimo == "X" else int(ultimo))

        soma = sum(
            (10 - i) * valor
            for i, valor in enumerate(valores)
        )

        return soma % 11 == 0

    return False


def obter_nome_autor(chave_autor):
    # Consulta os dados de um autor
    url = f"https://openlibrary.org{chave_autor}.json"

    try:
        resposta = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "SABIN-PAP/1.0"
            },
        )

        resposta.raise_for_status()

    except requests.RequestException:
        return None

    dados = resposta.json()

    return dados.get("name")


def procurar_livro_por_isbn(isbn):
    # Prepara e valida o ISBN
    isbn = limpar_isbn(isbn)

    if not isbn_valido(isbn):
        return {
            "sucesso": False,
            "erro": "ISBN inválido.",
        }

    # Consulta diretamente a edição através do ISBN
    url = f"https://openlibrary.org/isbn/{isbn}.json"

    try:
        resposta = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "SABIN-PAP/1.0"
            },
        )

        if resposta.status_code == 404:
            return {
                "sucesso": False,
                "erro": "Livro não encontrado.",
            }

        resposta.raise_for_status()

    except requests.RequestException as erro:
        return {
            "sucesso": False,
            "erro": f"Erro ao comunicar com a API: {erro}",
        }

    dados = resposta.json()

    # Obter os nomes dos autores
    autores = []

    for autor in dados.get("authors", []):
        chave_autor = autor.get("key")

        if chave_autor:
            nome = obter_nome_autor(chave_autor)

            if nome:
                autores.append(nome)

    # Obter editora
    editoras = dados.get("publishers", [])

    editora = editoras[0] if editoras else None

    return {
        "sucesso": True,
        "isbn": isbn,
        "titulo": dados.get("title"),
        "autores": autores,
        "data_publicacao": dados.get("publish_date"),
        "editora": editora,
    }


def mostrar_livro(livro):
    # Mostra erro caso a pesquisa falhe
    if not livro["sucesso"]:
        print(livro["erro"])
        return

    print()
    print("Livro encontrado:")
    print(f"ISBN: {livro['isbn']}")
    print(f"Título: {livro['titulo']}")

    if livro["autores"]:
        print(
            f"Autor(es): {', '.join(livro['autores'])}"
        )
    else:
        print("Autor(es): não disponível")

    print(
        f"Data de publicação: "
        f"{livro['data_publicacao'] or 'não disponível'}"
    )

    print(
        f"Editora: "
        f"{livro['editora'] or 'não disponível'}"
    )


def main():
    print("SABIN - PESQUISA DE LIVROS")

    isbn = input("Introduza o ISBN: ")

    livro = procurar_livro_por_isbn(isbn)

    mostrar_livro(livro)


if __name__ == "__main__":
    main()