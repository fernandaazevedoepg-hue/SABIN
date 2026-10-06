-- Modelo dimensional utilizado pelo ETL e pelo Power BI.
-- O ETL preenche estas tabelas a partir da base operacional public.

CREATE SCHEMA IF NOT EXISTS dw;

CREATE TABLE IF NOT EXISTS dw.dim_cliente (
    cliente_key BIGSERIAL PRIMARY KEY,
    cliente_id_origem BIGINT,
    nome_completo VARCHAR(200) NOT NULL,
    data_registo TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS dw.dim_livro (
    livro_key BIGSERIAL PRIMARY KEY,
    livro_id_origem BIGINT NOT NULL UNIQUE,
    titulo VARCHAR(255) NOT NULL,
    isbn VARCHAR(20),
    editora VARCHAR(150),
    data_publicacao DATE
);

CREATE TABLE IF NOT EXISTS dw.dim_pagamento (
    pagamento_key BIGSERIAL PRIMARY KEY,
    metodo_pagamento VARCHAR(30) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dw.dim_data (
    data_key INTEGER PRIMARY KEY,
    data DATE NOT NULL UNIQUE,
    dia INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    nome_mes VARCHAR(20) NOT NULL,
    trimestre INTEGER NOT NULL,
    ano INTEGER NOT NULL,
    dia_semana VARCHAR(20) NOT NULL,
    fim_semana BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.dim_autor (
    autor_key BIGSERIAL PRIMARY KEY,
    autor_id_origem BIGINT NOT NULL UNIQUE,
    nome VARCHAR(150) NOT NULL,
    nacionalidade VARCHAR(80),
    data_nascimento DATE
);

CREATE TABLE IF NOT EXISTS dw.dim_genero (
    genero_key BIGSERIAL PRIMARY KEY,
    genero_id_origem INTEGER NOT NULL UNIQUE,
    nome VARCHAR(80) NOT NULL,
    descricao TEXT
);

CREATE TABLE IF NOT EXISTS dw.bridge_livro_autor (
    livro_key BIGINT NOT NULL REFERENCES dw.dim_livro(livro_key) ON DELETE CASCADE,
    autor_key BIGINT NOT NULL REFERENCES dw.dim_autor(autor_key) ON DELETE CASCADE,
    PRIMARY KEY (livro_key, autor_key)
);

CREATE TABLE IF NOT EXISTS dw.bridge_livro_genero (
    livro_key BIGINT NOT NULL REFERENCES dw.dim_livro(livro_key) ON DELETE CASCADE,
    genero_key BIGINT NOT NULL REFERENCES dw.dim_genero(genero_key) ON DELETE CASCADE,
    PRIMARY KEY (livro_key, genero_key)
);

CREATE TABLE IF NOT EXISTS dw.fact_vendas (
    fact_venda_key BIGSERIAL PRIMARY KEY,
    data_key INTEGER NOT NULL REFERENCES dw.dim_data(data_key),
    cliente_key BIGINT NOT NULL REFERENCES dw.dim_cliente(cliente_key),
    livro_key BIGINT NOT NULL REFERENCES dw.dim_livro(livro_key),
    pagamento_key BIGINT NOT NULL REFERENCES dw.dim_pagamento(pagamento_key),
    venda_id_origem BIGINT NOT NULL,
    item_venda_id_origem BIGINT NOT NULL UNIQUE,
    quantidade INTEGER NOT NULL,
    preco_unitario NUMERIC(10,2) NOT NULL,
    subtotal NUMERIC(12,2) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fact_vendas_data ON dw.fact_vendas(data_key);
CREATE INDEX IF NOT EXISTS idx_fact_vendas_cliente ON dw.fact_vendas(cliente_key);
CREATE INDEX IF NOT EXISTS idx_fact_vendas_livro ON dw.fact_vendas(livro_key);
CREATE INDEX IF NOT EXISTS idx_fact_vendas_pagamento ON dw.fact_vendas(pagamento_key);
CREATE INDEX IF NOT EXISTS idx_fact_vendas_venda_origem ON dw.fact_vendas(venda_id_origem);

-- As tabelas dw.previsao_receita, dw.metricas_previsao, dw.alertas_previsao e dw.alertas_stock são geradas pelos módulos Python da pasta analysis/ e, por isso, não fazem parte do núcleo do modelo estrela.
