-- 13. DADOS DE EXEMPLO (SEED DATA)

-- 13.1 Autores

INSERT INTO autores (nome, nacionalidade, data_nascimento) VALUES
('José Saramago',       'Portuguesa',  '1922-11-16'),
('George Orwell',       'Britânica',   '1903-06-25'),
('Agatha Christie',     'Britânica',   '1890-09-15'),
('Fernando Pessoa',     'Portuguesa',  '1888-06-13'),
('J.R.R. Tolkien',      'Britânica',   '1892-01-03'),
('J.K. Rowling',        'Britânica',   '1965-07-31'),
('Machado de Assis',    'Brasileira',  '1839-06-21'),
('Clarice Lispector',   'Brasileira',  '1920-12-10'),
('Eça de Queiroz',      'Portuguesa',  '1845-11-25'),
('Stephen King',        'Americana',   '1947-09-21'),
('Isaac Asimov',        'Americana',   '1920-01-02'),
('Gabriel García Márquez', 'Colombiana', '1927-03-06'),
('Paulo Coelho',        'Brasileira',  '1947-08-24'),
('Franz Kafka',         'Checa',       '1883-07-03'),
('Jane Austen',         'Britânica',   '1775-12-16'),
('Dan Brown',           'Americana',   '1964-06-22'),
('Suzanne Collins',     'Americana',   '1962-08-10'),
('Antoine de Saint-Exupéry', 'Francesa', '1900-06-29');

-- 13.2 Gêneros
INSERT INTO generos (nome, descricao) VALUES
('Ficção',        'Obras de caráter imaginativo e narrativo.'),
('Distopia',       'Narrativas sobre sociedades opressoras ou totalitárias.'),
('Romance',        'Obras centradas em relações e desenvolvimento pessoal.'),
('Policial',       'Narrativas de mistério, crime e investigação.'),
('Poesia',         'Obras em verso, com foco estético e emocional.'),
('Fantasia',       'Narrativas com elementos mágicos ou de mundos imaginários.'),
('Terror',         'Obras que exploram o medo, o sobrenatural e o macabro.'),
('Ficção Científica', 'Narrativas baseadas em especulações científicas e tecnológicas.'),
('Suspense',       'Narrativas de tensão crescente e reviravoltas, próximas do thriller.'),
('Autoajuda',      'Obras voltadas ao desenvolvimento pessoal e reflexão.'),
('Biografia',      'Relatos da vida de pessoas reais.'),
('Infantil',       'Obras voltadas ao público infantil e juvenil.'),
('Aventura',       'Narrativas centradas em jornadas, exploração e desafios.'),
('Realismo Mágico', 'Narrativas que misturam o cotidiano com elementos fantásticos.');

-- 13.3 Livros
INSERT INTO livros (titulo, isbn, preco_venda, estoque_atual, data_publicacao, editora) VALUES
('Ensaio sobre a Cegueira',       '9789720000011', 16.90, 150, '1995-01-01', 'Caminho'),
('Memorial do Convento',          '9789720000028', 17.50, 120, '1982-01-01', 'Caminho'),
('1984',                          '9789720000035', 15.90, 200, '1949-06-08', 'Antígona'),
('A Revolução dos Animais',       '9789720000042', 12.50, 140, '1945-08-17', 'Antígona'),
('Assassinato no Expresso do Oriente', '9789720000059', 14.90, 110, '1934-01-01', 'Livros do Brasil'),
('Mensagem',                      '9789720000066', 11.00, 160, '1934-12-01', 'Ática'),
('O Hobbit',                      '9789720000073', 19.90, 130, '1937-09-21', 'Bertrand'),
('Harry Potter e a Pedra Filosofal', '9789720000080', 21.90, 220, '1997-06-26', 'Bertrand'),
('Dom Casmurro',                  '9789720000097', 13.90, 140, '1899-12-01', 'Porto Editora'),
('A Hora da Estrela',             '9789720000103', 12.90, 100, '1977-10-01', 'Rocco'),
('Os Maias',                      '9789720000110', 18.50, 110, '1888-01-01', 'Livros do Brasil'),
('It: A Coisa',                   '9789720000127', 24.90, 150, '1986-09-15', 'Suma de Letras'),
('O Iluminado',                   '9789720000134', 19.90, 130, '1977-01-28', 'Suma de Letras'),
('Fundação',                      '9789720000141', 17.90, 120, '1951-05-01', 'Bertrand'),
('Eu, Robô',                      '9789720000158', 16.90, 110, '1950-12-02', 'Bertrand'),
('Cem Anos de Solidão',           '9789720000165', 20.90, 130, '1967-05-30', 'Publicações Dom Quixote'),
('O Alquimista',                  '9789720000172', 15.90, 180, '1988-01-01', 'Pergaminho'),
('A Metamorfose',                 '9789720000189', 9.90,  100, '1915-01-01', 'Antígona'),
('Orgulho e Preconceito',         '9789720000196', 14.50, 130, '1813-01-28', 'Relógio D''Água'),
('O Código Da Vinci',             '9789720000202', 19.50, 170, '2003-03-18', 'Bertrand'),
('Anjos e Demónios',              '9789720000219', 18.90, 140, '2000-01-01', 'Bertrand'),
('Jogos da Fome',                 '9789720000226', 17.50, 190, '2008-09-14', 'Editorial Presença'),
('O Principezinho',               '9789720000233', 12.50, 150, '1943-04-06', 'Editorial Presença'),
('Harry Potter e a Câmara dos Segredos', '9789720000240', 21.90, 200, '1998-07-02', 'Bertrand'),
('O Senhor dos Anéis: A Sociedade do Anel', '9789720000257', 24.90, 160, '1954-07-29', 'Bertrand');

-- 13.4 Relação Livro-Autor

INSERT INTO livro_autores (livro_id, autor_id) VALUES
(1, 1),  -- Ensaio sobre a Cegueira - José Saramago
(2, 1),  -- Memorial do Convento - José Saramago
(3, 2),  -- 1984 - George Orwell
(4, 2),  -- A Revolução dos Animais - George Orwell
(5, 3),  -- Assassinato no Expresso do Oriente - Agatha Christie
(6, 4),  -- Mensagem - Fernando Pessoa
(7, 5),  -- O Hobbit - J.R.R. Tolkien
(8, 6),  -- Harry Potter e a Pedra Filosofal - J.K. Rowling
(9, 7),   -- Dom Casmurro - Machado de Assis
(10, 8),  -- A Hora da Estrela - Clarice Lispector
(11, 9),  -- Os Maias - Eça de Queiroz
(12, 10), -- It: A Coisa - Stephen King
(13, 10), -- O Iluminado - Stephen King
(14, 11), -- Fundação - Isaac Asimov
(15, 11), -- Eu, Robô - Isaac Asimov
(16, 12), -- Cem Anos de Solidão - Gabriel García Márquez
(17, 13), -- O Alquimista - Paulo Coelho
(18, 14), -- A Metamorfose - Franz Kafka
(19, 15), -- Orgulho e Preconceito - Jane Austen
(20, 16), -- O Código Da Vinci - Dan Brown
(21, 16), -- Anjos e Demónios - Dan Brown
(22, 17), -- Jogos da Fome - Suzanne Collins
(23, 18), -- O Principezinho - Antoine de Saint-Exupéry
(24, 6),  -- Harry Potter e a Câmara dos Segredos - J.K. Rowling
(25, 5);  -- O Senhor dos Anéis: A Sociedade do Anel - J.R.R. Tolkien


-- 13.5 Relação Livro-Gênero (alguns livros com múltiplos gêneros)

INSERT INTO livro_generos (livro_id, genero_id) VALUES
(1, 1), (1, 2),      -- Ensaio sobre a Cegueira: Ficção + Distopia
(2, 1), (2, 3),      -- Memorial do Convento: Ficção + Romance
(3, 1), (3, 2),      -- 1984: Ficção + Distopia
(4, 1), (4, 2),      -- A Revolução dos Animais: Ficção + Distopia
(5, 4),              -- Assassinato no Expresso do Oriente: Policial
(6, 5),              -- Mensagem: Poesia
(7, 6), (7, 1),      -- O Hobbit: Fantasia + Ficção
(8, 6), (8, 1),      -- Harry Potter e a Pedra Filosofal: Fantasia + Ficção
(9, 3), (9, 1),      -- Dom Casmurro: Romance + Ficção
(10, 1), (10, 3),    -- A Hora da Estrela: Ficção + Romance
(11, 3), (11, 1),    -- Os Maias: Romance + Ficção
(12, 7), (12, 9),    -- It: A Coisa: Terror + Suspense
(13, 7), (13, 9),    -- O Iluminado: Terror + Suspense
(14, 8), (14, 1),    -- Fundação: Ficção Científica + Ficção
(15, 8), (15, 1),    -- Eu, Robô: Ficção Científica + Ficção
(16, 14), (16, 1),   -- Cem Anos de Solidão: Realismo Mágico + Ficção
(17, 10), (17, 1),   -- O Alquimista: Autoajuda + Ficção
(18, 1),             -- A Metamorfose: Ficção
(19, 3),             -- Orgulho e Preconceito: Romance
(20, 9), (20, 4),    -- O Código Da Vinci: Suspense + Policial
(21, 9), (21, 4),    -- Anjos e Demónios: Suspense + Policial
(22, 8), (22, 13),   -- Jogos da Fome: Ficção Científica + Aventura
(23, 12), (23, 1),   -- O Principezinho: Infantil + Ficção
(24, 6), (24, 1),    -- Harry Potter e a Câmara dos Segredos: Fantasia + Ficção
(25, 6), (25, 13);   -- O Senhor dos Anéis: A Sociedade do Anel: Fantasia + Aventura

-- 13.6 Clientes (NIF e telemóvel portugueses)
INSERT INTO clientes (nome_completo, nif, telemovel, email, data_registo) VALUES
('Maria João Silva',    '123456789', '+351 912 345 678', 'mariajoao.silva@email.pt', '2024-01-10 10:00:00+00'),
('António Ferreira',    '234567891', '+351 923 456 789', 'antonio.ferreira@email.pt', '2024-02-15 11:30:00+00'),
('Beatriz Costa',       '345678912', '+351 934 567 890', 'beatriz.costa@email.pt',   '2024-03-20 09:15:00+00'),
('Ricardo Santos',      '456789123', '+351 961 234 567', 'ricardo.santos@email.pt',  '2024-04-05 14:45:00+00'),
('Inês Rodrigues',      '567891234', '+351 969 876 543', 'ines.rodrigues@email.pt',  '2024-05-12 16:20:00+00');

-- 13.7 Vendas anteriores + itens
-- Observação: o INSERT em itens_venda dispara automaticamente a trigger
-- que atualiza o estoque e o total de vendas do livro (seção 12.1).
-- valor_total do cabeçalho é definido de forma consistente com a soma
-- dos subtotais dos itens correspondentes.

-- Venda 1: Maria João compra "Ensaio sobre a Cegueira" e "1984"
INSERT INTO vendas (cliente_id, data_venda, valor_total, metodo_pagamento, status) VALUES
(1, '2024-06-01 10:15:00+00', 32.80, 'Multibanco', 'Concluída');
INSERT INTO itens_venda (venda_id, livro_id, quantidade, preco_unitario) VALUES
(1, 1, 1, 16.90),
(1, 3, 1, 15.90);

-- Venda 2: António compra "O Hobbit"
INSERT INTO vendas (cliente_id, data_venda, valor_total, metodo_pagamento, status) VALUES
(2, '2024-06-10 15:40:00+00', 19.90, 'MBWay', 'Concluída');
INSERT INTO itens_venda (venda_id, livro_id, quantidade, preco_unitario) VALUES
(2, 7, 1, 19.90);

-- Venda 3: Venda ao balcão, sem cliente identificado
INSERT INTO vendas (cliente_id, data_venda, valor_total, metodo_pagamento, status) VALUES
(NULL, '2024-06-15 12:00:00+00', 14.90, 'Dinheiro', 'Concluída');
INSERT INTO itens_venda (venda_id, livro_id, quantidade, preco_unitario) VALUES
(3, 5, 1, 14.90);

-- Venda 4: Beatriz compra 2x "Harry Potter" e 1x "Mensagem"
INSERT INTO vendas (cliente_id, data_venda, valor_total, metodo_pagamento, status) VALUES
(3, '2024-07-02 09:30:00+00', 54.80, 'Cartão de Crédito', 'Concluída');
INSERT INTO itens_venda (venda_id, livro_id, quantidade, preco_unitario) VALUES
(4, 8, 2, 21.90),
(4, 6, 1, 11.00);

-- Venda 5: Ricardo compra "A Revolução dos Animais"
INSERT INTO vendas (cliente_id, data_venda, valor_total, metodo_pagamento, status) VALUES
(4, '2024-07-20 17:10:00+00', 12.50, 'Cartão de Débito', 'Concluída');
INSERT INTO itens_venda (venda_id, livro_id, quantidade, preco_unitario) VALUES
(5, 4, 1, 12.50);

-- Venda 6: Inês compra "Cem Anos de Solidão" e "O Alquimista"
INSERT INTO vendas (cliente_id, data_venda, valor_total, metodo_pagamento, status) VALUES
(5, '2024-08-03 11:20:00+00', 36.80, 'Multibanco', 'Concluída');
INSERT INTO itens_venda (venda_id, livro_id, quantidade, preco_unitario) VALUES
(6, 16, 1, 20.90),
(6, 17, 1, 15.90);

-- Venda 7: Ricardo compra "O Código Da Vinci"
INSERT INTO vendas (cliente_id, data_venda, valor_total, metodo_pagamento, status) VALUES
(4, '2024-08-10 16:00:00+00', 19.50, 'MBWay', 'Concluída');
INSERT INTO itens_venda (venda_id, livro_id, quantidade, preco_unitario) VALUES
(7, 20, 1, 19.50);

-- Venda 8: Beatriz compra "Harry Potter e a Câmara dos Segredos" e "O Senhor dos Anéis: A Sociedade do Anel"
INSERT INTO vendas (cliente_id, data_venda, valor_total, metodo_pagamento, status) VALUES
(3, '2024-08-18 10:45:00+00', 46.80, 'Cartão de Crédito', 'Concluída');
INSERT INTO itens_venda (venda_id, livro_id, quantidade, preco_unitario) VALUES
(8, 24, 1, 21.90),
(8, 25, 1, 24.90);

-- 13.8 Reservas em diferentes status
-- A inserção/atualização abaixo dispara automaticamente a trigger que
-- mantém livros.qtd_reservada sincronizado (seção 12.2).

-- Reserva Pendente: Inês reserva 2 unidades de "Memorial do Convento"
INSERT INTO reservas (cliente_id, livro_id, data_reserva, quantidade, status, data_limite) VALUES
(5, 2, '2024-08-01 10:00:00+00', 2, 'Pendente', '2024-08-15');

-- Reserva Concluída: Maria João reservou e já levantou "O Hobbit"
INSERT INTO reservas (cliente_id, livro_id, data_reserva, quantidade, status, data_limite) VALUES
(1, 7, '2024-07-05 11:00:00+00', 1, 'Pendente', '2024-07-20');
UPDATE reservas SET status = 'Concluída' WHERE cliente_id = 1 AND livro_id = 7;

-- Reserva Cancelada: António desistiu da reserva de "1984"
INSERT INTO reservas (cliente_id, livro_id, data_reserva, quantidade, status, data_limite) VALUES
(2, 3, '2024-07-10 09:00:00+00', 1, 'Pendente', '2024-07-25');
UPDATE reservas SET status = 'Cancelada' WHERE cliente_id = 2 AND livro_id = 3;

-- Reserva Expirada: Ricardo não levantou a reserva de "It: A Coisa" a tempo
INSERT INTO reservas (cliente_id, livro_id, data_reserva, quantidade, status, data_limite) VALUES
(4, 12, '2024-06-01 09:00:00+00', 1, 'Pendente', '2024-06-15');
UPDATE reservas SET status = 'Expirada' WHERE cliente_id = 4 AND livro_id = 12;

-- 13.9 VENDAS ADICIONAIS EM VOLUME (histórico de ~2 anos para análises de BI)
-- As 8 vendas manuais acima servem para conferir a lógica passo a passo.
-- Para um projeto de Business Intelligence (dashboards, tendências mensais,
-- sazonalidade, top produtos, etc.) é necessário um volume de dados muito
-- maior e distribuído no tempo. O bloco abaixo gera automaticamente ~250
-- vendas adicionais, com itens, distribuídas nos últimos 24 meses:
--   - 35% concentradas num pico de Natal (15 Nov a 24 Dez)
--   - 20% concentradas num pico de regresso às aulas (25 Ago a 15 Set)
--   - 45% distribuídas aleatoriamente ao longo dos 2 anos
-- Cada venda tem entre 1 e 3 livros, cada um com quantidade entre 1 e 3.
-- Todas as inserções em itens_venda continuam a passar pela trigger
-- trg_atualizar_estoque_venda (seção 12.1), portanto o estoque e o total de
-- vendas acumuladas dos livros ficam corretos no final. setseed() é usado
-- para que o resultado seja reprodutível entre execuções.

DO $$
DECLARE
    v_venda_id      BIGINT;
    v_cliente_id    BIGINT;
    v_cliente_ids   BIGINT[];
    v_total_clientes INT;
    v_num_itens     INT;
    v_livro_id      BIGINT;
    v_preco         NUMERIC(10,2);
    v_estoque       INT;
    v_qtd           INT;
    v_metodo        TEXT;
    v_metodos       TEXT[] := ARRAY['Dinheiro','Multibanco','MBWay','Cartão de Crédito','Cartão de Débito','Transferência'];
    v_data          TIMESTAMP WITH TIME ZONE;
    v_ano            INT;
    v_perfil        NUMERIC;
    i               INT;
    j               INT;
    v_total_vendas_geradas INT := 0;
BEGIN
    -- Reprodutibilidade: mesma "aleatoriedade" a cada execução do script
    PERFORM setseed(0.42);

    SELECT array_agg(id) INTO v_cliente_ids FROM clientes;
    v_total_clientes := array_length(v_cliente_ids, 1);

    FOR i IN 1..250 LOOP
        v_perfil := random();

        -- Escolha da data com reforço sazonal (sempre em anos já passados
        -- em relação a "hoje", para nunca gerar datas no futuro)
        IF v_perfil < 0.35 THEN
            -- Pico de Natal: 15 Nov a 24 Dez, há 1 ou 2 anos
            v_ano := extract(year FROM now())::int - (1 + floor(random() * 2)::int);
            v_data := make_timestamptz(v_ano, 11, 15, 9, 0, 0)
                      + (random() * interval '39 days')
                      + (random() * interval '10 hours');
        ELSIF v_perfil < 0.55 THEN
            -- Pico de regresso às aulas: 25 Ago a 15 Set, há 1 ou 2 anos
            v_ano := extract(year FROM now())::int - (1 + floor(random() * 2)::int);
            v_data := make_timestamptz(v_ano, 8, 25, 9, 0, 0)
                      + (random() * interval '21 days')
                      + (random() * interval '10 hours');
        ELSE
            -- Distribuição uniforme ao longo dos últimos 730 dias
            v_data := now() - (random() * interval '730 days');
        END IF;

        -- Cliente identificado em 70% das vendas; 30% venda ao balcão (NULL)
        IF random() < 0.7 THEN
            v_cliente_id := v_cliente_ids[1 + floor(random() * v_total_clientes)::int];
        ELSE
            v_cliente_id := NULL;
        END IF;

        v_metodo := v_metodos[1 + floor(random() * array_length(v_metodos, 1))::int];

        INSERT INTO vendas (cliente_id, data_venda, valor_total, metodo_pagamento, status)
        VALUES (v_cliente_id, v_data, 0, v_metodo, 'Concluída')
        RETURNING id INTO v_venda_id;

        v_num_itens := 1 + floor(random() * 3)::int; -- 1 a 3 itens por venda

        FOR j IN 1..v_num_itens LOOP
            -- Escolhe um livro aleatório que ainda tenha estoque confortável
            SELECT id, preco_venda, estoque_atual
              INTO v_livro_id, v_preco, v_estoque
              FROM livros
             WHERE estoque_atual > 3
             ORDER BY random()
             LIMIT 1;

            EXIT WHEN v_livro_id IS NULL; -- sem livros com estoque disponível

            v_qtd := 1 + floor(random() * 3)::int;
            IF v_qtd > v_estoque THEN
                v_qtd := v_estoque;
            END IF;

            BEGIN
                INSERT INTO itens_venda (venda_id, livro_id, quantidade, preco_unitario)
                VALUES (v_venda_id, v_livro_id, v_qtd, v_preco);
            EXCEPTION WHEN OTHERS THEN
                -- Em caso de estoque insuficiente de última hora, ignora
                -- este item e segue para o próximo.
                NULL;
            END;
        END LOOP;

        -- Recalcula o valor_total do cabeçalho a partir dos itens inseridos
        UPDATE vendas
           SET valor_total = COALESCE((SELECT SUM(subtotal) FROM itens_venda WHERE venda_id = v_venda_id), 0)
         WHERE id = v_venda_id;

        -- Remove a venda caso não tenha sido possível inserir nenhum item
        IF NOT EXISTS (SELECT 1 FROM itens_venda WHERE venda_id = v_venda_id) THEN
            DELETE FROM vendas WHERE id = v_venda_id;
        ELSE
            v_total_vendas_geradas := v_total_vendas_geradas + 1;
        END IF;
    END LOOP;

    RAISE NOTICE 'Vendas adicionais geradas com sucesso: %', v_total_vendas_geradas;
END $$;
