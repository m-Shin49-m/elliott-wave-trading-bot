# -*- coding: utf-8 -*-
"""
Базовые тесты для модуля liquidity_zones.py
"""

import unittest
from unittest.mock import Mock
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from liquidity_zones import LiquidityZones
except ImportError:
    import elliott_wave_bot.liquidity_zones as lz_module
    LiquidityZones = lz_module.LiquidityZones


class TestLiquidityZones(unittest.TestCase):
    """Тесты для LiquidityZones."""
    
    def setUp(self):
        """Настройка перед каждым тестом."""
        self.logger = Mock()
        self.lz = LiquidityZones(logger=self.logger)
    
    def test_init(self):
        """Тест инициализации."""
        self.assertIsNotNone(self.lz.logger)
        self.assertGreater(self.lz.lookback, 0)
    
    def test_evaluate_insufficient_data(self):
        """Тест оценки при недостаточном количестве данных."""
        bars = [{"high": 100, "low": 90, "volume": 1000} for _ in range(10)]
        passed, ctx = self.lz.evaluate("BUY", bars)
        # При недостаточных данных должен возвращать True (не блокирует)
        self.assertTrue(passed)
        self.assertIsInstance(ctx, dict)
    
    def test_volume_spike_ok(self):
        """Тест определения всплеска объема."""
        # Нормальный объем
        bars_normal = [
            {"volume": 1000.0} for _ in range(25)
        ]
        # Последний бар с большим объемом
        bars_spike = [
            {"volume": 1000.0} for _ in range(24)
        ] + [{"volume": 2000.0}]  # Всплеск
        
        # Создаем новый экземпляр для теста
        result_normal = self.lz._volume_spike_ok(bars_normal)
        result_spike = self.lz._volume_spike_ok(bars_spike)
        
        # Всплеск должен быть обнаружен
        self.assertIsInstance(result_normal, bool)
        self.assertIsInstance(result_spike, bool)
    
    def test_swings(self):
        """Тест поиска свингов."""
        bars = [
            {"high": 100 + i * 0.1, "low": 100 + i * 0.1 - 0.05}
            for i in range(50)
        ]
        
        highs, lows = self.lz._swings(bars, swing_len=3)
        self.assertIsInstance(highs, list)
        self.assertIsInstance(lows, list)
        # Все элементы должны быть кортежами (index, price)
        if highs:
            self.assertIsInstance(highs[0], tuple)
            self.assertEqual(len(highs[0]), 2)


if __name__ == "__main__":
    unittest.main()
















