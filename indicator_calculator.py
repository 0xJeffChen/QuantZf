import pandas as pd
import pandas_ta as ta
import logging
from typing import List, Optional
from db_manager import DBManager
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("indicator_calculator.log"),
        logging.StreamHandler(),
    ],
)

def calculate_indicators(
    df: pd.DataFrame, indicator_types: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    根据输入的K线DataFrame计算技术指标 (纯计算函数)。

    :param df: 包含 open, high, low, close, vol 的DataFrame
    :param indicator_types: 要计算的指标类型列表, 默认全部
    :return: 包含计算后指标的DataFrame
    """
    logging.info("Starting indicator calculation...")
    # 确保我们操作的是一个副本
    df_calculated = df.copy()

    # 确保数据类型正确
    df_calculated = df_calculated.astype({
        "open": "float",
        "high": "float",
        "low": "float",
        "close": "float",
        "vol": "float",
    })

    # 确定要计算的指标
    indicators_to_calculate = (
        indicator_types if indicator_types else ["ma", "macd", "kdj", "rsi", "bbands", "adx", "atr"]
    )
    logging.info(f"Calculating indicators: {indicators_to_calculate}")

    # --- 最直接、最稳健的原地计算方法 ---
    if "ma" in indicators_to_calculate:
        df_calculated.ta.sma(length=5, append=True)
        df_calculated.ta.sma(length=10, append=True)
        df_calculated.ta.sma(length=20, append=True)
        df_calculated.ta.sma(length=60, append=True)

    if "macd" in indicators_to_calculate:
        df_calculated.ta.macd(append=True)

    if "kdj" in indicators_to_calculate:
        df_calculated.ta.kdj(append=True)

    if "rsi" in indicators_to_calculate:
        df_calculated.ta.rsi(length=6, append=True)
        df_calculated.ta.rsi(length=12, append=True)
        df_calculated.ta.rsi(length=24, append=True)

    if "bbands" in indicators_to_calculate:
        df_calculated.ta.bbands(length=20, append=True)
        
    if "adx" in indicators_to_calculate:
        df_calculated.ta.adx(length=14, append=True)

    if "atr" in indicators_to_calculate:
        df_calculated.ta.atr(length=14, append=True)

    logging.info("Indicator calculation finished.")
    return df_calculated

def process_and_store_indicators(
    ts_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    indicator_types: Optional[List[str]] = None,
):
    """
    获取数据、计算指标并存入数据库 (业务流程编排)。
    """
    db = DBManager()
    try:
        # 1. 从数据库获取K线数据
        logging.info(f"Fetching daily k-line data for {ts_code}...")
        daily_data = db.get_hk_stock_daily(
            ts_code=ts_code, start_date=start_date, end_date=end_date
        )

        if not daily_data:
            logging.warning(f"No daily data found for {ts_code}. Skipping processing.")
            return

        df_kline = pd.DataFrame(daily_data)
        df_kline.set_index("trade_date", inplace=True)

        # 2. 计算技术指标 (调用纯计算函数)
        df_with_indicators = calculate_indicators(df_kline, indicator_types)

        # 3. 数据整理与入库
        logging.info(f"Preparing data for database insertion for {ts_code}...")

        # 关键调试日志：打印转换前的原始列名
        logging.info(f"Original columns from pandas-ta: {df_with_indicators.columns.tolist()}")

        # 标准化列名为小写，以处理潜在的大小写不一致问题
        df_with_indicators.columns = [col.lower() for col in df_with_indicators.columns]
        logging.info(f"Standardized columns to lowercase: {df_with_indicators.columns.tolist()}")

        # 重命名列以匹配数据库 (使用小写键)
        rename_map = {
            "sma_5": "ma5",
            "sma_10": "ma10",
            "sma_20": "ma20",
            "sma_60": "ma60",
            "macd_12_26_9": "macd_hist",
            "macdh_12_26_9": "macd_dif",
            "macds_12_26_9": "macd_dea",
            "k_9_3": "kdj_k",
            "d_9_3": "kdj_d",
            "j_9_3": "kdj_j",
            "rsi_6": "rsi6",
            "rsi_12": "rsi12",
            "rsi_24": "rsi24",
            "bbl_20_2.0_2.0": "boll_low",
            "bbm_20_2.0_2.0": "boll_mid",
            "bbu_20_2.0_2.0": "boll_up",
            "adx_14": "adx",
            "ATRr_14": "atr",
        }
        df_with_indicators.rename(columns=rename_map, inplace=True)

        # 添加主键列
        df_with_indicators["ts_code"] = ts_code
        df_with_indicators.reset_index(inplace=True)

        # 选取要插入的列
        columns_to_insert = [
            "ts_code", "trade_date", "ma5", "ma10", "ma20", "ma60",
            "macd_dif", "macd_dea", "macd_hist", "kdj_k", "kdj_d", "kdj_j",
            "rsi6", "rsi12", "rsi24", "boll_up", "boll_mid", "boll_low", "adx", "atr"
        ]
        columns_to_insert = [
            col for col in columns_to_insert if col in df_with_indicators.columns
        ]
        df_to_insert = df_with_indicators[columns_to_insert]

        # 清理 NaN
        df_to_insert = df_to_insert.astype(object).where(
            pd.notnull(df_to_insert), None
        )

        # 转换为字典列表
        data = df_to_insert.to_dict("records")

        # 批量插入
        if data:
            logging.info(
                f"Inserting/updating {len(data)} indicator records for {ts_code}..."
            )
            count = db.insert_tech_indicators(data)
            logging.info(f"Successfully processed {count} records for {ts_code}.")
        else:
            logging.warning("No indicator data to insert.")

    except Exception as e:
        logging.error(f"Failed to process indicators for {ts_code}: {e}", exc_info=True)
    finally:
        db.close()


def batch_process_indicators(stocks: List[str], **kwargs):
    """
    批量处理多只股票的技术指标计算与存储。
    """
    logging.info(f"Starting batch processing for {len(stocks)} stocks.")
    for stock in stocks:
        process_and_store_indicators(ts_code=stock, **kwargs)
    logging.info("Batch processing finished.")


if __name__ == "__main__":
    load_dotenv()
    # --- 示例1: 计算并存储单只股票 (小米集团) 的所有技术指标 ---
    process_and_store_indicators(ts_code="01810.HK")
    process_and_store_indicators(ts_code="00700.HK")

    # --- 示例2: 批量计算并存储多只股票 (腾讯、阿里) 的 MA 和 RSI 指标 ---
    # stocks_to_process = ["00700.HK", "09988.HK"]
    # batch_process_indicators(stocks=stocks_to_process, indicator_types=["ma", "rsi"])
