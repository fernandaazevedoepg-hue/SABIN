-- SABIN - Restrições da Base de Dados Relacional

-- Autor

ALTER TABLE autores
ADD CONSTRAINT chk_autores_nascimento_passado
CHECK (
    data_nascimento IS NULL
    OR data_nascimento <= CURRENT_DATE
);

-- Livros

ALTER TABLE livros
ADD CONSTRAINT chk_livros_preco_positivo
CHECK (preco_venda >= 0);

ALTER TABLE livros
ADD CONSTRAINT chk_livros_estoque_nao_negativo
CHECK (estoque_atual >= 0);

ALTER TABLE livros
ADD CONSTRAINT chk_livros_vendas_nao_negativo
CHECK (total_vendas_acumuladas >= 0);

ALTER TABLE livros
ADD CONSTRAINT chk_livros_reservado_nao_negativo
CHECK (qtd_reservada >= 0);

-- Clientes

ALTER TABLE clientes
ADD CONSTRAINT chk_clientes_nif_formato
CHECK (nif ~ '^[0-9]{9}$');

ALTER TABLE clientes
ADD CONSTRAINT chk_clientes_total_valor_nao_negativo
CHECK (total_compras_valor >= 0);

ALTER TABLE clientes
ADD CONSTRAINT chk_clientes_total_qtd_nao_negativo
CHECK (total_compras_qtd >= 0);

-- Vendas

ALTER TABLE vendas
ADD CONSTRAINT chk_vendas_valor_total_nao_negativo
CHECK (valor_total >= 0);

ALTER TABLE vendas
ADD CONSTRAINT chk_vendas_metodo_pagamento
CHECK (
    metodo_pagamento IN (
        'Dinheiro',
        'Multibanco',
        'MBWay',
        'Cartão de Crédito',
        'Cartão de Débito',
        'Transferência'
    )
);

ALTER TABLE vendas
ADD CONSTRAINT chk_vendas_status
CHECK (
    status IN (
        'Concluída',
        'Cancelada',
        'Pendente'
    )
);

-- Itens de venda

ALTER TABLE itens_venda
ADD CONSTRAINT chk_itens_venda_quantidade_positiva
CHECK (quantidade > 0);

ALTER TABLE itens_venda
ADD CONSTRAINT chk_itens_venda_preco_nao_negativo
CHECK (preco_unitario >= 0);

-- Reservas

ALTER TABLE reservas
ADD CONSTRAINT chk_reservas_quantidade_positiva
CHECK (quantidade > 0);

ALTER TABLE reservas
ADD CONSTRAINT chk_reservas_status
CHECK (
    status IN (
        'Pendente',
        'Concluída',
        'Cancelada',
        'Expirada'
    )
);

-- Movimentos de stock

ALTER TABLE movimentos_stock
ADD CONSTRAINT chk_movimentos_stock_tipo
CHECK (
    tipo IN (
        'Entrada',
        'Saída'
    )
);

ALTER TABLE movimentos_stock
ADD CONSTRAINT chk_movimentos_stock_quantidade_positiva
CHECK (quantidade > 0);

ALTER TABLE movimentos_stock
ADD CONSTRAINT chk_movimentos_stock_anterior_nao_negativo
CHECK (stock_anterior >= 0);

ALTER TABLE movimentos_stock
ADD CONSTRAINT chk_movimentos_stock_novo_nao_negativo
CHECK (stock_novo >= 0);

-- Histórico de preços

ALTER TABLE historico_precos
ADD CONSTRAINT chk_historico_precos_anterior_nao_negativo
CHECK (preco_anterior >= 0);

ALTER TABLE historico_precos
ADD CONSTRAINT chk_historico_precos_novo_nao_negativo
CHECK (preco_novo >= 0);

ALTER TABLE historico_precos
ADD CONSTRAINT chk_historico_precos_alteracao_real
CHECK (preco_anterior <> preco_novo);