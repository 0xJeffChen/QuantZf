import pandas as pd
import numpy as np
import logging
import matplotlib.pyplot as plt
from db_manager import DBManager
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("backtester.log"),
        logging.StreamHandler(),
    ],
)

# 解决中文显示问题 (macOS 常用字体)
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

class VectorizedBacktester:
    """
    向量化回测框架，用于双均线策略。
    """

    def __init__(self, ts_code, start_date, end_date, short_window=5, long_window=20, vol_window=5, initial_cash=100000, trailing_stop=0.10, rsi_limit=80, adx_limit=25):
        self.ts_code = ts_code
        self.start_date = start_date
        self.end_date = end_date
        self.short_window = short_window
        self.long_window = long_window
        self.vol_window = vol_window
        self.initial_cash = initial_cash
        self.trailing_stop = trailing_stop # 移动止损阈值 (如 0.1 代表从高点回落 10%)
        self.rsi_limit = rsi_limit # RSI 超买过滤
        self.adx_limit = adx_limit # ADX 趋势强度过滤 (通常 > 25 表示有趋势)
        self.data = None
        self.results = None
        self.trades = [] # 记录每一笔交易的具体信息

    def _get_data(self):
        """从数据库获取并准备数据。"""
        logging.info("Fetching data for backtest...")
        db = DBManager()
        try:
            data = db.get_daily_with_indicators(self.ts_code, self.start_date, self.end_date)
            if not data:
                raise ValueError("No data found for the given stock and date range.")
            
            df = pd.DataFrame(data)
            df.set_index("trade_date", inplace=True)
            df.sort_index(inplace=True)

            # 统一数据类型为 float
            cols_to_float = ['open', 'high', 'low', 'close', 'vol', 'ma5', 'ma10', 'ma20', 'ma60', 'rsi6', 'rsi12', 'rsi24', 'adx']
            for col in cols_to_float:
                if col in df.columns:
                    df[col] = df[col].astype(float)
            
            # 确保均线列存在
            self.short_ma_col = f'ma{self.short_window}'
            self.long_ma_col = f'ma{self.long_window}'
            if self.short_ma_col not in df.columns or self.long_ma_col not in df.columns:
                raise ValueError(f"Required MA columns ({self.short_ma_col}, {self.long_ma_col}) not found in data.")

            self.data = df
            logging.info("Data preparation complete.")
        finally:
            db.close()

    def _generate_signals(self):
        """生成交易信号。"""
        logging.info("Generating trading signals...")
        df = self.data.copy()
        
        # 1. 均线交叉信号 (修正后的安全写法)
        # 使用比较运算直接生成布尔值，再转换为整数 (1 或 0)
        df["signal"] = (df[self.short_ma_col] > df[self.long_ma_col]).astype(int)
        
        # 动态判定：如果任一均线数据缺失（NaN），则信号无效，置为 0
        # 这样处理比硬编码窗口大小更健壮，能自动适应不同的预热期或数据缺失
        invalid_ma_mask = df[self.short_ma_col].isna() | df[self.long_ma_col].isna()
        df.loc[invalid_ma_mask, "signal"] = 0
        
        # 计算信号的变化：1代表金叉(0->1)，-1代表死叉(1->0)
        df["position"] = df["signal"].diff()
        
        # 额外处理：如果前一天的数据缺失，则当天的 diff 信号无效（避免数据开始时的假信号）
        prev_invalid_mask = df[self.short_ma_col].shift(1).isna() | df[self.long_ma_col].shift(1).isna()
        df.loc[prev_invalid_mask, "position"] = 0

        # 2. 成交量放大信号
        df["vol_mean"] = df["vol"].rolling(window=self.vol_window).mean()
        df["vol_signal"] = np.where(df["vol"] > df["vol_mean"], 1, 0)

        # 3. 结合信号 (放宽条件)
        # 增加 RSI 过滤：如果 RSI12 > 80，则认为是超买，不建议买入
        df["rsi_filter"] = np.where(df["rsi12"] < self.rsi_limit, 1, 0)
        
        # 如果当天或前一天有过成交量放大，则认为成交量信号有效
        df["recent_vol_spike"] = df["vol_signal"].rolling(2).max()

        # ADX 趋势过滤：只有当 ADX > adx_limit 时才认为趋势强，允许交易
        # 如果数据中没有 ADX 列，则默认通过过滤
        if "adx" in df.columns:
            df["trend_filter"] = np.where(df["adx"] > self.adx_limit, 1, 0)
        else:
            df["trend_filter"] = 1
        
        # 只有在成交量放大且不处于超买状态时，金叉才有效
        df["final_position"] = np.where(
            (df["recent_vol_spike"] == 1) & (df["rsi_filter"] == 1) & (df["trend_filter"] == 1), 
            df["position"], 
            np.where(df["position"] == -1, -1, 0) # 卖出信号不受成交量和RSI限制
        )

        df.to_csv("df.csv")

        # --- 调试日志 ---
        crossover_days = df[df["position"] != 0]
        if not crossover_days.empty:
            logging.info("Crossover events detected. Checking volume signals on these days:")
            logging.info(crossover_days[["position", "vol", "vol_mean", "vol_signal", "recent_vol_spike"]])

        trade_signals = df[df["final_position"] != 0]
        if trade_signals.empty:
            logging.warning("No valid trade signals were generated in the entire period.")
        else:
            logging.info(f"Generated trade signals on following dates:\n{trade_signals['final_position']}")
        
        self.data = df
        logging.info("Signal generation complete.")

    def _run_backtest(self):
        """执行回测模拟。"""
        logging.info("Running backtest simulation...")
        df = self.data.copy()
        # 显式初始化为浮点型，避免 Pandas 自动推断为 int64 导致赋值错误
        df["cash"] = float(self.initial_cash)
        df["shares"] = 0.0
        df["portfolio_value"] = float(self.initial_cash)
        df["trade_type"] = "" # 用于绘图标记

        last_high = 0.0 # 记录持仓期间的最高价

        for i in range(1, len(df)):
            current_date = df.index[i]
            # 继承前一天的状态
            df.loc[current_date, "cash"] = df.loc[df.index[i-1], "cash"]
            df.loc[current_date, "shares"] = df.loc[df.index[i-1], "shares"]
            
            close_price = df.loc[current_date, "close"]
            current_shares = df.loc[current_date, "shares"]
            
            # 如果有持仓，更新最高价
            if current_shares > 0:
                last_high = max(last_high, close_price)
                
                # 检查移动止损
                if close_price < last_high * (1 - self.trailing_stop):
                    cash_from_sale = current_shares * close_price
                    df.loc[current_date, "shares"] = 0
                    df.loc[current_date, "cash"] = cash_from_sale
                    df.loc[current_date, "trade_type"] = "trailing_stop_sell"
                    logging.info(f"{current_date}: TRAILING STOP SELL at {close_price} (High: {last_high})")
                    last_high = 0.0
                    current_shares = 0.0 # 更新状态以便后续逻辑判断

            # 执行交易信号 (均线信号)
            if df.loc[current_date, "final_position"] == 1: # 买入信号
                if current_shares == 0: # 确保是空仓状态
                    shares_to_buy = df.loc[current_date, "cash"] / close_price
                    df.loc[current_date, "shares"] = shares_to_buy
                    df.loc[current_date, "cash"] = 0
                    df.loc[current_date, "trade_type"] = "buy"
                    last_high = close_price
                    logging.info(f"{current_date}: BUY {shares_to_buy:.2f} shares at {close_price}")
            elif df.loc[current_date, "final_position"] == -1: # 卖出信号
                if current_shares > 0: # 确保是持仓状态
                    cash_from_sale = current_shares * close_price
                    df.loc[current_date, "shares"] = 0
                    df.loc[current_date, "cash"] = cash_from_sale
                    df.loc[current_date, "trade_type"] = "signal_sell"
                    logging.info(f"{current_date}: SIGNAL SELL shares at {close_price}")
                    last_high = 0.0
            
            # 更新每日投资组合价值
            df.loc[current_date, "portfolio_value"] = (
                df.loc[current_date, "cash"] + df.loc[current_date, "shares"] * close_price
            )

        self.results = df
        logging.info("Backtest simulation complete.")

    def _calculate_metrics(self):
        """计算回测性能指标。"""
        logging.info("Calculating performance metrics...")
        res = self.results
        
        # 1. 累计收益率
        total_return = (res["portfolio_value"].iloc[-1] / self.initial_cash - 1) * 100
        
        # 2. 年化收益率
        days = (res.index[-1] - res.index[0]).days
        annual_return = ((1 + total_return / 100) ** (365.0 / days) - 1) * 100 if days > 0 else 0

        # 3. 最大回撤
        res["peak"] = res["portfolio_value"].cummax()
        res["drawdown"] = (res["portfolio_value"] - res["peak"]) / res["peak"]
        max_drawdown = res["drawdown"].min() * 100

        # 4. 夏普比率 (假设无风险利率为0)
        res["daily_return"] = res["portfolio_value"].pct_change()
        sharpe_ratio = (res["daily_return"].mean() / res["daily_return"].std()) * np.sqrt(252) if res["daily_return"].std() != 0 else 0

        # 5. 基准收益率 (买入并持有)
        benchmark_return = (res["close"].iloc[-1] / res["close"].iloc[0] - 1) * 100

        print("\n--- Backtest Results ---")
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Initial Portfolio Value: {self.initial_cash:,.2f}")
        print(f"Final Portfolio Value:   {res['portfolio_value'].iloc[-1]:,.2f}")
        print("-" * 24)
        print(f"Total Return:            {total_return:.2f}%")
        print(f"Benchmark Return:        {benchmark_return:.2f}% (Buy and Hold)")
        print(f"Annualized Return:       {annual_return:.2f}%")
        print(f"Max Drawdown:            {max_drawdown:.2f}%")
        print(f"Sharpe Ratio:            {sharpe_ratio:.2f}")
        print("------------------------\n")

    def plot_results(self):
        """绘制回测结果走势图。"""
        logging.info("Generating plots...")
        res = self.results
        
        # 创建两个子图：上方是价格和信号，下方是净值曲线
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
        
        # 1. 绘制价格和均线
        ax1.plot(res.index, res["close"], label="收盘价", color="black", alpha=0.6)
        ax1.plot(res.index, res[self.short_ma_col], label=f"{self.short_window}日均线", alpha=0.8)
        ax1.plot(res.index, res[self.long_ma_col], label=f"{self.long_window}日均线", alpha=0.8)
        
        # 2. 标记买入点
        buys = res[res["trade_type"] == "buy"]
        ax1.scatter(buys.index, buys["close"], marker="^", color="red", s=100, label="买入信号", zorder=5)
        
        # 3. 标记卖出点 (区分均线卖出和止损卖出)
        sig_sells = res[res["trade_type"] == "signal_sell"]
        ax1.scatter(sig_sells.index, sig_sells["close"], marker="v", color="green", s=100, label="均线卖出", zorder=5)
        
        ts_sells = res[res["trade_type"] == "trailing_stop_sell"]
        ax1.scatter(ts_sells.index, ts_sells["close"], marker="x", color="darkorange", s=100, label="移动止损", zorder=5)
        
        ax1.set_title(f"回测走势图: {self.ts_code} ({self.start_date} ~ {self.end_date})")
        ax1.set_ylabel("价格 (港元)")
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 4. 绘制净值曲线
        ax2.plot(res.index, res["portfolio_value"], label="策略净值", color="blue")
        # 绘制基准净值 (假设全仓买入并持有)
        benchmark_nav = (res["close"] / res["close"].iloc[0]) * self.initial_cash
        ax2.plot(res.index, benchmark_nav, label="基准净值 (买入持有)", color="gray", linestyle="--", alpha=0.6)
        
        ax2.set_ylabel("账户总资产")
        ax2.set_xlabel("日期")
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 保存图片
        plot_path = "backtest_result.png"
        plt.savefig(plot_path)
        logging.info(f"Plot saved to {plot_path}")
        print(f"\n[可视化] 走势图已保存至: {plot_path}")

    def run(self):
        """运行整个回测流程。"""
        self._get_data()
        self._generate_signals()
        self._run_backtest()
        self._calculate_metrics()
        self.plot_results()


if __name__ == "__main__":
    load_dotenv()
    # --- 回测示例：对小米集团(01810.HK)在2023年的数据进行回测 ---
    # 策略参数：5日均线/20日均线，成交量窗口为5日
    backtester = VectorizedBacktester(
        ts_code="01810.HK",
        start_date="2024-12-13",
        end_date="2026-3-11",
        short_window=5,
        long_window=10,
        vol_window=2,
        initial_cash=100000,
        trailing_stop= 0.15,
        rsi_limit= 85,
        adx_limit= 25
    )

    # backtester = VectorizedBacktester(
    #     ts_code="00700.HK",
    #     start_date="2024-12-13",
    #     end_date="2026-3-11",
    #     short_window=5,
    #     long_window=10,
    #     vol_window=2,
    #     initial_cash=100000,
    #     trailing_stop= 0.10,
    #     rsi_limit= 85,
    #     adx_limit= 25
    # )
    backtester.run()
