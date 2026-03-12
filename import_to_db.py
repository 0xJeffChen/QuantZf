import pandas as pd
from db_manager import DBManager
from datetime import datetime
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量


def import_stock_data_to_db(csv_file: str, ts_code: str):
    """
    将 CSV 文件中的股票历史数据导入数据库。
    
    :param csv_file: CSV 文件路径
    :param ts_code: 股票代码 (如 1810.HK)
    """
    if not os.path.exists(csv_file):
        print(f"Error: CSV file {csv_file} not found.")
        return

    # 读取 CSV 数据
    df = pd.read_csv(csv_file)
    
    # yfinance 导出的 CSV 通常包含 Date, Open, High, Low, Close, Volume, Dividends, Stock Splits
    # 我们需要根据数据库结构进行转换
    
    # 假设 CSV 的第一列是日期
    # 如果 CSV 有 header 且日期列名为 'Date'
    if 'Date' in df.columns:
        df['trade_date'] = pd.to_datetime(df['Date']).dt.date
    else:
        # 否则假设第一列是日期
        df['trade_date'] = pd.to_datetime(df.iloc[:, 0]).dt.date

    # 确保数据按日期升序排列
    df.sort_values('trade_date', inplace=True)

    # 计算与前一收盘价相比的涨跌额和涨跌幅
    df['prev_close'] = df['Close'].shift(1)
    df['change'] = df['Close'] - df['prev_close']
    df['pct_chg'] = df['change'] / df['prev_close']

    # 粗略估算成交额
    df['amount'] = df['Volume'] * df['Close']

    # 将 NaN 值替换为 None，以便数据库可以处理 (NaN -> NULL)
    # astype(object) 确保列可以容纳 None
    df = df.astype(object).where(pd.notnull(df), None)

    # 准备插入数据列表
    data_to_insert = []
    for _, row in df.iterrows():
        item = {
            "ts_code": ts_code,
            "trade_date": row['trade_date'],
            "open": row.get('Open'),
            "high": row.get('High'),
            "low": row.get('Low'),
            "close": row.get('Close'),
            "change": row.get('change'),
            "pct_chg": row.get('pct_chg'),
            "vol": row.get('Volume'),
            "amount": row.get('amount'), # 使用预先计算好的值
            "turnover_rate": 0.0 # 预留
        }
        data_to_insert.append(item)

    # 连接数据库并插入
    db = DBManager()
    try:
        count = db.insert_hk_stock_daily(data_to_insert)
        print(f"Successfully imported {count} records for {ts_code} into database.")
    except Exception as e:
        print(f"Failed to import data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    load_dotenv()
    # 导入小米集团数据
    import_stock_data_to_db("xiaomi_historical_data.csv", "1810.HK")
