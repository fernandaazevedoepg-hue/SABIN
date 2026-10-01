-- 12.1 Trigger: atualização de estoque e total de vendas do livro

-- Sempre que um item de venda é inserido, o estoque do livro é reduzido e
-- o contador acumulado de vendas é incrementado na mesma quantidade.
-- Também impede a venda caso não haja estoque suficiente disponível.
CREATE OR REPLACE FUNCTION fn_atualizar_estoque_venda()
RETURNS TRIGGER AS $$
DECLARE
    v_estoque_disponivel INTEGER;
BEGIN
    SELECT estoque_atual INTO v_estoque_disponivel
    FROM livros
    WHERE id = NEW.livro_id
    FOR UPDATE;

    IF v_estoque_disponivel IS NULL THEN
        RAISE EXCEPTION 'Livro id % não encontrado.', NEW.livro_id;
    END IF;

    IF v_estoque_disponivel < NEW.quantidade THEN
        RAISE EXCEPTION 'Estoque insuficiente para o livro id % (disponível: %, solicitado: %).',
            NEW.livro_id, v_estoque_disponivel, NEW.quantidade;
    END IF;

    UPDATE livros
       SET estoque_atual           = estoque_atual - NEW.quantidade,
           total_vendas_acumuladas = total_vendas_acumuladas + NEW.quantidade,
           atualizado_em           = now()
     WHERE id = NEW.livro_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION fn_atualizar_estoque_venda() IS
    'Reduz o estoque e incrementa o total de vendas acumuladas do livro ao inserir um item de venda.';

CREATE TRIGGER trg_atualizar_estoque_venda
    AFTER INSERT ON itens_venda
    FOR EACH ROW
    EXECUTE FUNCTION fn_atualizar_estoque_venda();

-- 12.2 Trigger: atualização da quantidade "em reserva" do livro
-- Mantém livros.qtd_reservada em sincronia com as reservas com status
-- 'Pendente'. Cobre os três cenários:
--   - Nova reserva criada como 'Pendente'         -> incrementa
--   - Reserva pendente muda para outro status     -> decrementa
--   - Reserva não-pendente volta a ser 'Pendente'  -> incrementa
--   - Quantidade de uma reserva pendente é alterada -> ajusta a diferença

CREATE OR REPLACE FUNCTION fn_atualizar_reserva_livro()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status = 'Pendente' THEN
            UPDATE livros
               SET qtd_reservada = qtd_reservada + NEW.quantidade,
                   atualizado_em = now()
             WHERE id = NEW.livro_id;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        -- Continuava pendente, mas a quantidade reservada mudou
        IF OLD.status = 'Pendente' AND NEW.status = 'Pendente' THEN
            IF NEW.quantidade <> OLD.quantidade THEN
                UPDATE livros
                   SET qtd_reservada = qtd_reservada + (NEW.quantidade - OLD.quantidade),
                       atualizado_em = now()
                 WHERE id = NEW.livro_id;
            END IF;

        -- Saiu do status Pendente (Concluída / Cancelada / Expirada)
        ELSIF OLD.status = 'Pendente' AND NEW.status <> 'Pendente' THEN
            UPDATE livros
               SET qtd_reservada = GREATEST(qtd_reservada - OLD.quantidade, 0),
                   atualizado_em = now()
             WHERE id = OLD.livro_id;

        -- Voltou a ficar Pendente
        ELSIF OLD.status <> 'Pendente' AND NEW.status = 'Pendente' THEN
            UPDATE livros
               SET qtd_reservada = qtd_reservada + NEW.quantidade,
                   atualizado_em = now()
             WHERE id = NEW.livro_id;
        END IF;

        RETURN NEW;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION fn_atualizar_reserva_livro() IS
    'Mantém livros.qtd_reservada sincronizado com as reservas de status Pendente.';

CREATE TRIGGER trg_atualizar_reserva_livro
    AFTER INSERT OR UPDATE ON reservas
    FOR EACH ROW
    EXECUTE FUNCTION fn_atualizar_reserva_livro();


-- 12.3 Trigger (bônus/boa prática): atualização do total de compras do cliente

-- Não solicitada explicitamente, mas necessária para manter o atributo
-- "total de compras realizadas" de clientes atualizado de forma consistente,
-- assim como já foi feito para estoque e reservas.
--
-- É disparada em itens_venda (e não em vendas) porque, no fluxo normal de
-- uma venda, o cabeçalho (vendas) é inserido primeiro e os itens
-- (itens_venda) depois — se a trigger estivesse em vendas, ainda não
-- existiriam itens para somar. Para cada item inserido, consulta o
-- cabeçalho da venda correspondente e, se houver cliente identificado e a
-- venda estiver 'Concluída', incrementa o valor e a quantidade acumulados.

CREATE OR REPLACE FUNCTION fn_atualizar_total_compras_cliente()
RETURNS TRIGGER AS $$
DECLARE
    v_cliente_id BIGINT;
    v_status     VARCHAR(20);
BEGIN
    SELECT cliente_id, status INTO v_cliente_id, v_status
    FROM vendas
    WHERE id = NEW.venda_id;

    IF v_cliente_id IS NOT NULL AND v_status = 'Concluída' THEN
        UPDATE clientes
           SET total_compras_valor = total_compras_valor + NEW.subtotal,
               total_compras_qtd   = total_compras_qtd + NEW.quantidade
         WHERE id = v_cliente_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION fn_atualizar_total_compras_cliente() IS
    'Atualiza o total acumulado de compras (valor e quantidade) do cliente ao inserir um item de uma venda Concluída.';

CREATE TRIGGER trg_atualizar_total_compras_cliente
    AFTER INSERT ON itens_venda
    FOR EACH ROW
    EXECUTE FUNCTION fn_atualizar_total_compras_cliente();
