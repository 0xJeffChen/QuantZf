CREATE TABLE IF NOT EXISTS symbols (
  symbol_id BIGINT UNSIGNED NOT NULL COMMENT '标的主键（由应用侧生成/分配）',
  exchange VARCHAR(16) NOT NULL COMMENT '交易所/市场标识，如 SSE、SZSE、HKEX 等',
  asset_class ENUM('equity','futures','fx') NOT NULL COMMENT '资产类别：股票/期货/外汇',
  code VARCHAR(32) NOT NULL COMMENT '标的代码（按你的约定，如 700.HK、600000.SH 等）',
  canonical VARCHAR(96) AS (CONCAT(exchange, '.', asset_class, '.', code)) STORED COMMENT '全局唯一标识 exchange.asset_class.code（生成列）',
  PRIMARY KEY (symbol_id),
  UNIQUE KEY uk_symbols_canonical (canonical),
  KEY idx_symbols_lookup (exchange, asset_class, code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='标的维表';

CREATE TABLE IF NOT EXISTS bars (
  bar_id BIGINT UNSIGNED NOT NULL COMMENT 'K线主键（由应用侧生成/分配）',
  symbol_id BIGINT UNSIGNED NOT NULL COMMENT '标的ID（逻辑关联 symbols.symbol_id；bars 分区不使用外键）',
  freq ENUM('1m','5m','15m','30m','60m','1d','1w','1mo') NOT NULL COMMENT 'K线周期：1m/5m/15m/30m/60m/1d/1w/1mo',
  ts DATETIME(6) NOT NULL COMMENT 'Bar时间戳（建议统一为Bar结束时刻，并统一时区口径）',
  open DECIMAL(20,8) NOT NULL COMMENT '开盘价',
  high DECIMAL(20,8) NOT NULL COMMENT '最高价',
  low  DECIMAL(20,8) NOT NULL COMMENT '最低价',
  close DECIMAL(20,8) NOT NULL COMMENT '收盘价',
  volume DECIMAL(28,8) NOT NULL COMMENT '成交量',
  turnover DECIMAL(28,8) NULL COMMENT '成交额（可为空）',
  PRIMARY KEY (bar_id, ts),
  UNIQUE KEY uk_bars_symbol_freq_ts (symbol_id, freq, ts),
  KEY idx_bars_freq_ts (freq, ts),
  KEY idx_bars_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='行情K线表（可按ts分区）';

CREATE TABLE IF NOT EXISTS backtest_runs (
  backtest_run_id BIGINT UNSIGNED NOT NULL COMMENT '回测运行主键（由应用侧生成/分配）',
  run_uuid CHAR(32) NOT NULL COMMENT '回测运行UUID（程序生成，用于对外引用/幂等）',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '回测创建时间',
  freq ENUM('1m','5m','15m','30m','60m','1d','1w','1mo') NOT NULL COMMENT '回测使用的数据频率',
  initial_cash DECIMAL(28,8) NOT NULL COMMENT '初始资金',
  params_json JSON NULL COMMENT '回测/策略参数快照（JSON）',
  PRIMARY KEY (backtest_run_id),
  UNIQUE KEY uk_backtest_runs_uuid (run_uuid),
  KEY idx_runs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='回测运行元数据';

CREATE TABLE IF NOT EXISTS orders (
  order_id BIGINT UNSIGNED NOT NULL COMMENT '订单主键（由应用侧生成/分配）',
  backtest_run_id BIGINT UNSIGNED NOT NULL COMMENT '所属回测运行ID（逻辑关联 backtest_runs.backtest_run_id）',
  symbol_id BIGINT UNSIGNED NOT NULL COMMENT '标的ID（逻辑关联 symbols.symbol_id）',
  ts DATETIME(6) NOT NULL COMMENT '下单时间戳',
  qty DECIMAL(28,8) NOT NULL COMMENT '下单数量（正数，方向由side决定）',
  side ENUM('buy','sell') NOT NULL COMMENT '买卖方向',
  type ENUM('market','limit','stop') NOT NULL COMMENT '订单类型：市价/限价/止损',
  price DECIMAL(20,8) NULL COMMENT '价格（限价/止损触发价；市价单可为空）',
  client_order_id VARCHAR(64) NOT NULL DEFAULT '' COMMENT '客户端订单号（用于幂等/去重，同一run内唯一）',
  PRIMARY KEY (order_id),
  UNIQUE KEY uk_orders_run_client (backtest_run_id, client_order_id),
  KEY idx_orders_run_ts (backtest_run_id, ts),
  KEY idx_orders_symbol_ts (symbol_id, ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='回测订单流水';

CREATE TABLE IF NOT EXISTS fills (
  fill_id BIGINT UNSIGNED NOT NULL COMMENT '成交主键（由应用侧生成/分配）',
  backtest_run_id BIGINT UNSIGNED NOT NULL COMMENT '所属回测运行ID（逻辑关联 backtest_runs.backtest_run_id）',
  order_id BIGINT UNSIGNED NOT NULL COMMENT '对应订单ID（逻辑关联 orders.order_id）',
  fill_ts DATETIME(6) NOT NULL COMMENT '成交时间戳',
  fill_price DECIMAL(20,8) NOT NULL COMMENT '成交价（已计入滑点后的价格）',
  filled_qty DECIMAL(28,8) NOT NULL COMMENT '成交数量',
  fee DECIMAL(28,8) NOT NULL COMMENT '手续费/交易成本',
  PRIMARY KEY (fill_id),
  KEY idx_fills_run_ts (backtest_run_id, fill_ts),
  KEY idx_fills_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='回测成交流水';

CREATE TABLE IF NOT EXISTS equity_curve (
  equity_curve_id BIGINT UNSIGNED NOT NULL COMMENT '权益曲线主键（由应用侧生成/分配）',
  backtest_run_id BIGINT UNSIGNED NOT NULL COMMENT '所属回测运行ID（逻辑关联 backtest_runs.backtest_run_id）',
  ts DATETIME(6) NOT NULL COMMENT '权益点时间戳（通常对齐bar时间）',
  equity DECIMAL(28,8) NOT NULL COMMENT '总权益：现金 + 持仓市值',
  PRIMARY KEY (equity_curve_id),
  UNIQUE KEY uk_equity_curve_run_ts (backtest_run_id, ts),
  KEY idx_equity_curve_run_ts (backtest_run_id, ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='回测权益曲线';
