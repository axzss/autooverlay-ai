'use client'

import { Order } from '@/types/portfolio'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { CheckCircle2, XCircle, Clock, RefreshCw } from 'lucide-react'
import { ReactNode } from 'react'

interface TradeHistoryProps {
  orders: Order[]
}

// Map order statuses to their respective icons
function getStatusIcon(status: string): ReactNode {
  switch(status) {
    case 'filled':
      return <CheckCircle2 className="h-4 w-4 text-green-500" />
    case 'open':
      return <Clock className="h-4 w-4 text-blue-500 animate-pulse" />
    case 'canceled':
      return <XCircle className="h-4 w-4 text-red-500" />
    case 'done':
      return <CheckCircle2 className="h-4 w-4 text-green-500" />
    case 'partially_filled':
      return <RefreshCw className="h-4 w-4 text-yellow-500 animate-spin" />
    default:
      return <Clock className="h-4 w-4 text-blue-500 animate-pulse" />
  }
}

export default function TradeHistory({ orders }: TradeHistoryProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Past Executions</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {orders.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">No recent executions</p>
          ) : (
            orders.map((order) => (
              <div key={order.id} className="border rounded-lg p-4 flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <div className="flex-shrink-0">
                    {getStatusIcon(order.status)}
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="font-medium">{order.symbol}</span>
                      <Badge variant={order.side === 'buy' ? 'outline' : 'secondary'}>
                        {order.side.toUpperCase()}
                      </Badge>
                      <Badge className={order.status === 'filled' ? 'bg-green-500/20 text-green-400' : 'bg-blue-500/20 text-blue-400'}>
                        {order.status}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      {order.qty} contracts @ ${order.filled_avg_price || '—'}
                    </p>
                  </div>
                </div>
                
                <div className="text-right">
                  <p className="font-medium">
                    ${order.filled_avg_price 
                      ? (parseFloat(order.filled_avg_price) * parseFloat(order.qty)).toFixed(2) 
                      : '—'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(order.created_at).toLocaleString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  )
}
