'use client'

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { CheckCircle2, XCircle, Clock, AlertCircle } from 'lucide-react'

interface TradeLogProps {
  limit?: number
}

type TradeStatus = 'filled' | 'open' | 'canceled' | 'failed'

interface Trade {
  id: string
  symbol: string
  side: 'buy' | 'sell'
  qty: string
  price: string
  status: TradeStatus
  timestamp: string
}

export default function TradeLog({ limit = 10 }: TradeLogProps) {
  // Mock trade data - will be replaced with real API calls
  const trades: Trade[] = [
    { id: '1', symbol: 'AAPL', side: 'sell', qty: '1', price: '$1.28', status: 'filled', timestamp: '2024-06-18T10:30:00Z' },
    { id: '2', symbol: 'MSFT', side: 'sell', qty: '1', price: '$2.15', status: 'open', timestamp: '2024-06-20T14:15:00Z' },
    { id: '3', symbol: 'NVDA', side: 'buy', qty: '1', price: '$2.15', status: 'canceled', timestamp: '2024-06-19T09:45:00Z' },
  ]

  const statusIcons = {
    filled: <CheckCircle2 className="h-4 w-4 text-green-500" />,
    open: <Clock className="h-4 w-4 text-blue-500" />,
    canceled: <XCircle className="h-4 w-4 text-red-500" />,
    failed: <AlertCircle className="h-4 w-4 text-orange-500" />,
  }

  const statusColors: Record<TradeStatus, string> = {
    filled: 'bg-green-500/20 text-green-400',
    open: 'bg-blue-500/20 text-blue-400',
    canceled: 'bg-red-500/20 text-red-400',
    failed: 'bg-orange-500/20 text-orange-400',
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Trades</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {trades.slice(0, limit).map((trade) => (
            <div key={trade.id} className="flex items-center justify-between p-3 rounded-lg border">
              <div className="flex items-center space-x-3">
                <div className="flex-shrink-0">
                  {statusIcons[trade.status]}
                </div>
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-medium">{trade.symbol}</span>
                    <Badge 
                      variant={trade.side === 'sell' ? 'secondary' : 'outline'}
                      className="text-xs"
                    >
                      {trade.side.toUpperCase()}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {trade.qty} contract @ {trade.price}
                  </p>
                </div>
              </div>
              
              <div className="text-right">
                <Badge className={statusColors[trade.status]}>
                  {trade.status}
                </Badge>
                <p className="text-xs text-muted-foreground mt-1">
                  {new Date(trade.timestamp).toLocaleString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                  })}
                </p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
