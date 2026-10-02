
-- Estrutura principal da base operacional da livraria Bookmarked.

CREATE TABLE autores (
    id BIGSERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    nacionalidade VARCHAR(80),
    data_nascimento DATE,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE generos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(80) NOT NULL UNIQUE,
    descricao TEXT
);

CREATE TABLE livros (
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

CREATE TABLE livro_autores (
    livro_id BIGINT NOT NULL REFERENCES livros(id) ON DELETE CASCADE,
    autor_id BIGINT NOT NULL REFERENCES autores(id) ON DELETE CASCADE,
    PRIMARY KEY (livro_id, autor_id)
);

CREATE TABLE livro_generos (
    livro_id BIGINT NOT NULL REFERENCES livros(id) ON DELETE CASCADE,
    genero_id INTEGER NOT NULL REFERENCES generos(id) ON DELETE CASCADE,
    PRIMARY KEY (livro_id, genero_id)
);

CREATE TABLE clientes (
    id BIGSERIAL PRIMARY KEY,
    nome_completo VARCHAR(200) NOT NULL,
    nif VARCHAR(9) NOT NULL UNIQUE,
    telemovel VARCHAR(20),
    email VARCHAR(150) UNIQUE,
    data_registo TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    total_compras_valor NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_compras_qtd INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE vendas (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT REFERENCES clientes(id) ON DELETE SET NULL,
    data_venda TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    valor_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    metodo_pagamento VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Concluída'
);

CREATE TABLE itens_venda (
    id BIGSERIAL PRIMARY KEY,
    venda_id BIGINT NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
    livro_id BIGINT NOT NULL REFERENCES livros(id) ON DELETE RESTRICT,
    quantidade INTEGER NOT NULL,
    preco_unitario NUMERIC(10,2) NOT NULL,
    subtotal NUMERIC(12,2)
        GENERATED ALWAYS AS (quantidade * preco_unitario) STORED
);

CREATE TABLE reservas (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    livro_id BIGINT NOT NULL REFERENCES livros(id) ON DELETE CASCADE,
    data_reserva TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    quantidade INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Pendente',
    data_limite DATE NOT NULL
);

-- Guarda o histórico de entradas e saídas de stock.
CREATE TABLE movimentos_stock (
    id BIGSERIAL PRIMARY KEY,
    livro_id BIGINT NOT NULL REFERENCES livros(id) ON DELETE RESTRICT,
    tipo VARCHAR(20) NOT NULL,
    quantidade INTEGER NOT NULL,
    stock_anterior INTEGER NOT NULL,
    stock_novo INTEGER NOT NULL,
    origem VARCHAR(50) NOT NULL,
    referencia_id BIGINT,
    data_movimento TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    observacao TEXT
);

-- Guarda o histórico das alterações de preço.
CREATE TABLE historico_precos (
    id BIGSERIAL PRIMARY KEY,
    livro_id BIGINT NOT NULL REFERENCES livros(id) ON DELETE RESTRICT,
    preco_anterior NUMERIC(10,2) NOT NULL,
    preco_novo NUMERIC(10,2) NOT NULL,
    data_alteracao TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    observacao TEXT
);
