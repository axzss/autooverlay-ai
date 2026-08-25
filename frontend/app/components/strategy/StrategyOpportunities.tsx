'use client'

import { CoveredCallOpportunity } from '@/types/portfolio'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { 
  TrendingUp, 
  Calendar, 
  DollarSign, 
  BarChart3, 
  AlertTriangle, 
  CheckCircle2,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface StrategyOpportunitiesProps {
  opportunities: CoveredCallOpportunity[]
}

export default function StrategyOpportunities({ opportunities }: StrategyOpportunitiesProps) {
  const recommendationIcons = {
    INITIATE_POSITION: CheckCircle2,
    HOLD_POSITION: TrendingUp,
    MONITOR_CLOSELY: AlertTriangle,
    CLOSE_POSITION: BarChart3,
  }

  const recommendationColors = {
    INITIATE_POSITION: 'bg-green-500/20 text-green-400 border-green-500/30',
    HOLD_POSITION: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    MONITOR_CLOSELY: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    CLOSE_POSITION: 'bg-red-500/20 text-red-400 border-red-500/30',
  }

  return (
    <Card className="bg-surface-container border-outline-variant">
      <CardHeader>
        <CardTitle className="text-on-surface">Covered Call Opportunities</CardTitle>
        <p className="text-sm text-on-surface-variant">
          AI-recommended strategies based on current market conditions
        </p>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {opportunities.map((opp) => {
            const Icon = recommendationIcons[opp.recommendation]
            return (
              <div key={opp.option_symbol} className="border border-outline-variant rounded-lg p-6 hover:border-primary/50 transition-colors">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center space-x-3">
                    <div className="p-2 rounded-lg bg-primary/10 glow-emerald">
                      <Icon className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-on-surface">{opp.symbol} Covered Call</h3>
                      <p className="text-sm text-on-surface-variant">
                        Strike: ${opp.strike_price} • Expires: {opp.expiration_date}
                      </p>
                    </div>
                  </div>
                  <Badge 
                    className={recommendationColors[opp.recommendation]}
                  >
                    {opp.recommendation.replace('_', ' ')}
                  </Badge>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div>
                    <p className="text-sm text-on-surface-variant">Premium</p>
                    <p className="font-bold text-on-surface">${opp.premium_received_per_share.toFixed(2)}/share</p>
                  </div>
                  <div>
                    <p className="text-sm text-on-surface-variant">Total Premium</p>
                    <p className="font-bold text-on-surface">${opp.total_premium_received.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-on-surface-variant">Annualized Return</p>
                    <p className="font-bold text-primary">{(opp.annualized_return_rate * 100).toFixed(1)}%</p>
                  </div>
                  <div>
                    <p className="text-sm text-on-surface-variant">Days to Expiry</p>
                    <p className="font-bold text-on-surface">{opp.days_to_expiry}D</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
                  <div>
                    <p className="text-on-surface-variant">Delta</p>
                    <p className="text-on-surface">{opp.delta.toFixed(4)}</p>
                  </div>
                  <div>
                    <p className="text-on-surface-variant">Theta</p>
                    <p className="text-on-surface">{opp.theta.toFixed(4)}</p>
                  </div>
                  <div>
                    <p className="text-on-surface-variant">IV</p>
                    <p className="text-on-surface">{(opp.implied_volatility * 100).toFixed(1)}%</p>
                  </div>
                  <div>
                    <p className="text-on-surface-variant">Probability ITM</p>
                    <p className="text-on-surface">{(opp.probability_itm * 100).toFixed(1)}%</p>
                  </div>
                </div>

                <div className="bg-surface-bright/30 rounded-lg p-3 mb-4 border border-outline-variant">
                  <p className="text-sm mono-code text-on-surface-variant"><strong>AI Reasoning:</strong> {opp.reasoning}</p>
                </div>

                <div className="flex justify-end space-x-2">
                  <Button variant="outline" size="sm">
                    View Details
                  </Button>
                  <Button 
                    size="sm" 
                    className={cn(
                      opp.recommendation === 'INITIATE_POSITION' 
                        ? 'bg-primary text-primary-foreground hover:bg-primary/80 glow-emerald'
                        : 'bg-surface-bright border border-outline-variant text-on-surface hover:bg-surface-bright/80'
                    )}
                  >
                    {opp.recommendation === 'INITIATE_POSITION' && (
                      <DollarSign className="h-4 w-4 mr-1" />
                    )}
                    Execute
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
