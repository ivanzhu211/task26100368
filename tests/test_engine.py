"""竞价引擎自动化测试。"""
import unittest

from bidlib import AdGroup, BidEngine, BidRequest, Campaign, Targeting

REQ = BidRequest(content_category=3, device=1, hour=10, weekday=2, dma=100)


def make_engine(weights, campaigns):
    engine = BidEngine()
    engine.load_catalog(campaigns)
    engine.replace_weights(weights)
    return engine


class OverlapTest(unittest.TestCase):
    """同一活动多个重叠广告组命中：只取最高报价，不累加。"""

    def test_overlapping_adgroups_not_accumulated(self):
        # 权重 (1,1,1,1,1)，总和 5
        # 组 101：内容+设备两维显式 -> 500 + 1000*2//5 = 900
        # 组 102：内容一维显式 -> 500 + 1000*1//5 = 700
        # 两组定向重叠，同时命中；活动报价应取 900 而非 1600
        campaign_a = Campaign(
            campaign_id=1,
            adgroups=(
                AdGroup(101, 0, Targeting(
                    content_categories=frozenset({3, 5}),
                    devices=frozenset({1}),
                )),
                AdGroup(102, 0, Targeting(
                    content_categories=frozenset({3}),
                )),
            ),
        )
        # 对照活动：单组四维显式 -> 500 + 1000*4//5 = 1300
        # 若活动 1 累加（1600）会错误获胜；正确行为是活动 2 以 1300 胜出
        campaign_b = Campaign(
            campaign_id=2,
            adgroups=(
                AdGroup(201, 0, Targeting(
                    content_categories=frozenset({3}),
                    devices=frozenset({1}),
                    hours=frozenset({10}),
                    weekdays=frozenset({2}),
                )),
            ),
        )
        engine = make_engine([1, 1, 1, 1, 1], [campaign_a, campaign_b])
        result = engine.bid(REQ)
        self.assertIsNotNone(result)
        self.assertEqual(result.campaign_id, 2)
        self.assertEqual(result.adgroup_id, 201)
        self.assertEqual(result.cpm_milli, 1300)

    def test_campaign_picks_highest_adgroup(self):
        campaign = Campaign(
            campaign_id=1,
            adgroups=(
                AdGroup(11, 0, Targeting(
                    content_categories=frozenset({3}),
                )),
                AdGroup(12, 0, Targeting(
                    content_categories=frozenset({3}),
                    devices=frozenset({1, 2}),
                )),
            ),
        )
        engine = make_engine([1, 1, 1, 1, 1], [campaign])
        result = engine.bid(REQ)
        self.assertEqual(result.adgroup_id, 12)
        self.assertEqual(result.cpm_milli, 900)


class UnrestrictedVsFullDomainTest(unittest.TestCase):
    """不限与显式全域定向贡献的权重不同。"""

    def test_unrestricted_contributes_nothing(self):
        # 全不限组报价恒为 500
        campaign = Campaign(
            campaign_id=1,
            adgroups=(AdGroup(1, 0, Targeting()),),
        )
        engine = make_engine([1, 1, 1, 1, 1], [campaign])
        result = engine.bid(REQ)
        self.assertEqual(result.cpm_milli, 500)

    def test_explicit_full_domain_contributes(self):
        # 五维均显式覆盖全域 -> 500 + 1000*5//5 = 1500
        full = Targeting(
            content_categories=frozenset(range(25)),
            devices=frozenset(range(4)),
            hours=frozenset(range(24)),
            weekdays=frozenset(range(7)),
            dmas=frozenset(range(210)),
        )
        campaign = Campaign(
            campaign_id=1,
            adgroups=(AdGroup(1, 0, full),),
        )
        engine = make_engine([1, 1, 1, 1, 1], [campaign])
        result = engine.bid(REQ)
        self.assertEqual(result.cpm_milli, 1500)

    def test_explicit_full_single_dimension(self):
        # 仅内容维显式覆盖全部 25 类，仍贡献该维权重
        # -> 500 + 1000*1//5 = 700，与不限的 500 不同
        campaign = Campaign(
            campaign_id=1,
            adgroups=(AdGroup(1, 0, Targeting(
                content_categories=frozenset(range(25)),
            )),),
        )
        engine = make_engine([1, 1, 1, 1, 1], [campaign])
        result = engine.bid(REQ)
        self.assertEqual(result.cpm_milli, 700)


class TieBreakTest(unittest.TestCase):
    """取整后同价按编号裁决。"""

    def test_tie_breaks_by_campaign_then_adgroup_id(self):
        # 权重 (1,2,997,1000,500)，总和 2500
        # 活动 20 组 201：仅设备维显式 -> 500 + 1000*2//2500 = 500
        # 活动 10 组 101：仅内容维显式 -> 500 + 1000*1//2500 = 500
        # 相关性不同但取整后同价，活动编号较小者胜
        campaign_high = Campaign(
            campaign_id=20,
            adgroups=(AdGroup(201, 0, Targeting(
                devices=frozenset({1}),
            )),),
        )
        campaign_low = Campaign(
            campaign_id=10,
            adgroups=(AdGroup(101, 0, Targeting(
                content_categories=frozenset({3}),
            )),),
        )
        engine = make_engine(
            [1, 2, 997, 1000, 500], [campaign_high, campaign_low]
        )
        result = engine.bid(REQ)
        self.assertEqual(result.cpm_milli, 500)
        self.assertEqual(result.campaign_id, 10)
        self.assertEqual(result.adgroup_id, 101)

    def test_tie_within_campaign_by_adgroup_id(self):
        # 同活动两组同价，取广告组编号较小者
        campaign = Campaign(
            campaign_id=1,
            adgroups=(
                AdGroup(9, 0, Targeting(
                    content_categories=frozenset({3}),
                )),
                AdGroup(4, 0, Targeting(
                    devices=frozenset({1}),
                )),
            ),
        )
        engine = make_engine([1, 1, 1, 1, 1], [campaign])
        result = engine.bid(REQ)
        self.assertEqual(result.cpm_milli, 700)
        self.assertEqual(result.adgroup_id, 4)


class WeightReplacementTest(unittest.TestCase):
    """替换权重后，下一次竞价立即使用新配置。"""

    def test_winner_changes_immediately_after_replacement(self):
        # 活动 1 组 1：仅内容维显式；活动 2 组 2：仅设备维显式
        campaign_a = Campaign(
            campaign_id=1,
            adgroups=(AdGroup(1, 0, Targeting(
                content_categories=frozenset({3}),
            )),),
        )
        campaign_b = Campaign(
            campaign_id=2,
            adgroups=(AdGroup(2, 0, Targeting(
                devices=frozenset({1}),
            )),),
        )
        engine = make_engine([1, 0, 0, 0, 0], [campaign_a, campaign_b])
        first = engine.bid(REQ)
        self.assertEqual(first.campaign_id, 1)
        self.assertEqual(first.cpm_milli, 1500)

        engine.replace_weights([0, 1, 0, 0, 0])
        second = engine.bid(REQ)
        self.assertEqual(second.campaign_id, 2)
        self.assertEqual(second.cpm_milli, 1500)


class EdgeCaseTest(unittest.TestCase):
    def test_no_match_returns_none(self):
        campaign = Campaign(
            campaign_id=1,
            adgroups=(AdGroup(1, 0, Targeting(
                content_categories=frozenset({7}),
            )),),
        )
        engine = make_engine([1, 1, 1, 1, 1], [campaign])
        self.assertIsNone(engine.bid(REQ))

    def test_invalid_weights_rejected(self):
        engine = BidEngine()
        with self.assertRaises(ValueError):
            engine.replace_weights([1, 1, 1, 1])
        with self.assertRaises(ValueError):
            engine.replace_weights([0, 0, 0, 0, 0])
        with self.assertRaises(ValueError):
            engine.replace_weights([1, 1, 1, 1, 1001])
        with self.assertRaises(ValueError):
            engine.replace_weights([-1, 1, 1, 1, 1])

    def test_duplicate_adgroup_id_rejected(self):
        campaigns = [
            Campaign(1, (AdGroup(5, 0),)),
            Campaign(2, (AdGroup(5, 0),)),
        ]
        engine = BidEngine()
        with self.assertRaises(ValueError):
            engine.load_catalog(campaigns)


if __name__ == "__main__":
    unittest.main()
