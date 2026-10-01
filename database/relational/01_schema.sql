-- Estrutura operacional da livraria Bookmarked


CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS autores (
    id BIGSERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    nacionalidade VARCHAR(80),
    data_nascimento DATE,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS generos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(80) NOT NULL UNIQUE,
    descricao TEXT
);

CREATE TABLE IF NOT EXISTS livros (
    id BIGSERIAL PRIMARY KEY,
    titulo VARCHAR(255) NOT NULL,
    isbn VARCHAR(20) NOT NULL UNIQUE,
    preco_venda NUMERIC(10,2) NOT NULL,
    estoque_atual INTEGER NOT NULL DEFAULT 0,
    total_vendas_acumuladas INTEGER NOT NULL DEFAULT 0,
    qtd_reservada INTEGER NOT NULL DEFAULT 0,
    data_publicacao DATE,
    editora VARCHAR(150),
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS livro_autores (
    livro_id BIGINT NOT NULL REFERENCES livros(id) ON DELETE CASCADE,
    autor_id BIGINT NOT NULL REFERENCES autores(id) ON DELETE CASCADE,
    PRIMARY KEY (livro_id, autor_id)
);

CREATE TABLE IF NOT EXISTS livro_generos (
    livro_id BIGINT NOT NULL REFERENCES livros(id) ON DELETE CASCADE,
    genero_id INTEGER NOT NULL REFERENCES generos(id) ON DELETE CASCADE,
    PRIMARY KEY (livro_id, genero_id)
);

CREATE TABLE IF NOT EXISTS clientes (
    id BIGSERIAL PRIMARY KEY,
    nome_completo VARCHAR(200) NOT NULL,
    nif VARCHAR(9) NOT NULL UNIQUE,
    telemovel VARCHAR(20),
    email VARCHAR(150) UNIQUE,
    data_registo TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    total_compras_valor NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_compras_qtd INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS vendas (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT REFERENCES clientes(id) ON DELETE SET NULL,
    data_venda TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    valor_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    metodo_pagamento VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Concluída'
);

CREATE TABLE IF NOT EXISTS itens_venda (
    id BIGSERIAL PRIMARY KEY,
    venda_id BIGINT NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
    livro_id BIGINT NOT NULL REFERENCES livros(id) ON DELETE RESTRICT,
    quantidade INTEGER NOT NULL,
    preco_unitario NUMERIC(10,2) NOT NULL,
    subtotal NUMERIC(12,2) GENERATED ALWAYS AS (quantidade * preco_unitario) STORED
);

CREATE TABLE IF NOT EXISTS reservas (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    livro_id BIGINT NOT NULL REFERENCES livros(id) ON DELETE CASCADE,
    data_reserva TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    quantidade INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Pendente',
    data_limite DATE NOT NULL
);

COMMENT ON TABLE autores IS 'Autores dos livros disponíveis na Bookmarked.';
COMMENT ON TABLE generos IS 'Géneros literários utilizados para classificar os livros.';
COMMENT ON TABLE livros IS 'Catálogo operacional de livros da Bookmarked.';
COMMENT ON TABLE livro_autores IS 'Relação N:N entre livros e autores.';
COMMENT ON TABLE livro_generos IS 'Relação N:N entre livros e géneros.';
COMMENT ON TABLE clientes IS 'Clientes registados da livraria.';
COMMENT ON TABLE vendas IS 'Cabeçalho de cada venda; cliente_id pode ser NULL para venda ao balcão.';
COMMENT ON TABLE itens_venda IS 'Linhas de cada venda, uma por livro vendido.';
COMMENT ON TABLE reservas IS 'Reservas de livros efetuadas pelos clientes.';
