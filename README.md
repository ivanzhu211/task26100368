# 上下文竞价库

供上层直接调用的进程内 Python 库，无接口层。活动目录与当前权重仅保存在进程内，
供营销团队离线比较不同定向权重下的竞价结果。

## 用法

```python
from bidlib import AdGroup, BidEngine, BidRequest, Campaign, Targeting

engine = BidEngine()
engine.load_catalog([
    Campaign(campaign_id=1, adgroups=(
        AdGroup(adgroup_id=101, cpm_base=0, targeting=Targeting(
            content_categories=frozenset({3, 5}),  # None 表示该维度不限
        )),
    )),
])
engine.replace_weights([1, 1, 1, 1, 1])  # 五个整数，各 0..1000，总和 > 0
result = engine.bid(BidRequest(
    content_category=3, device=1, hour=10, weekday=2, dma=100,
))
# result: BidResult(campaign_id, adgroup_id, cpm_milli) 或 None（无命中不出价）
```

- CPM 单位为千分之一美元：`500 + 1000 * 命中维度权重之和 // 五维权重总和`。
- 仅显式设置允许值集合的维度贡献权重；显式覆盖全域仍贡献。
- 同一活动命中多组只取最高报价；全局平价先比活动编号，再比广告组编号。

## 测试

```bash
python3 -m unittest discover -s tests -v
```
