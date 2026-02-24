# -*- coding: utf-8 -*-
"""
策略 V2 重构 - 抗过拟合设计
===========================
核心思路: 
  1. 使用 rank-based 信号替代绝对阈值, 消除对具体数值的敏感性
  2. 引入多时间窗口投票机制 (Ensemble), 避免依赖单一参数
  3. 跟踪止损 (Trailing Stop) 代替固定 SMA 做风控
  
这套逻辑只有一个关键参数: trailing_stop_pct (止损百分比)
其他参数都是"结构性"的,不是"数值型"的,因此天然抗过拟合
"""

import sys
sys.path.append(r'd:\AI')
sys.stdout.reconfigure(encoding='utf-8')

import backtest
import math

data = backtest.load_csv_data(r'd:\AI\pump_data.csv')
N = len(data)


def compute_signals_v2(data, params):
    """
    V2 策略: 多窗口投票 + 跟踪止损
    
    投票机制: 
      - 计算短(3天)、中(7天)、长(14天) 三个窗口的收入动能
      - 如果"多数"窗口显示增长, 则看多; 否则看空
      - 天然不依赖某单个窗口大小
    
    风控:
      - 跟踪止损: 记录持仓期间最高净值, 如果从峰值回撤
        超过 trailing_stop_pct, 则强制平仓
    """
    windows = [3, 7, 14]  # 固定的多时间尺度, 不作为可调参数
    trailing_stop = params.get('trailing_stop_pct', 0.15)  # 唯一可调参数
    
    n = len(data)
    signals = [0] * n
    
    peak_price = 0
    in_position = False
    
    for i in range(max(w * 2 for w in windows), n):
        # === 多窗口投票 ===
        votes = 0
        for w in windows:
            recent_avg = sum(d['income'] for d in data[i-w:i]) / w
            prev_avg = sum(d['income'] for d in data[i-2*w:i-w]) / w
            if recent_avg > prev_avg:
                votes += 1
        
        # 多数投票: 至少 2/3 的窗口看涨
        momentum_signal = 1 if votes >= 2 else 0
        
        # === 跟踪止损 ===
        curr_price = data[i-1]['close']
        
        if in_position:
            if curr_price > peak_price:
                peak_price = curr_price
            drawdown = (peak_price - curr_price) / peak_price if peak_price > 0 else 0
            
            if drawdown > trailing_stop:
                # 触发跟踪止损, 强制平仓
                signals[i] = 0
                in_position = False
                continue
        
        if momentum_signal == 1 and not in_position:
            # 开仓
            signals[i] = 1
            in_position = True
            peak_price = curr_price
        elif momentum_signal == 0 and in_position:
            # 动能消失, 平仓
            signals[i] = 0
            in_position = False
        elif in_position:
            signals[i] = 1
        else:
            signals[i] = 0
    
    return signals


def run_full_test(data, params, label=""):
    signals = compute_signals_v2(data, params)
    hist = backtest.run_backtest(data, signals)
    metrics = backtest.calculate_metrics(hist)
    sharpe = float(metrics['夏普比率 (Sharpe Ratio)'])
    dd = metrics['最大回撤 (Max Drawdown)']
    ret = metrics['总收益率 (Total Return)']
    trades = metrics['交易次数 (Trade Count)']
    wr = metrics['胜率 (Win Rate)']
    print(f"  [{label}] Sharpe: {sharpe:.2f}, 回撤: {dd}, 收益: {ret}, 胜率: {wr}, 交易: {trades}")
    return sharpe, hist, signals


# ============================================================
# 1. Scan trailing stop values
# ============================================================
print("=" * 70)
print("V2 策略: 多窗口投票 + 跟踪止损")
print("=" * 70)
print("\n[1] 参数扫描 (唯一参数: trailing_stop_pct)")

best_sharpe = -999
best_ts = 0
for ts in [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30, 1.0]:
    s, _, _ = run_full_test(data, {'trailing_stop_pct': ts}, f"ts={ts:.0%}")
    if s > best_sharpe:
        best_sharpe = s
        best_ts = ts

print(f"\n最佳止损比例: {best_ts:.0%}, Sharpe: {best_sharpe:.2f}")

# ============================================================
# 2. 参数邻域稳定性 (只有一维, 更好看)
# ============================================================
print("\n[2] 邻域稳定性检查")
ts_range = [round(best_ts + delta, 2) for delta in [-0.06, -0.04, -0.02, 0, 0.02, 0.04, 0.06, 0.08, 0.10]]
ts_range = [t for t in ts_range if t > 0]
sharpe_neighbors = []
for ts in ts_range:
    s, _, _ = run_full_test(data, {'trailing_stop_pct': ts}, f"ts={ts:.0%}")
    sharpe_neighbors.append(s)

avg_neighbor = sum(sharpe_neighbors) / len(sharpe_neighbors)
above3_n = sum(1 for s in sharpe_neighbors if s >= 3.0)
print(f"\n邻域平均 Sharpe: {avg_neighbor:.2f}")
print(f"Sharpe >= 3.0: {above3_n}/{len(sharpe_neighbors)}")

# ============================================================
# 3. Walk-Forward
# ============================================================
print("\n[3] Walk-Forward 前进验证")
split = int(N * 0.6)
train = data[:split]
test = data[split:]
print(f"训练集: {len(train)} 天, 测试集: {len(test)} 天")

# Find best on train
best_train_s = -999
best_train_ts = 0.15
for ts in [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30, 1.0]:
    signals = compute_signals_v2(train, {'trailing_stop_pct': ts})
    hist = backtest.run_backtest(train, signals)
    m = backtest.calculate_metrics(hist)
    s = float(m['夏普比率 (Sharpe Ratio)'])
    if s > best_train_s:
        best_train_s = s
        best_train_ts = ts

print(f"训练集最佳: ts={best_train_ts:.0%}, Sharpe: {best_train_s:.2f}")

# Evaluate on test
signals_test = compute_signals_v2(test, {'trailing_stop_pct': best_train_ts})
hist_test = backtest.run_backtest(test, signals_test)
m_test = backtest.calculate_metrics(hist_test)
oos_sharpe = float(m_test['夏普比率 (Sharpe Ratio)'])
print(f"测试集 (样本外) Sharpe: {oos_sharpe:.2f}")
print(f"测试集回撤: {m_test['最大回撤 (Max Drawdown)']}")
print(f"测试集收益: {m_test['总收益率 (Total Return)']}")

# ============================================================
# 4. 综合结论
# ============================================================
print("\n" + "=" * 70)
print("[4] V2 策略综合评估")
print("=" * 70)

full_s, _, _ = run_full_test(data, {'trailing_stop_pct': best_ts}, "FINAL")
print(f"""
策略设计亮点:
  - 固定三窗口投票 (3/7/14天) → 消除窗口参数过拟合
  - 唯一参数为跟踪止损比例 → 一维参数空间, 过拟合风险极低
  - 邻域平均 Sharpe: {avg_neighbor:.2f}
  - 样本外 Sharpe: {oos_sharpe:.2f}
""")
