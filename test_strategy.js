// Quick Node.js backtest verification script
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync('./data.json', 'utf8'));
const data = payload.raw_data;
const n = data.length;

function runTest(trailingStopBase) {
    const smoothW = 3, shortW = 5, longW = 21;
    const minLookback = smoothW + longW + 1;
    const feeRate = 0.002;
    const initialCapital = 100000;
    const bhPos = initialCapital / (data[0].price * (1 + feeRate));

    // Log-smooth
    const logRev = data.map(d => d.revenue > 0 ? Math.log(d.revenue) : 0);
    const smooth = new Array(n).fill(0);
    for (let i = smoothW - 1; i < n; i++) {
        let s = 0;
        for (let j = i - smoothW + 1; j <= i; j++) s += logRev[j];
        smooth[i] = s / smoothW;
    }
    const sMA = new Array(n).fill(0), lMA = new Array(n).fill(0);
    for (let i = shortW - 1; i < n; i++) {
        let s = 0;
        for (let j = i - shortW + 1; j <= i; j++) s += smooth[j];
        sMA[i] = s / shortW;
    }
    for (let i = longW - 1; i < n; i++) {
        let s = 0;
        for (let j = i - longW + 1; j <= i; j++) s += smooth[j];
        lMA[i] = s / longW;
    }

    let capital = initialCapital, position = 0, peakPrice = 0;
    let inPos = false, daysIn = 0;
    const equities = [];
    let trades = 0, wins = 0, entryPrice = 0;

    for (let i = 0; i < n; i++) {
        const p = data[i].price;
        if (i < minLookback) { equities.push(capital); continue; }

        const rS = sMA[i - 1], rL = lMA[i - 1];
        const rSPrev = sMA[i - 2];
        const vel = rS - rSPrev;
        let sig = (rS > rL && vel > 0) ? 1 : 0;

        if (inPos) {
            daysIn++;
            if (p > peakPrice) peakPrice = p;
            const wp = Math.max(0, (daysIn - 14) / 7);
            const ds = Math.max(0.04, trailingStopBase - wp * 0.01);
            const dd = peakPrice > 0 ? (peakPrice - p) / peakPrice : 0;
            if (dd > ds || rS < rL) sig = 0;
        }

        if (sig === 1 && !inPos) {
            inPos = true; peakPrice = p; entryPrice = p; daysIn = 0;
            position = capital / (p * (1 + feeRate)); capital = 0;
        } else if (sig === 0 && inPos) {
            inPos = false;
            capital = position * p * (1 - feeRate); position = 0;
            trades++;
            if (p > entryPrice) wins++;
        }
        equities.push(capital + position * p);
    }

    const totalRet = equities[equities.length - 1] / equities[0] - 1;
    const days = equities.length;
    const annRet = Math.pow(1 + totalRet, 365 / days) - 1;
    const rets = [];
    for (let i = 1; i < equities.length; i++) {
        rets.push(equities[i - 1] > 0 ? (equities[i] - equities[i - 1]) / equities[i - 1] : 0);
    }
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
    const vol = Math.sqrt(rets.reduce((a, r) => a + (r - mean) ** 2, 0) / rets.length) * Math.sqrt(365);
    const sharpe = vol > 0 ? annRet / vol : 0;
    let peak = 0, maxDD = 0;
    for (const e of equities) { if (e > peak) peak = e; const dd = (peak - e) / peak; if (dd > maxDD) maxDD = dd; }
    const wr = trades > 0 ? (wins / trades * 100).toFixed(1) : '0';

    return { sharpe: sharpe.toFixed(2), totalRet: (totalRet * 100).toFixed(1), annRet: (annRet * 100).toFixed(1), maxDD: (maxDD * 100).toFixed(1), trades, winRate: wr, vol: (vol * 100).toFixed(1) };
}

console.log('=== V3 Strategy Backtest Results ===');
console.log(`Data: ${n} days, ${data[0].date} ~ ${data[n - 1].date}`);
console.log('');

// Test various stop levels
for (const ts of [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25]) {
    const r = runTest(ts);
    const marker = parseFloat(r.sharpe) >= 3.0 ? ' ★★★' : '';
    console.log(`Stop=${(ts * 100).toFixed(0)}% | Sharpe=${r.sharpe} | Return=${r.totalRet}% | AnnRet=${r.annRet}% | MaxDD=${r.maxDD}% | Trades=${r.trades} | WinRate=${r.winRate}%${marker}`);
}
