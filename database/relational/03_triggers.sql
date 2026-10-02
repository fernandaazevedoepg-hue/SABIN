-- SABIN - Funções e Triggers da Base de Dados Relacional

-- Atualiza o stock quando é registado um item de venda

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

    v_stock_disponivel :=
        v_estoque_atual - v_qtd_reservada;

    IF v_stock_disponivel < NEW.quantidade THEN
        RAISE EXCEPTION
            'Stock insuficiente para o livro id %. Disponível: %, solicitado: %.',
            NEW.livro_id,
            v_stock_disponivel,
            NEW.quantidade;
    END IF;

    v_stock_novo :=
        v_estoque_atual - NEW.quantidade;

    UPDATE livros
    SET
        estoque_atual = v_stock_novo,
        total_vendas_acumuladas =
            total_vendas_acumuladas + NEW.quantidade,
        atualizado_em = now()
    WHERE id = NEW.livro_id;

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
        'Saída automática de stock resultante de uma venda.'
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS
trg_atualizar_estoque_venda
ON itens_venda;

CREATE TRIGGER trg_atualizar_estoque_venda
AFTER INSERT ON itens_venda
FOR EACH ROW
EXECUTE FUNCTION fn_atualizar_estoque_venda();


-- Atualiza a quantidade reservada dos livros

CREATE OR REPLACE FUNCTION fn_atualizar_reserva_livro()
RETURNS TRIGGER AS $$
DECLARE
    v_stock_disponivel INTEGER;
BEGIN
    IF TG_OP = 'INSERT' THEN

        IF NEW.status = 'Pendente' THEN

            SELECT
                estoque_atual - qtd_reservada
            INTO
                v_stock_disponivel
            FROM livros
            WHERE id = NEW.livro_id
            FOR UPDATE;

            IF v_stock_disponivel < NEW.quantidade THEN
                RAISE EXCEPTION
                    'Stock insuficiente para reservar o livro id %.',
                    NEW.livro_id;
            END IF;

            UPDATE livros
            SET
                qtd_reservada =
                    qtd_reservada + NEW.quantidade,
                atualizado_em = now()
            WHERE id = NEW.livro_id;

        END IF;

        RETURN NEW;
    END IF;


    IF TG_OP = 'UPDATE' THEN

        IF OLD.status = 'Pendente' THEN

            UPDATE livros
            SET
                qtd_reservada =
                    GREATEST(
                        qtd_reservada - OLD.quantidade,
                        0
                    ),
                atualizado_em = now()
            WHERE id = OLD.livro_id;

        END IF;


        IF NEW.status = 'Pendente' THEN

            SELECT
                estoque_atual - qtd_reservada
            INTO
                v_stock_disponivel
            FROM livros
            WHERE id = NEW.livro_id
            FOR UPDATE;

            IF v_stock_disponivel < NEW.quantidade THEN
                RAISE EXCEPTION
                    'Stock insuficiente para reservar o livro id %.',
                    NEW.livro_id;
            END IF;

            UPDATE livros
            SET
                qtd_reservada =
                    qtd_reservada + NEW.quantidade,
                atualizado_em = now()
            WHERE id = NEW.livro_id;

        END IF;

        RETURN NEW;
    END IF;


    IF TG_OP = 'DELETE' THEN

        IF OLD.status = 'Pendente' THEN

            UPDATE livros
            SET
                qtd_reservada =
                    GREATEST(
                        qtd_reservada - OLD.quantidade,
                        0
                    ),
                atualizado_em = now()
            WHERE id = OLD.livro_id;

        END IF;

        RETURN OLD;
    END IF;


    RETURN NULL;
END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS
trg_atualizar_reserva_livro
ON reservas;

CREATE TRIGGER trg_atualizar_reserva_livro
AFTER INSERT OR UPDATE OR DELETE
ON reservas
FOR EACH ROW
EXECUTE FUNCTION fn_atualizar_reserva_livro();


-- Atualiza os totais acumulados do cliente

CREATE OR REPLACE FUNCTION fn_atualizar_total_compras_cliente()
RETURNS TRIGGER AS $$
DECLARE
    v_cliente_id BIGINT;
    v_status VARCHAR(20);
BEGIN
    SELECT
        cliente_id,
        status
    INTO
        v_cliente_id,
        v_status
    FROM vendas
    WHERE id = NEW.venda_id;

    IF
        v_cliente_id IS NOT NULL
        AND v_status = 'Concluída'
    THEN

        UPDATE clientes
        SET
            total_compras_valor =
                total_compras_valor + NEW.subtotal,
            total_compras_qtd =
                total_compras_qtd + NEW.quantidade
        WHERE id = v_cliente_id;

    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS
trg_atualizar_total_compras_cliente
ON itens_venda;

CREATE TRIGGER trg_atualizar_total_compras_cliente
AFTER INSERT ON itens_venda
FOR EACH ROW
EXECUTE FUNCTION fn_atualizar_total_compras_cliente();


-- Guarda automaticamente as alterações de preço

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