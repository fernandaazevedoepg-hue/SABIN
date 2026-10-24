"""Testes unitários TU01–TU15 (Tabela 28 do relatório).

    python -m unittest -v tests.test_unitarios
"""

import os
import unittest

import pandas as pd

# Os módulos criam a ligação à base de dados ao serem importados. A ligação
# só é aberta quando é usada, por isso um endereço fictício chega para os
# testes (se o .env existir, é usado o endereço do .env).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://teste:teste@localhost:5432/teste",
)

from analysis.kpis import calcular_kpis  # noqa: E402
from analysis.stock_alerts import (  # noqa: E402
    calcular_nivel,
    calcular_quantidade_recomendada,
)
from services.book_catalog import isbn_valido, normalizar_isbn  # noqa: E402


# As médias mensais são calculadas com 3 meses de vendas, por isso 4,67 e
# 2,33 são na verdade 14/3 e 7/3. Usa-se o valor exato: com 4,67 arredondado,
# 3 × 4,67 − 1 = 13,01 e a função (que arredonda para cima) daria 14.
MEDIA_14_EM_3_MESES = 14 / 3
MEDIA_7_EM_3_MESES = 7 / 3


class TestesStock(unittest.TestCase):
    """TU01–TU08: nível de stock e quantidade a repor (secção 4.8.7)."""

    def test_TU01_nivel_critico_por_cobertura(self):
        self.assertEqual(calcular_nivel(1, MEDIA_14_EM_3_MESES, 1 / MEDIA_14_EM_3_MESES), "Crítico")

    def test_TU02_nivel_atencao(self):
        self.assertEqual(calcular_nivel(4, MEDIA_7_EM_3_MESES, 4 / MEDIA_7_EM_3_MESES), "Atenção")

    def test_TU03_sem_procura_recente(self):
        self.assertEqual(calcular_nivel(15, 0, None), "Sem procura recente")

    def test_TU04_stock_zero_e_critico(self):
        self.assertEqual(calcular_nivel(0, 0, None), "Crítico")

    def test_TU05_nivel_normal(self):
        self.assertEqual(calcular_nivel(60, 1.67, 36), "Normal")

    def test_TU06_quantidade_critico(self):
        self.assertEqual(calcular_quantidade_recomendada(1, MEDIA_14_EM_3_MESES, "Crítico"), 13)

    def test_TU07_quantidade_atencao(self):
        self.assertEqual(calcular_quantidade_recomendada(4, MEDIA_7_EM_3_MESES, "Atenção"), 3)

    def test_TU08_quantidade_normal(self):
        self.assertEqual(calcular_quantidade_recomendada(60, 1.67, "Normal"), 0)


class TestesIsbn(unittest.TestCase):
    """TU09–TU12: validação e limpeza do ISBN."""

    def test_TU09_isbn13_valido(self):
        self.assertTrue(isbn_valido("9789727086535"))

    def test_TU10_isbn13_digito_errado(self):
        self.assertFalse(isbn_valido("9789727086536"))

    def test_TU11_isbn10_com_x(self):
        self.assertTrue(isbn_valido("080442957X"))

    def test_TU12_limpar_isbn(self):
        self.assertEqual(normalizar_isbn("978-972-708 653-5"), "9789727086535")


class TestesKpis(unittest.TestCase):
    """TU13–TU15: indicadores de vendas."""

    def setUp(self):
        # 2 vendas, 3 linhas de venda, 6 unidades e 37 € de receita.
        self.vendas = pd.DataFrame(
            {
                "venda_id_origem": [1, 1, 2],
                "item_venda_id_origem": [10, 11, 12],
                "quantidade": [2, 1, 3],
                "preco_unitario": [5.00, 12.00, 5.00],
                "subtotal": [10.00, 12.00, 15.00],
            }
        )

    def test_TU13_kpis_basicos(self):
        kpis = calcular_kpis(self.vendas)
        self.assertEqual(kpis["numero_vendas"], 2)
        self.assertEqual(kpis["linhas_venda"], 3)
        self.assertEqual(kpis["unidades_vendidas"], 6)
        self.assertAlmostEqual(kpis["receita_total"], 37.00)

    def test_TU14_ticket_medio(self):
        self.assertAlmostEqual(calcular_kpis(self.vendas)["ticket_medio"], 18.50)

    def test_TU15_sem_vendas_nao_da_erro(self):
        vazio = self.vendas.iloc[0:0]
        kpis = calcular_kpis(vazio)
        self.assertEqual(kpis["numero_vendas"], 0)
        self.assertEqual(kpis["ticket_medio"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
