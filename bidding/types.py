"""类型定义：活动目录、定向、请求与竞价结果。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Set

NUM_DIMENSIONS = 5


@dataclass(frozen=True)
class Targeting:
    """广告组定向。某维度为 None 表示不限制；否则为非空允许值集合。"""

    content_categories: Optional[frozenset[int]] = None
    devices: Optional[frozenset[int]] = None
    hours: Optional[frozenset[int]] = None
    weekdays: Optional[frozenset[int]] = None
    dmas: Optional[frozenset[int]] = None

    def __post_init__(self) -> None:
        for name in (
            "content_categories",
            "devices",
            "hours",
            "weekdays",
            "dmas",
        ):
            values = getattr(self, name)
            if values is not None:
                if not isinstance(values, frozenset):
                    object.__setattr__(self, name, frozenset(values))
                    values = getattr(self, name)
                if len(values) == 0:
                    raise ValueError(f"定向集合 {name} 不能为空；不限制请用 None")


@dataclass(frozen=True)
class AdGroup:
    ad_group_id: int
    targeting: Targeting = field(default_factory=Targeting)


@dataclass(frozen=True)
class Campaign:
    campaign_id: int
    ad_groups: tuple[AdGroup, ...] = ()


@dataclass(frozen=True)
class Weights:
    """五个维度的整数权重，每个 0..1000，总和大于 0。"""

    content_category: int
    device: int
    hour: int
    weekday: int
    dma: int

    def __post_init__(self) -> None:
        values = (
            self.content_category,
            self.device,
            self.hour,
            self.weekday,
            self.dma,
        )
        for value in values:
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError("权重必须是整数")
            if not 0 <= value <= 1000:
                raise ValueError("权重必须在 0 到 1000 之间")
        if sum(values) <= 0:
            raise ValueError("五个权重之和必须大于 0")

    @property
    def total(self) -> int:
        return (
            self.content_category
            + self.device
            + self.hour
            + self.weekday
            + self.dma
        )


@dataclass(frozen=True)
class BidRequest:
    """单次竞价请求，每个维度恰有一个值（小时/星期已本地化）。"""

    content_category: int
    device: int
    hour: int
    weekday: int
    dma: int


@dataclass(frozen=True)
class BidResult:
    """竞价胜者。没有命中时引擎返回 None 而不是本对象。"""

    campaign_id: int
    ad_group_id: int
    cpm_milli_dollars: int
