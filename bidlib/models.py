"""类型定义：活动目录、定向与竞价请求。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Set, Tuple

NUM_CONTENT_CATEGORIES = 25
NUM_DEVICES = 4
NUM_HOURS = 24
NUM_WEEKDAYS = 7
NUM_DMAS = 210

DIMENSION_SIZES: Tuple[int, int, int, int, int] = (
    NUM_CONTENT_CATEGORIES,
    NUM_DEVICES,
    NUM_HOURS,
    NUM_WEEKDAYS,
    NUM_DMAS,
)


@dataclass(frozen=True)
class Targeting:
    """广告组定向。None 表示该维度不限制；否则为非空允许值集合。"""
    content_categories: Optional[frozenset] = None
    devices: Optional[frozenset] = None
    hours: Optional[frozenset] = None
    weekdays: Optional[frozenset] = None
    dmas: Optional[frozenset] = None


@dataclass(frozen=True)
class AdGroup:
    adgroup_id: int
    cpm_base: int  # 保留字段，当前定价公式固定
    targeting: Targeting = field(default_factory=Targeting)


@dataclass(frozen=True)
class Campaign:
    campaign_id: int
    adgroups: Tuple[AdGroup, ...]


@dataclass(frozen=True)
class BidRequest:
    content_category: int
    device: int
    hour: int
    weekday: int
    dma: int


@dataclass(frozen=True)
class BidResult:
    campaign_id: int
    adgroup_id: int
    cpm_milli: int  # 千分之一美元
