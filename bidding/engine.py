"""竞价引擎：进程内保存活动目录与当前权重规则。"""

from __future__ import annotations

from typing import Iterable, Optional

from .types import AdGroup, BidRequest, BidResult, Campaign, Weights

BASE_CPM = 500
CPM_SCALE = 1000


class AuctionEngine:
    def __init__(self) -> None:
        self._campaigns: tuple[Campaign, ...] = ()
        self._weights: Optional[Weights] = None

    def load_catalog(self, campaigns: Iterable[Campaign]) -> None:
        """载入活动目录（载入后不变）。"""
        catalog = tuple(campaigns)
        seen_ad_group_ids: set[int] = set()
        for campaign in catalog:
            for ad_group in campaign.ad_groups:
                if ad_group.ad_group_id in seen_ad_group_ids:
                    raise ValueError(
                        f"广告组编号 {ad_group.ad_group_id} 重复，必须全局唯一"
                    )
                seen_ad_group_ids.add(ad_group.ad_group_id)
        self._campaigns = catalog

    def set_weights(self, weights: Weights) -> None:
        """一次性替换完整的五个权重，下一次竞价立即生效。"""
        if not isinstance(weights, Weights):
            raise TypeError("weights 必须是 Weights 实例")
        self._weights = weights

    def bid(self, request: BidRequest) -> Optional[BidResult]:
        """单次竞价；无命中时返回 None。"""
        if self._weights is None:
            raise RuntimeError("尚未设置权重规则，请先调用 set_weights")
        weights = self._weights
        best: Optional[BidResult] = None
        for campaign in self._campaigns:
            campaign_best: Optional[BidResult] = None
            for ad_group in campaign.ad_groups:
                cpm = self._match_cpm(ad_group, request, weights)
                if cpm is None:
                    continue
                if campaign_best is None or (cpm, -ad_group.ad_group_id) > (
                    campaign_best.cpm_milli_dollars,
                    -campaign_best.ad_group_id,
                ):
                    campaign_best = BidResult(
                        campaign_id=campaign.campaign_id,
                        ad_group_id=ad_group.ad_group_id,
                        cpm_milli_dollars=cpm,
                    )
            if campaign_best is not None and (
                best is None
                or (
                    campaign_best.cpm_milli_dollars,
                    -campaign_best.campaign_id,
                    -campaign_best.ad_group_id,
                )
                > (
                    best.cpm_milli_dollars,
                    -best.campaign_id,
                    -best.ad_group_id,
                )
            ):
                best = campaign_best
        return best

    @staticmethod
    def _match_cpm(
        ad_group: AdGroup, request: BidRequest, weights: Weights
    ) -> Optional[int]:
        """命中返回整数 CPM，未命中返回 None。仅显式定向的维度贡献权重。"""
        targeting = ad_group.targeting
        contributed = 0
        for allowed, value, weight in (
            (
                targeting.content_categories,
                request.content_category,
                weights.content_category,
            ),
            (targeting.devices, request.device, weights.device),
            (targeting.hours, request.hour, weights.hour),
            (targeting.weekdays, request.weekday, weights.weekday),
            (targeting.dmas, request.dma, weights.dma),
        ):
            if allowed is None:
                continue
            if value not in allowed:
                return None
            contributed += weight
        return BASE_CPM + (CPM_SCALE * contributed) // weights.total
