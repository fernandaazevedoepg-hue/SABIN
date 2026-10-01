--- Regras de integridade da base relacional.

ALTER TABLE autores
    ADD CONSTRAINT chk_autores_nascimento_passado
    CHECK (data_nascimento IS NULL OR data_nascimento <= CURRENT_DATE);

ALTER TABLE livros
    ADD CONSTRAINT chk_livros_preco_positivo
    CHECK (preco_venda >= 0),
    ADD CONSTRAINT chk_livros_estoque_nao_negativo
    CHECK (estoque_atual >= 0),
    ADD CONSTRAINT chk_livros_vendas_nao_negativo
    CHECK (total_vendas_acumuladas >= 0),
    ADD CONSTRAINT chk_livros_reservado_nao_negativo
    CHECK (qtd_reservada >= 0);

ALTER TABLE clientes
    ADD CONSTRAINT chk_clientes_nif_formato
    CHECK (nif ~ '^[0-9]{9}$'),
    ADD CONSTRAINT chk_clientes_total_valor_nao_negativo
    CHECK (total_compras_valor >= 0),
    ADD CONSTRAINT chk_clientes_total_qtd_nao_negativo
    CHECK (total_compras_qtd >= 0);

ALTER TABLE vendas
    ADD CONSTRAINT chk_vendas_valor_total_nao_negativo
    CHECK (valor_total >= 0),
    ADD CONSTRAINT chk_vendas_metodo_pagamento
    CHECK (metodo_pagamento IN (
        'Dinheiro',
        'Multibanco',
        'MBWay',
        'Cartão de Crédito',
        'Cartão de Débito',
        'Transferência'
    )),
    ADD CONSTRAINT chk_vendas_status
    CHECK (status IN ('Concluída', 'Cancelada', 'Pendente'));

ALTER TABLE itens_venda
    ADD CONSTRAINT chk_itens_venda_quantidade_positiva
    CHECK (quantidade > 0),
    ADD CONSTRAINT chk_itens_venda_preco_nao_negativo
    CHECK (preco_unitario >= 0);

ALTER TABLE reservas
    ADD CONSTRAINT chk_reservas_quantidade_positiva
    CHECK (quantidade > 0),
    ADD CONSTRAINT chk_reservas_status
    CHECK (status IN ('Pendente', 'Concluída', 'Cancelada', 'Expirada'));

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_livros_titulo
    ON livros USING gin (titulo gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_livros_isbn ON livros (isbn);
CREATE INDEX IF NOT EXISTS idx_livros_estoque_atual ON livros (estoque_atual);
CREATE INDEX IF NOT EXISTS idx_clientes_nif ON clientes (nif);
CREATE INDEX IF NOT EXISTS idx_vendas_cliente_id ON vendas (cliente_id);
CREATE INDEX IF NOT EXISTS idx_vendas_data_venda ON vendas (data_venda);
CREATE INDEX IF NOT EXISTS idx_vendas_status ON vendas (status);
CREATE INDEX IF NOT EXISTS idx_itens_venda_venda_id ON itens_venda (venda_id);
CREATE INDEX IF NOT EXISTS idx_itens_venda_livro_id ON itens_venda (livro_id);
CREATE INDEX IF NOT EXISTS idx_reservas_status ON reservas (status);
CREATE INDEX IF NOT EXISTS idx_reservas_cliente_id ON reservas (cliente_id);
CREATE INDEX IF NOT EXISTS idx_reservas_livro_id ON reservas (livro_id);
CREATE INDEX IF NOT EXISTS idx_reservas_data_limite ON reservas (data_limite);
