'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { AccountInfo, Position } from '@/types/portfolio'
import { ArrowUpDown, DollarSign, TrendingUp, Wallet } from 'lucide-react'

interface PortfolioOverviewProps {
  positions: Position[]
  accountInfo: AccountInfo
}

export default function PortfolioOverview({ positions, accountInfo }: PortfolioOverviewProps) {
  const totalValue = Number(accountInfo.portfolio_value)
  const totalCash = Number(accountInfo.cash)
  
  // Calculate portfolio change
  const equity = Number(accountInfo.equity)
  const lastEquity = Number(accountInfo.last_equity)
  const changeAmount = equity - lastEquity
  const changePct = ((changeAmount / lastEquity) * 100).toFixed(2)
  
  // Calculate total gains from positions
  const totalGain = positions.reduce((sum, pos) => sum + parseFloat(pos.unrealized_pl), 0)

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card className="bg-surface-container border-outline-variant">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-on-surface-variant">
            Total Portfolio Value
          </CardTitle>
          <DollarSign className="h-4 w-4 text-on-surface-variant" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-on-surface">${totalValue.toLocaleString('en-US', {maximumFractionDigits: 2})}</div>
          <p className={`text-xs ${changeAmount >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {changeAmount >= 0 ? '+' : ''}${changeAmount.toFixed(2)} ({changePct}%) from last update
          </p>
        </CardContent>
      </Card>

      <Card className="bg-surface-container border-outline-variant">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-on-surface-variant">
            Cash Available
          </CardTitle>
          <Wallet className="h-4 w-4 text-on-surface-variant" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-on-surface">${totalCash.toLocaleString('en-US', {maximumFractionDigits: 2})}</div>
          <p className="text-xs text-on-surface-variant">
            {((totalCash / totalValue) * 100).toFixed(1)}% of portfolio
          </p>
        </CardContent>
      </Card>

      <Card className="bg-surface-container border-outline-variant">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-on-surface-variant">
            Day P&L
          </CardTitle>
          <TrendingUp className="h-4 w-4 text-on-surface-variant" />
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${changeAmount >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {changeAmount >= 0 ? '+' : ''}${changeAmount.toFixed(2)}
          </div>
          <p className="text-xs text-on-surface-variant">
            {changePct}% of portfolio value
          </p>
        </CardContent>
      </Card>

      <Card className="bg-surface-container border-outline-variant">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-on-surface-variant">
            Unrealized Gains
          </CardTitle>
          <ArrowUpDown className="h-4 w-4 text-on-surface-variant" />
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${totalGain >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${totalGain.toFixed(2)}
          </div>
          <p className="text-xs text-on-surface-variant">
            {((totalGain / (totalValue - totalCash)) * 100).toFixed(2)}% return on invested capital
          </p>
        </CardContent>
      </Card>

      {/* Positions Table */}
      <Card className="md:col-span-2 lg:col-span-4 bg-surface-container border-outline-variant">
        <CardHeader>
          <CardTitle className="text-on-surface">Current Holdings</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {positions.map((position) => {
              const marketValue = Number(position.market_value)
              const costBasis = Number(position.cost_basis)
              const gainLoss = marketValue - costBasis
              const gainLossPercent = ((gainLoss / costBasis) * 100).toFixed(2)
              
              return (
                <div key={position.asset_id} className="flex items-center justify-between border border-outline-variant rounded-lg p-3 hover:bg-surface-bright/50 transition-colors">
                  <div className="flex items-center space-x-4">
                    <div>
                      <p className="font-medium text-on-surface">{position.symbol}</p>
                      <p className="text-sm text-on-surface-variant">{position.name}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-medium text-on-surface">{position.qty} shares</p>
                    <p className="text-sm text-on-surface-variant">Avg ${Number(position.avg_entry_price).toFixed(2)}</p>
                  </div>
                  <div className="text-right">
                    <p className={`font-medium ${gainLoss >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${gainLoss.toFixed(2)}
                    </p>
                    <Badge variant={gainLoss >= 0 ? 'success' : 'warning'}>
                      {gainLossPercent}%
                    </Badge>
                  </div>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
