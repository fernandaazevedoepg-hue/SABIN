import os
import unittest

# A ligação só é criada durante a importação; estes testes não consultam a base de dados.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://sabin:sabin@localhost:5432/sabin_test",
)

import pandas as pd

from services.books_api import limpar_isbn, isbn_valido
from analysis.previsao import (
    FEATURES,
    avaliar_modelo,
    criar_features,
    prever_proximos_meses,
)


class TestISBN(unittest.TestCase):
    def test_limpar_isbn_remove_espacos_e_hifens(self):
        self.assertEqual(limpar_isbn(" 978-0-306-40615-7 "), "9780306406157")

    def test_isbn13_valido(self):
        self.assertTrue(isbn_valido("9780306406157"))

    def test_isbn10_valido(self):
        self.assertTrue(isbn_valido("0306406152"))

    def test_isbn10_com_x_valido(self):
        self.assertTrue(isbn_valido("080442957X"))

    def test_isbn_invalido(self):
        self.assertFalse(isbn_valido("9780306406158"))
        self.assertFalse(isbn_valido("texto"))


class TestPrevisao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        meses = pd.date_range("2023-01-01", periods=30, freq="MS")
        receitas = [500 + i * 12 + (i % 12) * 7 for i in range(len(meses))]
        cls.dados = pd.DataFrame({"mes": meses, "receita": receitas})
        cls.features = criar_features(cls.dados)

    def test_criar_features_remove_lags_incompletos(self):
        self.assertEqual(len(self.features), len(self.dados) - 3)
        self.assertTrue(set(FEATURES).issubset(self.features.columns))
        self.assertFalse(self.features[FEATURES].isna().any().any())

    def test_avaliacao_produz_metricas_finitas(self):
        mae, rmse, r2 = avaliar_modelo(self.features)
        self.assertGreaterEqual(mae, 0)
        self.assertGreaterEqual(rmse, 0)
        self.assertTrue(pd.notna(r2))

    def test_preve_tres_meses_futuros_nao_negativos(self):
        previsoes = prever_proximos_meses(self.dados, self.features, quantidade=3)
        self.assertEqual(len(previsoes), 3)
        self.assertEqual(
            list(previsoes["mes"]),
            list(pd.date_range("2025-07-01", periods=3, freq="MS")),
        )
        self.assertTrue((previsoes["receita_prevista"] >= 0).all())
        self.assertTrue(previsoes["receita_prevista"].notna().all())

    def test_avaliacao_rejeita_dados_insuficientes(self):
        with self.assertRaises(ValueError):
            avaliar_modelo(self.features.iloc[:6])


if __name__ == "__main__":
    unittest.main()
