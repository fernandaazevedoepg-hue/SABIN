-- SABIN - Gestão de Catálogo
-- Adiciona histórico de stock e de preços à base operacional.

CREATE TABLE IF NOT EXISTS movimentos_stock (
    id BIGSERIAL PRIMARY KEY,
    livro_id BIGINT NOT NULL
        REFERENCES livros(id)
        ON DELETE RESTRICT,

    tipo VARCHAR(20) NOT NULL,

    quantidade INTEGER NOT NULL,

    stock_anterior INTEGER NOT NULL,

    stock_novo INTEGER NOT NULL,

    origem VARCHAR(50) NOT NULL,

    referencia_id BIGINT,

    data_movimento TIMESTAMP WITH TIME ZONE
        NOT NULL
        DEFAULT now(),

    observacao TEXT,

    CONSTRAINT chk_movimentos_stock_tipo
        CHECK (
            tipo IN (
                'Entrada',
                'Saída'
            )
        ),

    CONSTRAINT chk_movimentos_stock_quantidade
        CHECK (
            quantidade > 0
        ),

    CONSTRAINT chk_movimentos_stock_anterior
        CHECK (
            stock_anterior >= 0
        ),

    CONSTRAINT chk_movimentos_stock_novo
        CHECK (
            stock_novo >= 0
        )
);


CREATE TABLE IF NOT EXISTS historico_precos (
    id BIGSERIAL PRIMARY KEY,

    livro_id BIGINT NOT NULL
        REFERENCES livros(id)
        ON DELETE RESTRICT,

    preco_anterior NUMERIC(10,2)
        NOT NULL,

    preco_novo NUMERIC(10,2)
        NOT NULL,

    data_alteracao TIMESTAMP WITH TIME ZONE
        NOT NULL
        DEFAULT now(),

    observacao TEXT,

    CONSTRAINT chk_historico_precos_anterior
        CHECK (
            preco_anterior >= 0
        ),

    CONSTRAINT chk_historico_precos_novo
        CHECK (
            preco_novo >= 0
        ),

    CONSTRAINT chk_historico_precos_alteracao
        CHECK (
            preco_anterior <> preco_novo
        )
);


CREATE INDEX IF NOT EXISTS
idx_movimentos_stock_livro_id
ON movimentos_stock (livro_id);


CREATE INDEX IF NOT EXISTS
idx_movimentos_stock_data
ON movimentos_stock (data_movimento);


CREATE INDEX IF NOT EXISTS
idx_historico_precos_livro_id
ON historico_precos (livro_id);


CREATE INDEX IF NOT EXISTS
idx_historico_precos_data
ON historico_precos (data_alteracao);


CREATE OR REPLACE FUNCTION fn_atualizar_estoque_venda()
RETURNS TRIGGER AS $$
DECLARE
    v_estoque_atual INTEGER;
    v_qtd_reservada INTEGER;
    v_stock_disponivel INTEGER;
    v_stock_novo INTEGER;
BEGIN

    SELECT
        estoque_atual,
        qtd_reservada
    INTO
        v_estoque_atual,
        v_qtd_reservada
    FROM livros
    WHERE id = NEW.livro_id
    FOR UPDATE;


    IF v_estoque_atual IS NULL THEN
        RAISE EXCEPTION
            'Livro com id % não encontrado.',
            NEW.livro_id;
    END IF;


    v_stock_disponivel =
        v_estoque_atual
        - v_qtd_reservada;


    IF v_stock_disponivel < NEW.quantidade THEN
        RAISE EXCEPTION
            'Stock insuficiente para o livro id %. Disponível: %, solicitado: %.',
            NEW.livro_id,
            v_stock_disponivel,
            NEW.quantidade;
    END IF;


    v_stock_novo =
        v_estoque_atual
        - NEW.quantidade;


    UPDATE livros
    SET
        estoque_atual =
            v_stock_novo,

        total_vendas_acumuladas =
            total_vendas_acumuladas
            + NEW.quantidade,

        atualizado_em =
            now()

    WHERE id =
        NEW.livro_id;


    INSERT INTO movimentos_stock (
        livro_id,
        tipo,
        quantidade,
        stock_anterior,
        stock_novo,
        origem,
        referencia_id,
        observacao
    )
    VALUES (
        NEW.livro_id,
        'Saída',
        NEW.quantidade,
        v_estoque_atual,
        v_stock_novo,
        'Venda',
        NEW.venda_id,
        'Saída automática de stock através de uma venda.'
    );


    RETURN NEW;

END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS
trg_atualizar_estoque_venda
ON itens_venda;


CREATE TRIGGER trg_atualizar_estoque_venda
AFTER INSERT
ON itens_venda
FOR EACH ROW
EXECUTE FUNCTION fn_atualizar_estoque_venda();


CREATE OR REPLACE FUNCTION fn_registar_alteracao_preco()
RETURNS TRIGGER AS $$
BEGIN

    IF
        NEW.preco_venda
        IS DISTINCT FROM
        OLD.preco_venda
    THEN

        INSERT INTO historico_precos (
            livro_id,
            preco_anterior,
            preco_novo,
            data_alteracao,
            observacao
        )
        VALUES (
            NEW.id,
            OLD.preco_venda,
            NEW.preco_venda,
            now(),
            'Alteração do preço de venda.'
        );

    END IF;


    RETURN NEW;

END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS
trg_registar_alteracao_preco
ON livros;


CREATE TRIGGER trg_registar_alteracao_preco
AFTER UPDATE OF preco_venda
ON livros
FOR EACH ROW
EXECUTE FUNCTION fn_registar_alteracao_preco();