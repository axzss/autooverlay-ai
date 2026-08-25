// Shared types for the application
export interface AccountInfo {
  account_id: string
  status: "ACTIVE" | "INACTIVE"
  currency: string
  cash: string
  cash_withdrawable: string
  cash_transferable: string
  portfolio_value: string
  pattern_day_trader: boolean
  trade_suspended_by_user: boolean
  shorting_enabled: boolean
  long_market_value: string
  short_market_value: string
  equity: string
  last_equity: string
  multiplier: string
}

export interface Position {
  asset_id: string
  symbol: string
  name: string
  qty: string
  avg_entry_price: string
  market_value: string
  cost_basis: string
  unrealized_pl: string
  unrealized_plpc: string
  change_today: string
  asset_class: string
  exchange: string
  id: string
}

export interface Order {
  id: string
  client_order_id: string
  created_at: string
  updated_at: string
  submitted_at: string
  filled_at: string
  expired_at: string | null
  canceled_at: string | null
  failed_at: string | null
  symbol: string
  qty: string
  legs: any
  side: "buy" | "sell"
  type: "market" | "limit"
  trend: string
  time_in_force: string
  limit_price: string | null
  stop_price: string | null
  status: "new" | "partially_filled" | "filled" | "done"
  extended_hours: boolean
  leveraged_by: string | null
  timestamp: string
  filled_avg_price: string
}

export interface CoveredCallOpportunity {
  symbol: string
  underlying_price: number
  option_symbol: string
  strike_price: number
  expiration_date: string
  days_to_expiry: number
  bid: number
  ask: number
  last_price: number
  volume: number
  open_interest: number
  implied_volatility: number
  delta: number
  gamma: number
  theta: number
  vega: number
  premium_received_per_share: number
  total_premium_received: number
  max_return_if_called_away: number
  annualized_return_rate: number
  probability_itm: number
  cagr_if_held_to_expiry: number
  recommendation: "HOLD_POSITION" | "INITIATE_POSITION" | "MONITOR_CLOSELY" | "CLOSE_POSITION"
  reasoning: string
}

export interface PortfolioData {
  account_info: AccountInfo
  positions: Position[]
  orders: Order[]
  covered_call_opportunities: CoveredCallOpportunity[]
}
