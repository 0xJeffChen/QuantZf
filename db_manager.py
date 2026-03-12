import mysql.connector
import os
from typing import List, Dict, Any, Optional
from datetime import date
from decimal import Decimal
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

class DBManager:
    """
    MySQL 数据库管理类，用于港股日K线数据的存储与删除。
    """
    def __init__(self):
        # 从环境变量读取配置
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = int(os.getenv("DB_PORT", 3306))
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "")
        self.database = os.getenv("DB_NAME", "quant_db")
        self.connection = None

    def connect(self):
        """建立数据库连接"""
        try:
            if self.connection is None or not self.connection.is_connected():
                self.connection = mysql.connector.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    charset="utf8mb4"
                )
            return self.connection
        except mysql.connector.Error as err:
            print(f"Error: {err}")
            raise

    def close(self):
        """关闭数据库连接"""
        if self.connection and self.connection.is_connected():
            self.connection.close()

    def insert_hk_stock_daily(self, data: List[Dict[str, Any]]) -> int:
        """
        插入港股日K线数据。
        
        :param data: 字典列表，每个字典包含表中的字段
        :return: 成功插入的记录数
        """
        if not data:
            return 0
        
        conn = self.connect()
        cursor = conn.cursor()
        
        sql = """
        INSERT INTO hk_stock_daily (
            ts_code, trade_date, open, high, low, close, `change`, pct_chg, vol, amount, turnover_rate
        ) VALUES (
            %(ts_code)s, %(trade_date)s, %(open)s, %(high)s, %(low)s, %(close)s, %(change)s, %(pct_chg)s, %(vol)s, %(amount)s, %(turnover_rate)s
        ) ON DUPLICATE KEY UPDATE
            open=VALUES(open), high=VALUES(high), low=VALUES(low), close=VALUES(close),
            `change`=VALUES(`change`), pct_chg=VALUES(pct_chg), vol=VALUES(vol),
            amount=VALUES(amount), turnover_rate=VALUES(turnover_rate)
        """
        
        try:
            cursor.executemany(sql, data)
            conn.commit()
            return cursor.rowcount
        except mysql.connector.Error as err:
            conn.rollback()
            print(f"Error during insert: {err}")
            raise
        finally:
            cursor.close()

    def get_daily_with_indicators(self, ts_code: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """
        联合查询日K线和技术指标数据。

        :param ts_code: 股票代码
        :param start_date: 开始日期
        :param end_date: 结束日期
        :return: 包含合并数据的字典列表
        """
        conn = self.connect()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT
            d.trade_date, d.open, d.high, d.low, d.close, d.vol,
            i.ma5, i.ma10, i.ma20, i.ma60, i.rsi6, i.rsi12, i.rsi24, i.adx
        FROM 
            hk_stock_daily d
        LEFT JOIN 
            hk_stock_tech_indicators i ON d.ts_code = i.ts_code AND d.trade_date = i.trade_date
        WHERE 
            d.ts_code = %s
        """
        params = [ts_code]

        if start_date:
            sql += " AND d.trade_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND d.trade_date <= %s"
            params.append(end_date)
        
        sql += " ORDER BY d.trade_date ASC"

        try:
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()
        except mysql.connector.Error as err:
            print(f"Error during joined select: {err}")
            raise
        finally:
            cursor.close()

    def get_hk_stock_daily(self, ts_code: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """
        根据股票代码和日期范围查询日K线数据。

        :param ts_code: 股票代码 (如 00700.HK)
        :param start_date: 开始日期 (可选)
        :param end_date: 结束日期 (可选)
        :return: 包含日K线数据的字典列表
        """
        conn = self.connect()
        cursor = conn.cursor(dictionary=True) # 使用字典游标

        sql = "SELECT trade_date, open, high, low, close, vol FROM hk_stock_daily WHERE ts_code = %s"
        params = [ts_code]

        if start_date:
            sql += " AND trade_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND trade_date <= %s"
            params.append(end_date)
        
        sql += " ORDER BY trade_date ASC" # 保证数据按时间升序

        try:
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()
        except mysql.connector.Error as err:
            print(f"Error during select: {err}")
            raise
        finally:
            cursor.close()

    def insert_tech_indicators(self, data: List[Dict[str, Any]]) -> int:
        """
        批量插入或更新技术指标数据。

        :param data: 字典列表，每个字典包含技术指标表中的字段
        :return: 成功插入/更新的记录数
        """
        if not data:
            return 0
        
        conn = self.connect()
        cursor = conn.cursor()

        # 获取所有列名用于构建SQL语句
        if not data[0]: return 0
        columns = data[0].keys()
        
        sql_columns = ", ".join([f"`{col}`" for col in columns])
        sql_placeholders = ", ".join([f"%({col})s" for col in columns])
        sql_update = ", ".join([f"`{col}`=VALUES(`{col}`)" for col in columns if col not in ["ts_code", "trade_date"]])

        sql = f"""
        INSERT INTO hk_stock_tech_indicators ({sql_columns})
        VALUES ({sql_placeholders})
        ON DUPLICATE KEY UPDATE {sql_update}
        """

        try:
            cursor.executemany(sql, data)
            conn.commit()
            return cursor.rowcount
        except mysql.connector.Error as err:
            conn.rollback()
            print(f"Error during indicator insert: {err}")
            raise
        finally:
            cursor.close()

    def delete_hk_stock_daily(self, ts_code: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> int:
        """
        根据股票代码和日期范围删除日K线数据。
        
        :param ts_code: 股票代码 (如 00700.HK)
        :param start_date: 开始日期 (可选)
        :param end_date: 结束日期 (可选)
        :return: 删除的记录数
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        sql = "DELETE FROM hk_stock_daily WHERE ts_code = %s"
        params = [ts_code]
        
        if start_date:
            sql += " AND trade_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND trade_date <= %s"
            params.append(end_date)
            
        try:
            cursor.execute(sql, tuple(params))
            conn.commit()
            return cursor.rowcount
        except mysql.connector.Error as err:
            conn.rollback()
            print(f"Error during delete: {err}")
            raise
        finally:
            cursor.close()

if __name__ == "__main__":
    # 示例用法
    # 注意：运行前请确保设置了相应的环境变量
    # export DB_HOST=localhost
    # export DB_USER=root
    # export DB_PASSWORD=your_password
    # export DB_NAME=your_db
    
    db = DBManager()
    
    # 插入示例数据
    sample_data = [
        {
            "ts_code": "00700.HK",
            "trade_date": "2023-10-27",
            "open": 290.000,
            "high": 295.000,
            "low": 288.000,
            "close": 292.400,
            "change": 2.400,
            "pct_chg": 0.0083,
            "vol": 1500000,
            "amount": 440000000.000,
            "turnover_rate": 0.015
        }
    ]
    
    try:
        inserted = db.insert_hk_stock_daily(sample_data)
        print(f"Successfully inserted {inserted} records.")
        
        # 删除示例数据
        # deleted = db.delete_hk_stock_daily("00700.HK", start_date="2023-10-27", end_date="2023-10-27")
        # print(f"Successfully deleted {deleted} records.")
    except Exception as e:
        print(f"Test failed: {e}")
    finally:
        db.close()
