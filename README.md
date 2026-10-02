# 上下文竞价库

进程内的上下文竞价库，供上层直接调用（无接口层）。活动目录与当前权重规则仅保存在进程内，支持载入目录、替换权重配置和单次竞价。

## 用法

```python
from bidding import AdGroup, AuctionEngine, BidRequest, Campaign, Targeting, Weights

engine = AuctionEngine()
engine.load_catalog([
    Campaign(1, (
        AdGroup(11),                                  # 不限，命中报价 500
        AdGroup(12, Targeting(devices={1, 2})),       # 显式定向，命中贡献设备权重
    )),
])
engine.set_weights(Weights(200, 200, 200, 200, 200))  # 五个维度权重，0..1000，总和 > 0

result = engine.bid(BidRequest(content_category=3, device=1, hour=10, weekday=2, dma=42))
# result: BidResult(campaign_id, ad_group_id, cpm_milli_dollars)；无命中时为 None
```

- CPM 单位为千分之一美元：`500 + 1000 * 命中组贡献权重之和 // 五维权重总和`。
- 同一活动命中多个广告组只取最高报价；全局取 CPM 最高者，平价先比活动编号再比广告组编号（均取较小者）。
- `set_weights` 一次提交完整五个值，下一次竞价立即生效。

## 测试

```bash
python3 -m pytest tests/ -q
```
