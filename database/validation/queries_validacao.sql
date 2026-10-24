-- QUERIES DE VALIDAÇÃO
-- Consultas usadas para provar que a transformação relacional -> dimensional
-- mantém os dados consistentes.
-- A fact_vendas tem uma linha por item de venda x autor x género; o valor de
-- cada item é repartido pelo peso, por isso as somas de quantidade_atribuida e
-- receita_atribuida dão os totais reais.

-- 1. Vendas concluídas na base operacional vs vendas no Data Warehouse
SELECT
    (SELECT COUNT(*)
     FROM public.vendas
     WHERE status = 'Concluída') AS vendas_operacional,
    (SELECT COUNT(DISTINCT venda_id_origem)
     FROM dw.fact_vendas) AS vendas_dw;

-- 2. Receita e unidades: base operacional vs Data Warehouse (devem ser iguais)
SELECT
    (SELECT ROUND(SUM(i.subtotal), 2)
     FROM public.itens_venda i
     JOIN public.vendas v ON v.id = i.venda_id
     WHERE v.status = 'Concluída') AS receita_operacional,
    (SELECT ROUND(SUM(receita_atribuida), 2)
     FROM dw.fact_vendas) AS receita_dw,
    (SELECT SUM(i.quantidade)
     FROM public.itens_venda i
     JOIN public.vendas v ON v.id = i.venda_id
     WHERE v.status = 'Concluída') AS unidades_operacional,
    (SELECT ROUND(SUM(quantidade_atribuida), 2)
     FROM dw.fact_vendas) AS unidades_dw;

-- 3. KPIs principais
SELECT
    ROUND(SUM(receita_atribuida), 2) AS receita_total,
    COUNT(DISTINCT venda_id_origem) AS numero_vendas,
    ROUND(SUM(quantidade_atribuida), 2) AS unidades_vendidas,
    COUNT(DISTINCT item_venda_id_origem) AS linhas_de_venda,
    ROUND(SUM(receita_atribuida) / NULLIF(COUNT(DISTINCT venda_id_origem), 0), 2) AS ticket_medio,
    ROUND(SUM(quantidade_atribuida) / NULLIF(COUNT(DISTINCT venda_id_origem), 0), 2) AS unidades_por_venda,
    ROUND(SUM(receita_atribuida) / NULLIF(SUM(quantidade_atribuida), 0), 2) AS valor_medio_unidade
FROM dw.fact_vendas;

-- 4. Pesos: em cada item de venda, a soma dos pesos tem de ser 1
-- (deve devolver 0 linhas)
SELECT
    item_venda_id_origem,
    ROUND(SUM(peso), 6) AS soma_pesos
FROM dw.fact_vendas
GROUP BY item_venda_id_origem
HAVING ROUND(SUM(peso), 6) <> 1;

-- 5. Duplicados: o mesmo item, autor e género não pode repetir-se
-- (deve devolver 0 linhas)
SELECT
    item_venda_id_origem,
    autor_key,
    genero_key,
    COUNT(*) AS ocorrencias
FROM dw.fact_vendas
GROUP BY item_venda_id_origem, autor_key, genero_key
HAVING COUNT(*) > 1;

-- 6. Vendas sem cliente identificado: base operacional vs Data Warehouse
SELECT
    (SELECT COUNT(*)
     FROM public.vendas
     WHERE status = 'Concluída'
       AND cliente_id IS NULL) AS vendas_sem_cliente_operacional,
    (SELECT COUNT(DISTINCT f.venda_id_origem)
     FROM dw.fact_vendas f
     JOIN dw.dim_cliente c ON c.cliente_key = f.cliente_key
     WHERE c.cliente_id_origem IS NULL) AS vendas_sem_cliente_dw;

-- 7. Número de linhas de cada tabela do Data Warehouse
SELECT 'dim_data' AS tabela, COUNT(*) AS linhas FROM dw.dim_data
UNION ALL
SELECT 'dim_cliente', COUNT(*) FROM dw.dim_cliente
UNION ALL
SELECT 'dim_livro', COUNT(*) FROM dw.dim_livro
UNION ALL
SELECT 'dim_autor', COUNT(*) FROM dw.dim_autor
UNION ALL
SELECT 'dim_genero', COUNT(*) FROM dw.dim_genero
UNION ALL
SELECT 'dim_pagamento', COUNT(*) FROM dw.dim_pagamento
UNION ALL
SELECT 'dim_nivel_stock', COUNT(*) FROM dw.dim_nivel_stock
UNION ALL
SELECT 'dim_modelo_previsao', COUNT(*) FROM dw.dim_modelo_previsao
UNION ALL
SELECT 'dim_alerta_previsao', COUNT(*) FROM dw.dim_alerta_previsao
UNION ALL
SELECT 'fact_vendas', COUNT(*) FROM dw.fact_vendas
UNION ALL
SELECT 'fact_stock', COUNT(*) FROM dw.fact_stock
UNION ALL
SELECT 'fact_previsao', COUNT(*) FROM dw.fact_previsao
UNION ALL
SELECT 'fact_alerta_previsao', COUNT(*) FROM dw.fact_alerta_previsao;

-- 8. Stock: a fotografia mais recente da fact_stock vs o stock atual dos livros
-- (deve devolver 0 linhas se a fotografia for de hoje)
SELECT
    l.titulo,
    l.estoque_atual AS stock_operacional,
    s.estoque_atual AS stock_dw
FROM public.livros l
JOIN dw.dim_livro dl ON dl.livro_id_origem = l.id
JOIN dw.fact_stock s ON s.livro_key = dl.livro_key
WHERE s.data_key = (SELECT MAX(data_key) FROM dw.fact_stock)
  AND l.estoque_atual <> s.estoque_atual;

-- 9. Receita mensal
SELECT
    d.ano_mes AS mes,
    ROUND(SUM(f.receita_atribuida), 2) AS receita
FROM dw.fact_vendas f
JOIN dw.dim_data d ON d.data_key = f.data_key
GROUP BY d.ano_mes
ORDER BY d.ano_mes;

-- 10. Últimas vendas transformadas (uma linha por item x autor x género)
SELECT
    f.venda_id_origem,
    f.item_venda_id_origem,
    d.data,
    l.titulo,
    a.nome AS autor,
    g.nome AS genero,
    f.peso,
    f.quantidade_atribuida,
    f.preco_unitario,
    f.receita_atribuida
FROM dw.fact_vendas f
JOIN dw.dim_data d ON d.data_key = f.data_key
JOIN dw.dim_livro l ON l.livro_key = f.livro_key
JOIN dw.dim_autor a ON a.autor_key = f.autor_key
JOIN dw.dim_genero g ON g.genero_key = f.genero_key
ORDER BY f.venda_id_origem DESC, f.item_venda_id_origem DESC
LIMIT 20;
