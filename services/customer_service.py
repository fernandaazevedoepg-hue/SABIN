import os
import re

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


def adicionar_cliente(
    nome_completo,
    nif,
    telemovel=None,
    email=None,
):
    nome_completo = (
        str(nome_completo).strip()
        if nome_completo is not None
        else ""
    )

    nif = re.sub(
        r"\D",
        "",
        str(nif or ""),
    )

    telemovel = (
        str(telemovel).strip()
        if telemovel and str(telemovel).strip()
        else None
    )

    email = (
        str(email).strip().lower()
        if email and str(email).strip()
        else None
    )

    if not nome_completo:
        raise ValueError(
            "Indica o nome completo do cliente."
        )

    if len(nif) != 9:
        raise ValueError(
            "O NIF deve ter 9 dígitos."
        )

    if email:
        email_valido = re.fullmatch(
            r"[^\s@]+@[^\s@]+\.[^\s@]+",
            email,
        )

        if not email_valido:
            raise ValueError(
                "Indica um email válido."
            )

    with engine.begin() as connection:
        cliente_existente = (
            connection.execute(
                text("""
                    SELECT id
                    FROM public.clientes
                    WHERE nif = :nif;
                """),
                {
                    "nif": nif,
                },
            )
            .mappings()
            .first()
        )

        if cliente_existente:
            raise ValueError(
                "Já existe um cliente com este NIF."
            )

        if email:
            email_existente = (
                connection.execute(
                    text("""
                        SELECT id
                        FROM public.clientes
                        WHERE LOWER(email) = LOWER(:email);
                    """),
                    {
                        "email": email,
                    },
                )
                .mappings()
                .first()
            )

            if email_existente:
                raise ValueError(
                    "Já existe um cliente com este email."
                )

        resultado = (
            connection.execute(
                text("""
                    INSERT INTO public.clientes (
                        nome_completo,
                        nif,
                        telemovel,
                        email
                    )
                    VALUES (
                        :nome_completo,
                        :nif,
                        :telemovel,
                        :email
                    )
                    RETURNING id, nome_completo, nif;
                """),
                {
                    "nome_completo": nome_completo,
                    "nif": nif,
                    "telemovel": telemovel,
                    "email": email,
                },
            )
            .mappings()
            .one()
        )

    return {
        "sucesso": True,
        "cliente_id": int(resultado["id"]),
        "nome_completo": resultado["nome_completo"],
        "nif": resultado["nif"],
    }
