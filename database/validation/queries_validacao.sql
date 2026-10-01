-- QUERIES DE VALIDAÇÃO
-- Consultas usadas para provar que a transformação relacional -> dimensional
-- mantém os dados consistentes.

-- 1. Vendas concluídas na base operacional vs vendas no Data Warehouse
SELECT
    (SELECT COUNT(*)
     FROM public.vendas
     WHERE status = 'Concluída') AS vendas_operacional,
    (SELECT COUNT(DISTINCT venda_id_origem)
     FROM dw.fact_vendas) AS vendas_dw;

-- 2. Receita, vendas, unidades e linhas do Data Warehouse
SELECT
    ROUND(SUM(subtotal), 2) AS receita_total,
    COUNT(DISTINCT venda_id_origem) AS numero_vendas,
    SUM(quantidade) AS unidades_vendidas,
    COUNT(*) AS linhas_fact
FROM dw.fact_vendas;

-- 3. KPIs principais
SELECT
    ROUND(SUM(subtotal), 2) AS receita_total,
    COUNT(DISTINCT venda_id_origem) AS numero_vendas,
    SUM(quantidade) AS unidades_vendidas,
    ROUND(SUM(subtotal) / NULLIF(COUNT(DISTINCT venda_id_origem), 0), 2) AS ticket_medio,
    ROUND(AVG(subtotal), 2) AS valor_medio_linha,
    ROUND(SUM(quantidade)::numeric / NULLIF(COUNT(DISTINCT venda_id_origem), 0), 2) AS unidades_por_venda,
    ROUND(SUM(subtotal) / NULLIF(SUM(quantidade), 0), 2) AS valor_medio_unidade
FROM dw.fact_vendas;

-- 4. Verificar duplicados na fact
SELECT
    item_venda_id_origem,
    COUNT(*) AS ocorrencias
FROM dw.fact_vendas
GROUP BY item_venda_id_origem
HAVING COUNT(*) > 1;

-- 5. Vendas sem cliente identificado na origem
SELECT COUNT(*) AS vendas_sem_cliente_operacional
FROM public.vendas
WHERE status = 'Concluída'
  AND cliente_id IS NULL;

-- 6. Linhas da fact associadas ao cliente não identificado
SELECT
    COUNT(DISTINCT f.venda_id_origem) AS vendas_sem_cliente_dw
FROM dw.fact_vendas f
JOIN dw.dim_cliente c
  ON c.cliente_key = f.cliente_key
WHERE c.cliente_id_origem IS NULL;

-- 7. Contagens das dimensões e bridges
SELECT 'dim_cliente' AS tabela, COUNT(*) AS linhas FROM dw.dim_cliente
UNION ALL
SELECT 'dim_livro', COUNT(*) FROM dw.dim_livro
UNION ALL
SELECT 'dim_pagamento', COUNT(*) FROM dw.dim_pagamento
UNION ALL
SELECT 'dim_data', COUNT(*) FROM dw.dim_data
UNION ALL
SELECT 'dim_autor', COUNT(*) FROM dw.dim_autor
UNION ALL
SELECT 'dim_genero', COUNT(*) FROM dw.dim_genero
UNION ALL
SELECT 'bridge_livro_autor', COUNT(*) FROM dw.bridge_livro_autor
UNION ALL
SELECT 'bridge_livro_genero', COUNT(*) FROM dw.bridge_livro_genero
UNION ALL
SELECT 'fact_vendas', COUNT(*) FROM dw.fact_vendas;

-- 8. Validar se todas as foreign keys da fact encontram dimensão
SELECT
    COUNT(*) FILTER (WHERE d.data_key IS NULL) AS datas_sem_correspondencia,
    COUNT(*) FILTER (WHERE c.cliente_key IS NULL) AS clientes_sem_correspondencia,
    COUNT(*) FILTER (WHERE l.livro_key IS NULL) AS livros_sem_correspondencia,
    COUNT(*) FILTER (WHERE p.pagamento_key IS NULL) AS pagamentos_sem_correspondencia
FROM dw.fact_vendas f
LEFT JOIN dw.dim_data d ON d.data_key = f.data_key
LEFT JOIN dw.dim_cliente c ON c.cliente_key = f.cliente_key
LEFT JOIN dw.dim_livro l ON l.livro_key = f.livro_key
LEFT JOIN dw.dim_pagamento p ON p.pagamento_key = f.pagamento_key;

-- 9. Receita mensal
SELECT
    DATE_TRUNC('month', d.data)::date AS mes,
    ROUND(SUM(f.subtotal), 2) AS receita
FROM dw.fact_vendas f
JOIN dw.dim_data d ON d.data_key = f.data_key
GROUP BY 1
ORDER BY 1;

-- 10. Últimas vendas transformadas
SELECT
    f.venda_id_origem,
    f.item_venda_id_origem,
    d.data,
    l.titulo,
    f.quantidade,
    f.preco_unitario,
    f.subtotal
FROM dw.fact_vendas f
JOIN dw.dim_data d ON d.data_key = f.data_key
JOIN dw.dim_livro l ON l.livro_key = f.livro_key
ORDER BY f.venda_id_origem DESC, f.item_venda_id_origem DESC
LIMIT 20;
