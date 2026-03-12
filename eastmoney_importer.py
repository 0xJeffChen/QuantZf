import akshare as ak
import pandas as pd
from db_manager import DBManager
from dotenv import load_dotenv

def sync_hk_stock_hist(
    symbol: str,
    start_date: str = "19700101",
    end_date: str = "22220101",
    adjust: str = "qfq",
):
    """
    从东方财富获取港股历史行情数据，并存入数据库。

    :param symbol: 港股代码, e.g., "00700"
    :param start_date: 开始日期, e.g., "20230101"
    :param end_date: 结束日期, e.g., "20231231"
    :param adjust: 复权类型, "qfq" (前复权), "hfq" (后复权), "" (不复权)
    """
    try:
        print(f"Fetching data for {symbol} from {start_date} to {end_date}...")
        # 1. 获取数据
        stock_hk_hist_df = ak.stock_hk_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )

        if stock_hk_hist_df.empty:
            print(f"No data found for {symbol}.")
            return

        print(f"Successfully fetched {len(stock_hk_hist_df)} records.")

        # 2. 数据转换
        # 添加 ts_code
        stock_hk_hist_df["ts_code"] = f"{symbol}.HK"

        # 重命名列以匹配数据库表结构
        rename_map = {
            "日期": "trade_date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "vol",
            "成交额": "amount",
            "涨跌额": "change",
            "涨跌幅": "pct_chg",
            "换手率": "turnover_rate",
        }
        stock_hk_hist_df.rename(columns=rename_map, inplace=True)

        # 转换百分比为小数
        stock_hk_hist_df["pct_chg"] = stock_hk_hist_df["pct_chg"] / 100
        stock_hk_hist_df["turnover_rate"] = stock_hk_hist_df["turnover_rate"] / 100

        # 确保日期格式正确
        stock_hk_hist_df["trade_date"] = pd.to_datetime(
            stock_hk_hist_df["trade_date"]
        ).dt.date

        # 选取需要的列
        columns_to_keep = [
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "change",
            "pct_chg",
            "vol",
            "amount",
            "turnover_rate",
        ]
        stock_hk_hist_df = stock_hk_hist_df[columns_to_keep]

        # 将 NaN 替换为 None
        stock_hk_hist_df = stock_hk_hist_df.astype(object).where(
            pd.notnull(stock_hk_hist_df), None
        )

        # 3. 数据入库
        data_to_insert = stock_hk_hist_df.to_dict("records")

        db = DBManager()
        try:
            print("Inserting data into database...")
            count = db.insert_hk_stock_daily(data_to_insert)
            print(f"Successfully inserted/updated {count} records for {symbol}.")
        except Exception as e:
            print(f"Database operation failed: {e}")
        finally:
            db.close()

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    # 加载环境变量
    load_dotenv()

    # --- 示例：同步腾讯控股 (00700) 2023年的历史数据 ---
    sync_hk_stock_hist(symbol="00700", start_date="20180101", end_date="20260311")

    # --- 示例：同步小米集团 (01810) 的全部历史数据 ---
    # sync_hk_stock_hist(symbol="01810")
