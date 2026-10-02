"""上下文竞价库的自动化测试。"""

import pytest

from bidding import (
    AdGroup,
    AuctionEngine,
    BidRequest,
    Campaign,
    Targeting,
    Weights,
)

REQUEST = BidRequest(content_category=3, device=1, hour=10, weekday=2, dma=42)


def make_engine(campaigns, weights):
    engine = AuctionEngine()
    engine.load_catalog(campaigns)
    engine.set_weights(weights)
    return engine


class TestOverlappingAdGroups:
    """同一活动多个重叠广告组命中：只取最高报价，不累加。"""

    def test_campaign_bid_is_max_not_sum(self):
        weights = Weights(0, 100, 100, 0, 0)
        overlapping = Campaign(
            1,
            (
                AdGroup(11, Targeting(devices={1, 2})),
                AdGroup(12, Targeting(hours={10, 11})),
            ),
        )
        stronger = Campaign(
            2,
            (AdGroup(21, Targeting(devices={1}, hours={10})),),
        )
        engine = make_engine([overlapping, stronger], weights)

        result = engine.bid(REQUEST)

        # 活动 1 两个组各报价 1000，若累加为 2000；只取最高则为 1000，
        # 因此活动 2 以 1500 胜出。
        assert result is not None
        assert result.campaign_id == 2
        assert result.ad_group_id == 21
        assert result.cpm_milli_dollars == 1500

    def test_highest_group_within_campaign_is_used(self):
        weights = Weights(0, 100, 100, 0, 0)
        campaign = Campaign(
            1,
            (
                AdGroup(11, Targeting(devices={1})),
                AdGroup(12, Targeting(devices={1}, hours={10})),
                AdGroup(13),
            ),
        )
        engine = make_engine([campaign], weights)

        result = engine.bid(REQUEST)

        assert result is not None
        assert result.ad_group_id == 12
        assert result.cpm_milli_dollars == 1500


class TestUnrestrictedVsExplicitFullDomain:
    """不限与显式全域定向贡献的权重不同。"""

    def test_unrestricted_contributes_nothing(self):
        weights = Weights(200, 200, 200, 200, 200)
        engine = make_engine([Campaign(1, (AdGroup(11),))], weights)

        result = engine.bid(REQUEST)

        assert result is not None
        assert result.cpm_milli_dollars == 500

    def test_explicit_full_domain_still_contributes(self):
        weights = Weights(200, 200, 200, 200, 200)
        full_domain = Targeting(
            content_categories=frozenset(range(25)),
            devices=frozenset(range(4)),
            hours=frozenset(range(24)),
            weekdays=frozenset(range(7)),
            dmas=frozenset(range(210)),
        )
        engine = make_engine(
            [Campaign(1, (AdGroup(11, full_domain),))], weights
        )

        result = engine.bid(REQUEST)

        assert result is not None
        assert result.cpm_milli_dollars == 1500

    def test_single_explicit_full_domain_dimension(self):
        weights = Weights(200, 200, 200, 200, 200)
        engine = make_engine(
            [Campaign(1, (AdGroup(11, Targeting(devices=frozenset(range(4)))),))],
            weights,
        )

        result = engine.bid(REQUEST)

        assert result is not None
        assert result.cpm_milli_dollars == 700


class TestFlooringTieBreak:
    """不同相关性取整后同价时按编号裁决。"""

    # 权重 (1000, 1000, 999, 0, 0)，总和 2999：
    # 贡献 2000 -> 500 + 2_000_000 // 2999 = 1166
    # 贡献 1999 -> 500 + 1_999_000 // 2999 = 1166（同价）
    WEIGHTS = Weights(1000, 1000, 999, 0, 0)

    def build_engine(self):
        campaigns = [
            Campaign(1, (AdGroup(11, Targeting(content_categories={3}, devices={1})),)),
            Campaign(2, (AdGroup(21, Targeting(content_categories={3}, hours={10})),)),
        ]
        return make_engine(campaigns, self.WEIGHTS)

    def test_same_price_after_flooring(self):
        engine = self.build_engine()

        result = engine.bid(REQUEST)

        # 两组相关性不同（2000 对 1999），取整后同为 1166。
        assert result is not None
        assert result.cpm_milli_dollars == 1166

    def test_tie_broken_by_smaller_campaign_id(self):
        engine = self.build_engine()

        result = engine.bid(REQUEST)

        assert result is not None
        assert result.campaign_id == 1
        assert result.ad_group_id == 11

    def test_tie_broken_by_smaller_ad_group_id(self):
        campaigns = [
            Campaign(
                1,
                (
                    AdGroup(9, Targeting(content_categories={3}, devices={1})),
                    AdGroup(4, Targeting(content_categories={3}, devices={1})),
                ),
            ),
        ]
        engine = make_engine(campaigns, self.WEIGHTS)

        result = engine.bid(REQUEST)

        assert result is not None
        assert result.ad_group_id == 4


class TestWeightReplacement:
    """替换权重后，下一次竞价立即使用新配置。"""

    def test_winner_changes_immediately_after_replacement(self):
        campaigns = [
            Campaign(1, (AdGroup(11, Targeting(content_categories={3}, devices={1})),)),
            Campaign(2, (AdGroup(21, Targeting(content_categories={3}, hours={10})),)),
        ]
        engine = make_engine(campaigns, Weights(1000, 1000, 999, 0, 0))

        first = engine.bid(REQUEST)
        assert first is not None
        assert first.campaign_id == 1

        # 新权重只奖励小时维度：活动 1 贡献 0 报价 500，活动 2 报价 1500。
        engine.set_weights(Weights(0, 0, 999, 0, 0))

        second = engine.bid(REQUEST)
        assert second is not None
        assert second.campaign_id == 2
        assert second.ad_group_id == 21
        assert second.cpm_milli_dollars == 1500


class TestMatchingRules:
    def test_no_hit_returns_none(self):
        engine = make_engine(
            [Campaign(1, (AdGroup(11, Targeting(devices={2, 3})),))],
            Weights(100, 100, 100, 100, 100),
        )

        assert engine.bid(REQUEST) is None

    def test_or_within_dimension_and_across_dimensions(self):
        ad_group = AdGroup(
            11,
            Targeting(devices={1, 2}, hours={9, 10}, weekdays={5}),
        )
        engine = make_engine(
            [Campaign(1, (ad_group,))], Weights(100, 100, 100, 100, 100)
        )

        # 星期维度不命中（请求为 2，允许集合为 {5}），整组不命中。
        assert engine.bid(REQUEST) is None
        # 各维度均在允许集合内则命中。
        hit = BidRequest(content_category=3, device=2, hour=9, weekday=5, dma=42)
        assert engine.bid(hit) is not None

    def test_bid_without_weights_raises(self):
        engine = AuctionEngine()
        engine.load_catalog([Campaign(1, (AdGroup(11),))])

        with pytest.raises(RuntimeError):
            engine.bid(REQUEST)

    def test_duplicate_ad_group_id_rejected(self):
        engine = AuctionEngine()
        campaigns = [
            Campaign(1, (AdGroup(11),)),
            Campaign(2, (AdGroup(11),)),
        ]

        with pytest.raises(ValueError):
            engine.load_catalog(campaigns)

    def test_invalid_weights_rejected(self):
        with pytest.raises(ValueError):
            Weights(0, 0, 0, 0, 0)
        with pytest.raises(ValueError):
            Weights(1001, 0, 0, 0, 0)
        with pytest.raises(ValueError):
            Weights(-1, 0, 0, 0, 1)
