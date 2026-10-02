import os
from datetime import date

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


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


def expirar_reservas():
    with engine.begin() as connection:
        connection.execute(
            text("""
                UPDATE public.reservas
                SET status = 'Expirada'
                WHERE status = 'Pendente'
                  AND data_limite < CURRENT_DATE;
            """)
        )


def carregar_clientes_reserva():
    query = text("""
        SELECT
            id,
            nome_completo,
            nif
        FROM public.clientes
        ORDER BY nome_completo;
    """)

    with engine.connect() as connection:
        resultados = (
            connection.execute(query)
            .mappings()
            .all()
        )

    return [dict(resultado) for resultado in resultados]


def carregar_livros_reserva():
    query = text("""
        SELECT
            id,
            titulo,
            isbn,
            estoque_atual,
            qtd_reservada,
            GREATEST(
                estoque_atual - qtd_reservada,
                0
            ) AS stock_disponivel
        FROM public.livros
        ORDER BY titulo;
    """)

    with engine.connect() as connection:
        resultados = (
            connection.execute(query)
            .mappings()
            .all()
        )

    return [dict(resultado) for resultado in resultados]


def carregar_reservas():
    expirar_reservas()

    query = text("""
        SELECT
            r.id,
            r.cliente_id,
            c.nome_completo AS cliente,
            r.livro_id,
            l.titulo AS livro,
            l.isbn,
            r.quantidade,
            r.data_reserva,
            r.data_limite,
            r.status
        FROM public.reservas r
        JOIN public.clientes c
            ON c.id = r.cliente_id
        JOIN public.livros l
            ON l.id = r.livro_id
        ORDER BY
            CASE WHEN r.status = 'Pendente' THEN 0 ELSE 1 END,
            r.data_limite ASC,
            r.id DESC;
    """)

    with engine.connect() as connection:
        resultados = (
            connection.execute(query)
            .mappings()
            .all()
        )

    return [dict(resultado) for resultado in resultados]


def criar_reserva(
    cliente_id,
    livro_id,
    quantidade,
    data_limite,
):
    if not cliente_id:
        raise ValueError(
            "Seleciona um cliente."
        )

    if not livro_id:
        raise ValueError(
            "Seleciona um livro."
        )

    try:
        quantidade = int(quantidade)
    except (TypeError, ValueError):
        raise ValueError(
            "Indica uma quantidade válida."
        )

    if quantidade <= 0:
        raise ValueError(
            "A quantidade deve ser superior a zero."
        )

    if not data_limite:
        raise ValueError(
            "Seleciona a data limite da reserva."
        )

    try:
        limite = date.fromisoformat(
            str(data_limite)
        )
    except ValueError:
        raise ValueError(
            "A data limite não é válida."
        )

    if limite < date.today():
        raise ValueError(
            "A data limite não pode estar no passado."
        )

    expirar_reservas()

    with engine.begin() as connection:
        livro = (
            connection.execute(
                text("""
                    SELECT
                        id,
                        titulo,
                        estoque_atual,
                        qtd_reservada,
                        GREATEST(
                            estoque_atual - qtd_reservada,
                            0
                        ) AS stock_disponivel
                    FROM public.livros
                    WHERE id = :livro_id
                    FOR UPDATE;
                """),
                {
                    "livro_id": int(livro_id),
                },
            )
            .mappings()
            .first()
        )

        if not livro:
            raise ValueError(
                "Livro não encontrado."
            )

        if quantidade > int(livro["stock_disponivel"]):
            raise ValueError(
                "Não existe stock disponível suficiente para esta reserva."
            )

        cliente = connection.execute(
            text("""
                SELECT id
                FROM public.clientes
                WHERE id = :cliente_id;
            """),
            {
                "cliente_id": int(cliente_id),
            },
        ).first()

        if not cliente:
            raise ValueError(
                "Cliente não encontrado."
            )

        reserva = (
            connection.execute(
                text("""
                    INSERT INTO public.reservas (
                        cliente_id,
                        livro_id,
                        quantidade,
                        status,
                        data_limite
                    )
                    VALUES (
                        :cliente_id,
                        :livro_id,
                        :quantidade,
                        'Pendente',
                        :data_limite
                    )
                    RETURNING id;
                """),
                {
                    "cliente_id": int(cliente_id),
                    "livro_id": int(livro_id),
                    "quantidade": quantidade,
                    "data_limite": limite,
                },
            )
            .mappings()
            .one()
        )

    return {
        "sucesso": True,
        "reserva_id": int(reserva["id"]),
    }


def atualizar_status_reserva(
    reserva_id,
    novo_status,
):
    if novo_status not in {
        "Concluída",
        "Cancelada",
    }:
        raise ValueError(
            "Estado de reserva inválido."
        )

    with engine.begin() as connection:
        reserva = (
            connection.execute(
                text("""
                    SELECT
                        id,
                        status
                    FROM public.reservas
                    WHERE id = :reserva_id
                    FOR UPDATE;
                """),
                {
                    "reserva_id": int(reserva_id),
                },
            )
            .mappings()
            .first()
        )

        if not reserva:
            raise ValueError(
                "Reserva não encontrada."
            )

        if reserva["status"] != "Pendente":
            raise ValueError(
                "Esta reserva já não está pendente."
            )

        connection.execute(
            text("""
                UPDATE public.reservas
                SET status = :novo_status
                WHERE id = :reserva_id;
            """),
            {
                "novo_status": novo_status,
                "reserva_id": int(reserva_id),
            },
        )

    return {
        "sucesso": True,
        "reserva_id": int(reserva_id),
        "status": novo_status,
    }
