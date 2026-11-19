# XAUUSD Smart Money Concepts for MetaTrader 5

本目录是 [Prasad1612/smart-money-concept](https://github.com/Prasad1612/smart-money-concept) 的本地改编，不是已推送到 GitHub 的 fork。原项目用 yfinance 分析股票；这里改成通过 Python `MetaTrader5` 包读取本机终端的外汇黄金行情，并给出可回测、可干跑的交易规则。

原分析逻辑（BOS、CHoCH、订单块、FVG、溢价/折价）仍在 `smart_money_concepts/smc.py`。交易规则是新增的，只做黄金顺势回撤，不保证盈利。

## 交易规则

- 品种默认 `XAUUSD`。K 线是 Bid 价，买入按点差计入成本。
- 方向看 H1 摆动结构，入场看 M15 内部 BOS/CHoCH。两者方向必须一致。
- 多单只在区间 62% 以下寻找，空单只在 38% 以上寻找。
- 最近 8 根 K 线必须回踩同向订单块或公允价值缺口，止损放在该区域外侧再加 0.2 ATR。
- 止损距离限制在 80 到 2500 点。默认 2R 止盈。
- 单笔风险默认权益的 0.5%。手数按品种 tick value 向下取整，不会为了凑最小手数而放大风险。
- 只在 K 线时间 09:00–22:00 开仓，周五 21:00 后不再开仓，并在回测里按市价平掉持仓，避开周末跳空。
- 点差超过 40 点不做。同一 magic `161211` 同时只持有一笔。

K 线时间是 MT5 返回的经纪商服务器时间。若服务器不是 UTC+2/+3，用参数调整时段。

## 安装

使用已经安装 `MetaTrader5` 的 Windows Python，例如 `D:\Python312\python.exe`。终端需要已经登录并打开。

```powershell
D:\Python312\python.exe -m pip install -r requirements.txt
```

## 用法

```powershell
# 结构分析，图保存到 reports\
D:\Python312\python.exe -m smart_money_concepts.cli analyze --symbol XAUUSD --timeframe M15 --bars 1500

# 回测。成交在信号下一根 K 线开盘，同一根同时碰到止损和止盈时按止损处理。
D:\Python312\python.exe -m smart_money_concepts.cli backtest --symbol XAUUSD --bars 8000 --balance 10000

# 只评估最新已收盘 K 线，不会下单。
D:\Python312\python.exe -m smart_money_concepts.cli live --symbol XAUUSD

# 真正下单必须同时带上这两个开关。先在模拟账户验证。
D:\Python312\python.exe -m smart_money_concepts.cli live --symbol XAUUSD --send --confirm-live
```

`live` 默认是干跑。它只管理 magic 为 161211 的持仓，不会平掉终端里的其他黄金单。

## 测试

```powershell
D:\Python312\python.exe -m unittest tests.test_gold_strategy -v
```

## 说明

这是研究和教育用途的规则实现，不是投资建议。回测没有计入隔夜利息，手续费默认为 0。实盘前请核对品种名、点差、最小手数和账户模式。

## MQL5 EA

`mql5/Experts/SmartMoneyConceptsEA` 是同一套规则的 MetaTrader 5 专家顾问，结构引擎在 `mql5/Include/SmartMoneyConceptsEA/SMCEngine.mqh`。算法对齐 LuxAlgo Smart Money Concepts（CC BY-NC-SA 4.0，非商用）。

- 默认 `InpAllowLive=false`，实盘会拒绝启动；只在策略测试器里跑。
- 方向看 H4 摆动趋势，入场看图表周期内部 BOS/CHoCH。
- 多单只在 62% 以下、空单只在 38% 以上，并要求最近 8 根回踩未缓解 OB/FVG。
- 单笔风险 0.5%，止盈 2R，同时只持有 1 单。

把源码拷到终端 `MQL5/Experts` 与 `MQL5/Include` 后编译 `SmartMoneyConceptsEA.mq5`。回测品种 `XAUUSD`，H4 偏差，图表周期分别用 H4 / H1 / M30。

回测（XAUUSD，H4 偏差，M1 OHLC，初始资金 10000，杠杆 500，2023.01.01–2026.11.19）：

| 图表周期 | 净利 | 最大净值回撤 | 交易数 | 胜率 | 利润因子 |
| --- | --- | --- | --- | --- | --- |
| H4 | -175.46 | 180.70 (1.81%) | 4 | 0.00% | 0.00 |
| H1 | +203.47 | 397.14 (3.86%) | 36 | 38.89% | 1.20 |
| M30 | -241.53 | 574.25 (5.68%) | 62 | 32.26% | 0.87 |

这是研究和教育用途的实现，不是投资建议。默认禁止实盘。
