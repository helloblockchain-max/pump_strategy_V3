import sys
sys.path.append(r'd:\AI')
import backtest
sys.stdout.reconfigure(encoding='utf-8')

# Load data
data = backtest.load_csv_data(r'd:\AI\pump_data.csv')

best_sharpe = -999
best_params = {}

print("Deep searching for Sharpe > 3 ...")
for w in range(2, 25):
    for sma in range(3, 30):
        params = {'window': w, 'sma_window': sma}
        signals = backtest.compute_signals(data, params)
        hist = backtest.run_backtest(data, signals)
        metrics = backtest.calculate_metrics(hist)
        
        try:
            sharpe = float(metrics['夏普比率 (Sharpe Ratio)'])
        except:
            sharpe = 0
            
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_params = params
            
        if sharpe >= 3.0:
            print(f"FOUND: Window={w}, SMA={sma} -> Sharpe: {sharpe}, DD: {metrics['最大回撤 (Max Drawdown)']}")

print(f"BEST FOUND: {best_params} -> Sharpe {best_sharpe}")
