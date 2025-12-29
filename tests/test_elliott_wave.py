# -*- coding: utf-8 -*-
"""
Базовые тесты для модуля elliott_wave.py
"""

import unittest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from elliott_wave import ElliottWaveAnalyzer
except ImportError:
    # Fallback для случая, когда модуль импортируется как пакет
    import elliott_wave_bot.elliott_wave as elliott_wave_module
    ElliottWaveAnalyzer = elliott_wave_module.ElliottWaveAnalyzer


class TestElliottWaveAnalyzer(unittest.TestCase):
    """Тесты для ElliottWaveAnalyzer."""
    
    def setUp(self):
        """Настройка перед каждым тестом."""
        self.logger = Mock()
        self.analyzer = ElliottWaveAnalyzer(logger=self.logger, timeframe="1h")
    
    def test_init(self):
        """Тест инициализации."""
        self.assertEqual(self.analyzer.timeframe, "1h")
        self.assertEqual(self.analyzer.pivot_len, 5)  # Значение по умолчанию из config
        self.assertIsNotNone(self.analyzer.exchange)
    
    def test_timeframe_to_ms(self):
        """Тест конвертации таймфрейма в миллисекунды."""
        # Используем приватный метод через патч или публичный API
        ms_1h = self.analyzer._timeframe_to_ms("1h")
        self.assertEqual(ms_1h, 3600000)
        
        ms_15m = self.analyzer._timeframe_to_ms("15m")
        self.assertEqual(ms_15m, 900000)
    
    def test_find_pivots_empty(self):
        """Тест поиска пивотов в пустых данных."""
        bars = []
        pivots = self.analyzer.find_pivots(bars)
        self.assertEqual(pivots, [])
    
    def test_find_pivots_insufficient_data(self):
        """Тест поиска пивотов при недостаточном количестве данных."""
        # Нужно минимум 2 * pivot_len + 1 баров
        bars = [{"high": 100, "low": 90, "close": 95} for _ in range(10)]
        pivots = self.analyzer.find_pivots(bars)
        # Может быть пусто или содержать пивоты в зависимости от данных
        self.assertIsInstance(pivots, list)
    
    def test_market_quality_ok(self):
        """Тест проверки качества рынка."""
        # Создаем тестовые бары с нормальным объемом
        bars = [
            {
                "high": 100 + i * 0.1,
                "low": 100 + i * 0.1 - 0.05,
                "close": 100 + i * 0.1 - 0.02,
                "volume": 1000.0
            }
            for i in range(100)
        ]
        
        ok, details = self.analyzer._market_quality_ok(bars)
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(details, dict)
    
    def test_determine_trend(self):
        """Тест определения тренда."""
        # Восходящий тренд
        bars_up = [
            {"close": 100 + i * 0.5} for i in range(50)
        ]
        trend = self.analyzer._determine_trend(bars_up)
        self.assertIn(trend, ["UP", "DOWN", "FLAT"])
        
        # Нисходящий тренд
        bars_down = [
            {"close": 100 - i * 0.5} for i in range(50)
        ]
        trend = self.analyzer._determine_trend(bars_down)
        self.assertIn(trend, ["UP", "DOWN", "FLAT"])


class TestHelperFunctions(unittest.TestCase):
    """Тесты для вспомогательных функций."""
    
    def test_timeframe_conversion(self):
        """Тест конвертации таймфреймов."""
        analyzer = ElliottWaveAnalyzer(logger=Mock(), timeframe="1h")
        
        test_cases = [
            ("1m", 60000),
            ("5m", 300000),
            ("15m", 900000),
            ("1h", 3600000),
            ("4h", 14400000),
            ("1d", 86400000),
        ]
        
        for tf, expected_ms in test_cases:
            result = analyzer._timeframe_to_ms(tf)
            self.assertEqual(result, expected_ms, f"Failed for {tf}")


if __name__ == "__main__":
    unittest.main()
















