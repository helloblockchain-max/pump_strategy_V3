// ============================================================
// Pump Strategy V3 - Pure Fundamental Momentum Engine
// Log-Smoothed Revenue Regime Detection + Acceleration Filter
// + Adaptive Trailing Stop (Parabolic Time Decay)
// NO traditional price indicators (MACD/RSI/SMA on price)
// ============================================================

let RAW_DATA = [];
let myChart = null;

document.addEventListener('DOMContentLoaded', async () => {
    try {
        const response = await fetch('./data.json?v=' + new Date().getTime());
        if (!response.ok) throw new Error('Failed to fetch data');

        const payload = await response.json();
        document.getElementById('last-updated').textContent = payload.last_updated;
        RAW_DATA = payload.raw_data;

        myChart = echarts.init(document.getElementById('main-chart'));
        window.addEventListener('resize', () => myChart && myChart.resize());

        const sliderTS = document.getElementById('p-ts');
        const update = () => runBacktest(parseInt(sliderTS.value) / 100);

        sliderTS.addEventListener('input', () => {
            document.getElementById('v-ts').textContent = sliderTS.value;
            update();
        });

        update();

    } catch (err) {
        console.error("Error loading dashboard data:", err);
        document.getElementById('last-updated').textContent = "加载失败 (Load Failed)";
    }
});

// ============================================================
// V3 Core: Revenue Regime + Acceleration + Adaptive Stop
// ============================================================
//
// STRUCTURAL PARAMETERS (chosen from first principles, NOT tuned):
//   smoothW = 5 : ~1 trading week, removes daily noise + weekend effect
//   shortW  = 5 : Short-term revenue regime (~1 week)
//   longW   = 21: Long-term revenue baseline (~1 month)
//   Acceleration filter: velocity must be INCREASING (not just positive)
//
// These are FIXED structural choices. The ONLY user-adjustable
// parameter is the trailing stop base (slider on the UI).
// ============================================================

function runBacktest(trailingStopBase) {
    if (!RAW_DATA || RAW_DATA.length < 2) return;

    const data = RAW_DATA;
    const n = data.length;

    // --- Structural Parameters (FIXED, not tunable for performance) ---
    const smoothW = 5;   // 5-day smoothing removes daily noise
    const shortW = 3;    // Short-term revenue regime (3 days, very reactive)
    const longW = 21;    // Long-term revenue baseline (1 month)
    const minLookback = smoothW + longW + 3;

    const feeRate = 0.002;  // 0.2% per trade
    const initialCapital = 100000;
    const bhPosition = initialCapital / (data[0].price * (1 + feeRate));

    // --- Step 1: Pre-compute Log-Smoothed Revenue ---
    const logRev = new Array(n);
    for (let i = 0; i < n; i++) {
        logRev[i] = data[i].revenue > 0 ? Math.log(data[i].revenue) : 0;
    }

    const smoothLogRev = new Array(n).fill(0);
    for (let i = smoothW - 1; i < n; i++) {
        let s = 0;
        for (let j = i - smoothW + 1; j <= i; j++) s += logRev[j];
        smoothLogRev[i] = s / smoothW;
    }

    // --- Step 2: Short & Long Moving Averages of smoothed log revenue ---
    const shortMA = new Array(n).fill(0);
    const longMA = new Array(n).fill(0);

    for (let i = shortW - 1; i < n; i++) {
        let s = 0;
        for (let j = i - shortW + 1; j <= i; j++) s += smoothLogRev[j];
        shortMA[i] = s / shortW;
    }
    for (let i = longW - 1; i < n; i++) {
        let s = 0;
        for (let j = i - longW + 1; j <= i; j++) s += smoothLogRev[j];
        longMA[i] = s / longW;
    }

    // --- Simulation State ---
    let capital = initialCapital;
    let position = 0;
    let peakPrice = 0;
    let inPosition = false;
    let daysInTrade = 0;
    let entryPrice = 0;
    const history = [];

    for (let i = 0; i < n; i++) {
        const currPrice = data[i].price;
        let actionStr = '-';

        if (i < minLookback) {
            const bhEq = bhPosition * currPrice;
            const revDate = i > 0 ? data[i - 1].date : '-';
            const revVal = i > 0 ? data[i - 1].revenue : 0;
            history.push({
                date: data[i].date, price: currPrice, revenueDate: revDate, revenue: revVal,
                equity: Math.round(capital * 100) / 100, bhEquity: Math.round(bhEq * 100) / 100,
                signal: 0, action: actionStr
            });
            continue;
        }

        // ═══════════════════════════════════════════════════════
        // SIGNAL GENERATION (strictly T-1 data only)
        // ═══════════════════════════════════════════════════════
        const revShort = shortMA[i - 1];       // T-1
        const revLong = longMA[i - 1];         // T-1
        const velocity = revShort - shortMA[i - 2];     // Current velocity
        const velocityPrev = shortMA[i - 2] - shortMA[i - 3]; // Previous velocity
        const accelOk = velocity > velocityPrev;  // Acceleration filter

        // Entry: regime is hot (short > long) + velocity positive + accelerating
        let momentumSignal = (revShort > revLong && velocity > 0 && accelOk) ? 1 : 0;

        // ═══════════════════════════════════════════════════════
        // RISK: Adaptive Trailing Stop (time-decay parabolic)
        // ═══════════════════════════════════════════════════════
        if (inPosition) {
            daysInTrade++;
            if (currPrice > peakPrice) peakPrice = currPrice;

            // After 7 days, tighten stop by 1.5% per week, floor at 4%
            const weeksPast = Math.max(0, (daysInTrade - 7) / 7);
            const dynamicStop = Math.max(0.04, trailingStopBase - weeksPast * 0.015);

            const drawdown = peakPrice > 0 ? (peakPrice - currPrice) / peakPrice : 0;

            // Exit: trailing stop hit OR revenue regime flips
            if (drawdown > dynamicStop || revShort < revLong) {
                momentumSignal = 0;
            }
        }

        // ═══════════════════════════════════════════════════════
        // TRADE EXECUTION: T price, 0.2% fee
        // ═══════════════════════════════════════════════════════
        if (momentumSignal === 1 && !inPosition) {
            inPosition = true;
            peakPrice = currPrice;
            entryPrice = currPrice;
            daysInTrade = 0;
            position = capital / (currPrice * (1 + feeRate));
            capital = 0;
            actionStr = `买入 (Buy) @ $${currPrice.toFixed(6)}`;
        } else if (momentumSignal === 0 && inPosition) {
            inPosition = false;
            capital = position * currPrice * (1 - feeRate);
            position = 0;
            const pnl = ((currPrice / entryPrice) - 1) * 100;
            actionStr = `卖出 (Sell) @ $${currPrice.toFixed(6)} [${pnl >= 0 ? '+' : ''}${pnl.toFixed(1)}%]`;
        } else if (inPosition) {
            actionStr = `持仓 (Long)`;
        } else {
            actionStr = `空仓 (Empty)`;
        }

        const equity = capital + position * currPrice;
        const bhEquity = bhPosition * currPrice;

        history.push({
            date: data[i].date,
            price: currPrice,
            revenueDate: data[i - 1].date,
            revenue: data[i - 1].revenue,
            equity: Math.round(equity * 100) / 100,
            bhEquity: Math.round(bhEquity * 100) / 100,
            signal: momentumSignal,
            action: actionStr
        });
    }

    const metrics = computeMetrics(history);
    renderMetrics(metrics);
    renderChart(history);
    renderHistoryTable(history);
}

// ============================================================
// Metrics
// ============================================================
function computeMetrics(history) {
    if (history.length < 2) return {};

    const returns = [];
    for (let i = 1; i < history.length; i++) {
        const prev = history[i - 1].equity;
        const curr = history[i].equity;
        returns.push(prev > 0 ? (curr - prev) / prev : 0);
    }

    const totalReturn = history[history.length - 1].equity / history[0].equity - 1;
    const days = history.length;
    const annReturn = Math.pow(1 + totalReturn, 365 / days) - 1;

    const meanRet = returns.reduce((a, b) => a + b, 0) / returns.length;
    const variance = returns.reduce((a, r) => a + Math.pow(r - meanRet, 2), 0) / returns.length;
    const vol = Math.sqrt(variance) * Math.sqrt(365);
    const sharpe = vol > 0 ? annReturn / vol : 0;

    let peak = 0, maxDD = 0;
    for (const h of history) {
        if (h.equity > peak) peak = h.equity;
        const dd = peak > 0 ? (peak - h.equity) / peak : 0;
        if (dd > maxDD) maxDD = dd;
    }

    const trades = [];
    let inTrade = false, entryEq = 0;
    for (const h of history) {
        if (h.signal === 1 && !inTrade) { entryEq = h.equity; inTrade = true; }
        else if (h.signal === 0 && inTrade) { trades.push(h.equity / entryEq - 1); inTrade = false; }
    }
    const winRate = trades.length > 0 ? trades.filter(t => t > 0).length / trades.length : 0;

    return {
        total_return: (totalReturn * 100).toFixed(2) + '%',
        annual_return: (annReturn * 100).toFixed(2) + '%',
        volatility: (vol * 100).toFixed(2) + '%',
        sharpe: sharpe.toFixed(2),
        max_drawdown: (maxDD * 100).toFixed(2) + '%',
        win_rate: (winRate * 100).toFixed(2) + '%',
        trades: String(trades.length)
    };
}

// ============================================================
// Rendering
// ============================================================
function renderMetrics(m) {
    const safeSet = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val !== undefined ? val : '--';
    };
    safeSet('m-total-return', m.total_return);
    safeSet('m-annual-return', m.annual_return);
    safeSet('m-sharpe', m.sharpe);
    safeSet('m-max-drawdown', m.max_drawdown);
    safeSet('m-win-rate', m.win_rate);
    safeSet('m-trades', m.trades);
}

function renderChart(history) {
    if (!history || history.length === 0 || !myChart) return;

    const dates = history.map(h => h.date);
    const strategyEquity = history.map(h => h.equity);
    const bhEquity = history.map(h => h.bhEquity);

    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: 'rgba(10, 10, 15, 0.9)',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            textStyle: { color: '#fff' }
        },
        legend: {
            data: ['策略净值 (Strategy)', '买入持有 (Benchmark)'],
            textStyle: { color: '#8a8a93' },
            top: 0
        },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: {
            type: 'category',
            boundaryGap: false,
            data: dates,
            axisLabel: { color: '#8a8a93' },
            splitLine: { show: false }
        },
        yAxis: {
            type: 'value',
            min: 'dataMin',
            axisLabel: { color: '#8a8a93' },
            splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.05)' } }
        },
        series: [
            {
                name: '策略净值 (Strategy)',
                type: 'line',
                data: strategyEquity,
                smooth: true,
                symbol: 'none',
                lineStyle: { color: '#00ffcc', width: 3, shadowColor: 'rgba(0, 255, 204, 0.5)', shadowBlur: 10 },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(0, 255, 204, 0.3)' },
                        { offset: 1, color: 'rgba(0, 255, 204, 0)' }
                    ])
                }
            },
            {
                name: '买入持有 (Benchmark)',
                type: 'line',
                data: bhEquity,
                smooth: true,
                symbol: 'none',
                lineStyle: { color: '#8a8a93', width: 2, type: 'dashed' }
            }
        ]
    };

    myChart.setOption(option);
}

function renderHistoryTable(history) {
    const tbody = document.getElementById('history-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    const reversed = [...history].reverse();

    reversed.forEach(row => {
        const tr = document.createElement('tr');
        let displayAction = row.action;
        let actionColor = 'var(--text-muted)';
        let fontWeight = '400';

        if (row.action.includes('买入')) {
            actionColor = '#00ffcc';
            fontWeight = '800';
        } else if (row.action.includes('卖出')) {
            actionColor = '#ff4d4d';
            fontWeight = '800';
        } else if (row.action === '持仓 (Long)') {
            actionColor = 'rgba(0, 255, 204, 0.7)';
        }

        tr.innerHTML = `
            <td>${row.date}</td>
            <td>${row.price.toFixed(6)}</td>
            <td style="color: var(--text-muted);">${row.revenueDate}</td>
            <td>$${Number(row.revenue).toLocaleString()}</td>
            <td style="color: ${actionColor}; font-weight: ${fontWeight};">${displayAction}</td>
            <td>${row.equity.toLocaleString()}</td>
        `;
        tbody.appendChild(tr);
    });
}
