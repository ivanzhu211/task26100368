"""竞价引擎：进程内保存活动目录与当前权重。"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

from .models import (
    DIMENSION_SIZES,
    AdGroup,
    BidRequest,
    BidResult,
    Campaign,
)

BASE_CPM_MILLI = 500
WEIGHT_CPM_MILLI = 1000
NUM_DIMENSIONS = 5
MAX_WEIGHT = 1000


def _targeting_sets(adgroup: AdGroup):
    t = adgroup.targeting
    return (
        t.content_categories,
        t.devices,
        t.hours,
        t.weekdays,
        t.dmas,
    )


class BidEngine:
    """目录载入后不变；权重可整体替换，下一次竞价立即生效。"""

    def __init__(self) -> None:
        self._campaigns: Tuple[Campaign, ...] = ()
        self._weights: Tuple[int, int, int, int, int] = (1, 1, 1, 1, 1)

    def load_catalog(self, campaigns: Iterable[Campaign]) -> None:
        catalog = tuple(campaigns)
        seen_adgroups = set()
        for campaign in catalog:
            if not campaign.adgroups:
                raise ValueError(
                    f"campaign {campaign.campaign_id} has no adgroups"
                )
            for adgroup in campaign.adgroups:
                if adgroup.adgroup_id in seen_adgroups:
                    raise ValueError(
                        f"duplicate adgroup id {adgroup.adgroup_id}"
                    )
                seen_adgroups.add(adgroup.adgroup_id)
                for allowed, size in zip(
                    _targeting_sets(adgroup), DIMENSION_SIZES
                ):
                    if allowed is None:
                        continue
                    if not allowed:
                        raise ValueError(
                            f"adgroup {adgroup.adgroup_id} has an empty "
                            "targeting set"
                        )
                    for value in allowed:
                        if not 0 <= value < size:
                            raise ValueError(
                                f"adgroup {adgroup.adgroup_id} targeting "
                                f"value {value} out of range [0, {size})"
                            )
        self._campaigns = catalog

    def replace_weights(self, weights: Sequence[int]) -> None:
        new_weights = tuple(weights)
        if len(new_weights) != NUM_DIMENSIONS:
            raise ValueError("weights must contain exactly 5 values")
        for weight in new_weights:
            if not isinstance(weight, int) or isinstance(weight, bool):
                raise ValueError("weights must be integers")
            if not 0 <= weight <= MAX_WEIGHT:
                raise ValueError("each weight must be in [0, 1000]")
        if sum(new_weights) <= 0:
            raise ValueError("sum of weights must be positive")
        self._weights = new_weights  # 下一次竞价立即生效

    def bid(self, request: BidRequest) -> Optional[BidResult]:
        request_values = (
            request.content_category,
            request.device,
            request.hour,
            request.weekday,
            request.dma,
        )
        total_weight = sum(self._weights)
        best: Optional[BidResult] = None
        for campaign in self._campaigns:
            campaign_best: Optional[BidResult] = None
            for adgroup in campaign.adgroups:
                cpm = self._match_cpm(
                    adgroup, request_values, total_weight
                )
                if cpm is None:
                    continue
                candidate = BidResult(
                    campaign_id=campaign.campaign_id,
                    adgroup_id=adgroup.adgroup_id,
                    cpm_milli=cpm,
                )
                # 同一活动内只取最高报价，平价取广告组编号较小者
                if campaign_best is None or (
                    candidate.cpm_milli,
                    -candidate.adgroup_id,
                ) > (
                    campaign_best.cpm_milli,
                    -campaign_best.adgroup_id,
                ):
                    campaign_best = candidate
            if campaign_best is None:
                continue
            # 全局取最高报价，平价先比活动编号，再比广告组编号
            if best is None or (
                campaign_best.cpm_milli,
                -campaign_best.campaign_id,
                -campaign_best.adgroup_id,
            ) > (
                best.cpm_milli,
                -best.campaign_id,
                -best.adgroup_id,
            ):
                best = campaign_best
        return best

    def _match_cpm(
        self,
        adgroup: AdGroup,
        request_values: Tuple[int, int, int, int, int],
        total_weight: int,
    ) -> Optional[int]:
        contributed = 0
        for allowed, value, weight in zip(
            _targeting_sets(adgroup), request_values, self._weights
        ):
            if allowed is None:
                continue  # 不限制的维度总能通过，但不贡献权重
            if value not in allowed:
                return None
            contributed += weight
        return BASE_CPM_MILLI + WEIGHT_CPM_MILLI * contributed // total_weight
