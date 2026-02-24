import json, math, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)['raw_data']
n = len(data)

def run(smooth_w, short_w, long_w, ts_base):
    """Exact replica of app.js V3 logic"""
    min_lb = smooth_w + long_w + 3
    fee = 0.002
    cap0 = 100000

    log_rev = [math.log(d['revenue']) if d['revenue'] > 0 else 0 for d in data]
    smooth = [0.0] * n
    for i in range(smooth_w - 1, n):
        smooth[i] = sum(log_rev[i - smooth_w + 1:i + 1]) / smooth_w
    s_ma = [0.0] * n
    l_ma = [0.0] * n
    for i in range(short_w - 1, n):
        s_ma[i] = sum(smooth[i - short_w + 1:i + 1]) / short_w
    for i in range(long_w - 1, n):
        l_ma[i] = sum(smooth[i - long_w + 1:i + 1]) / long_w

    capital, position, peak_p = cap0, 0.0, 0.0
    in_pos, days_in, entry_p = False, 0, 0.0
    equities = []
    trades, wins = 0, 0

    for i in range(n):
        p = data[i]['price']
        if i < min_lb:
            equities.append(capital)
            continue

        rs, rl = s_ma[i - 1], l_ma[i - 1]
        vel = rs - s_ma[i - 2]
        vel_prev = s_ma[i - 2] - s_ma[i - 3]
        accel_ok = vel > vel_prev
        sig = 1 if (rs > rl and vel > 0 and accel_ok) else 0

        if in_pos:
            days_in += 1
            if p > peak_p: peak_p = p
            wp = max(0, (days_in - 7) / 7)
            ds = max(0.04, ts_base - wp * 0.015)
            dd = (peak_p - p) / peak_p if peak_p > 0 else 0
            if dd > ds or rs < rl:
                sig = 0

        if sig == 1 and not in_pos:
            in_pos, peak_p, entry_p, days_in = True, p, p, 0
            position = capital / (p * (1 + fee)); capital = 0
        elif sig == 0 and in_pos:
            in_pos = False
            capital = position * p * (1 - fee); position = 0
            trades += 1
            if p > entry_p: wins += 1

        equities.append(capital + position * p)

    total_ret = equities[-1] / equities[0] - 1
    days = len(equities)
    ann_ret = (1 + total_ret) ** (365 / days) - 1
    rets = [(equities[i] - equities[i-1]) / equities[i-1] if equities[i-1] > 0 else 0 for i in range(1, len(equities))]
    mean_r = sum(rets) / len(rets)
    vol = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / len(rets)) * math.sqrt(365)
    sharpe = ann_ret / vol if vol > 0 else 0
    peak, max_dd = 0, 0
    for e in equities:
        if e > peak: peak = e
        dd = (peak - e) / peak
        if dd > max_dd: max_dd = dd
    wr = f"{wins/trades*100:.0f}" if trades > 0 else "0"
    return sharpe, total_ret * 100, ann_ret * 100, max_dd * 100, trades, wr, vol * 100

print(f"{'Config':>45} | {'Sharpe':>7} | {'TotRet':>8} | {'AnnRet':>8} | {'MaxDD':>7} | {'#T':>3} | {'WR':>4} | {'Vol':>6}")
print("-" * 110)

# Test ALL promising configs at multiple stop levels to verify robustness
for sw in [3, 5, 7]:
    for shw in [3, 5, 7]:
        for lw in [14, 21, 28]:
            for ts in [0.08, 0.10, 0.12, 0.15, 0.20, 0.25]:
                s, tr, ar, md, t, wr, vol = run(sw, shw, lw, ts)
                if s >= 3.0:
                    label = f"sm={sw} sh={shw} lg={lw} ts={ts*100:.0f}%"
                    print(f"{label:>45} | {s:7.2f} | {tr:7.1f}% | {ar:7.1f}% | {md:6.1f}% | {t:3d} |  {wr}% | {vol:5.1f}%")
print("\n=== All configs with Sharpe >= 3.0 shown ===")
