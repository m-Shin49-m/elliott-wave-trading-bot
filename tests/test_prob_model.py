# -*- coding: utf-8 -*-
"""
Базовые тесты для модуля prob_model.py
"""

import unittest
import sys
import json
import tempfile
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from prob_model import load_model, estimate, ProbEstimate, _bucket_quality
except ImportError:
    import elliott_wave_bot.prob_model as pm_module
    load_model = pm_module.load_model
    estimate = pm_module.estimate
    ProbEstimate = pm_module.ProbEstimate
    _bucket_quality = pm_module._bucket_quality


class TestProbModel(unittest.TestCase):
    """Тесты для вероятностной модели."""
    
    def setUp(self):
        """Настройка перед каждым тестом."""
        # Создаем временный файл модели для тестов
        self.test_model = {
            "buckets": {
                "ELLIOTT|BUY|UP|60-69": {
                    "n": 100,
                    "p_tp1": 0.65,
                    "p_tp2": 0.45,
                    "p_tp3": 0.25,
                    "p_sl": 0.20,
                    "avg_r": 1.5
                }
            }
        }
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(self.test_model, self.temp_file)
        self.temp_file.close()
    
    def tearDown(self):
        """Очистка после каждого теста."""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
    
    def test_load_model(self):
        """Тест загрузки модели."""
        model = load_model(self.temp_file.name)
        self.assertIsNotNone(model)
        self.assertIn("buckets", model)
    
    def test_load_model_nonexistent(self):
        """Тест загрузки несуществующего файла."""
        model = load_model("/nonexistent/path/model.json")
        self.assertIsNone(model)
    
    def test_bucket_quality(self):
        """Тест бакетирования качества."""
        self.assertEqual(_bucket_quality(45), "<50")
        self.assertEqual(_bucket_quality(55), "50-59")
        self.assertEqual(_bucket_quality(65), "60-69")
        self.assertEqual(_bucket_quality(75), "70-79")
        self.assertEqual(_bucket_quality(85), "80+")
    
    def test_estimate(self):
        """Тест оценки вероятности."""
        model = load_model(self.temp_file.name)
        result = estimate(
            model,
            setup="ELLIOTT",
            direction="BUY",
            trend="UP",
            quality=65
        )
        
        self.assertIsNotNone(result)
        self.assertIsInstance(result, ProbEstimate)
        self.assertEqual(result.n, 100)
        self.assertAlmostEqual(result.p_tp1, 0.65, places=2)
    
    def test_estimate_no_match(self):
        """Тест оценки при отсутствии совпадения."""
        model = load_model(self.temp_file.name)
        result = estimate(
            model,
            setup="UNKNOWN",
            direction="SELL",
            trend="DOWN",
            quality=50
        )
        # Должен вернуть None при отсутствии данных
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
















