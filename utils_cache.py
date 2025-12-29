# -*- coding: utf-8 -*-
"""
Утилиты для кэширования данных и оптимизации производительности.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple
from collections import OrderedDict


class DataCache:
    """
    Простой LRU кэш для данных свечей.
    Ключ: (pair, timeframe, limit)
    Значение: (timestamp, data)
    """
    
    def __init__(self, max_size: int = 10, ttl_seconds: int = 30):
        """
        Args:
            max_size: Максимальное количество записей в кэше
            ttl_seconds: Время жизни кэша в секундах
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[Tuple[str, str, int], Tuple[float, List[Dict]]] = OrderedDict()
    
    def get(self, pair: str, timeframe: str, limit: int) -> Optional[List[Dict]]:
        """Получить данные из кэша, если они актуальны."""
        key = (pair, timeframe, limit)
        if key not in self._cache:
            return None
        
        timestamp, data = self._cache[key]
        age = time.time() - timestamp
        
        if age > self.ttl_seconds:
            # Устарело, удаляем
            del self._cache[key]
            return None
        
        # Перемещаем в конец (LRU)
        self._cache.move_to_end(key)
        return data
    
    def set(self, pair: str, timeframe: str, limit: int, data: List[Dict]) -> None:
        """Сохранить данные в кэш."""
        key = (pair, timeframe, limit)
        timestamp = time.time()
        
        # Если кэш переполнен, удаляем самый старый
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
        
        self._cache[key] = (timestamp, data)
        self._cache.move_to_end(key)
    
    def clear(self) -> None:
        """Очистить кэш."""
        self._cache.clear()
    
    def size(self) -> int:
        """Текущий размер кэша."""
        return len(self._cache)


# Глобальный экземпляр кэша
_global_cache: Optional[DataCache] = None


def get_cache() -> DataCache:
    """Получить глобальный экземпляр кэша."""
    global _global_cache
    if _global_cache is None:
        _global_cache = DataCache(max_size=10, ttl_seconds=30)
    return _global_cache


def clear_cache() -> None:
    """Очистить глобальный кэш."""
    global _global_cache
    if _global_cache is not None:
        _global_cache.clear()
















