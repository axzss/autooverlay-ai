'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Shield, TrendingUp, BarChart3, ArrowRightLeft } from 'lucide-react'

interface OverlayControlProps {
  // Props will be defined when integrated with parent
}

export default function OverlayControl({}: OverlayControlProps) {
  return (
    <Card className="bg-card/30 border-border">
      <CardHeader>
        <CardTitle className="flex items-center space-x-2">
          <Shield className="h-5 w-5 text-primary" />
          <span>Portfolio Overlay Control</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {/* Strategy Status */}
          <div className="flex items-center justify-between p-4 bg-muted/20 rounded-lg">
            <div className="flex items-center space-x-3">
              <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
              <div>
                <p className="font-medium">Covered Call Engine</p>
                <p className="text-sm text-muted-foreground">Active monitoring positions</p>
              </div>
            </div>
            <Badge variant="success">Active</Badge>
          </div>

          {/* Performance Metrics */}
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="text-2xl font-bold text-green-400">+2.3%</p>
              <p className="text-xs text-muted-foreground">Monthly Return</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-primary">7</p>
              <p className="text-xs text-muted-foreground">Strategies Active</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-secondary">$187.50</p>
              <p className="text-xs text-muted-foreground">Premium Collected</p>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="grid grid-cols-2 gap-3">
            <button className="flex items-center justify-center space-x-2 p-3 rounded-lg border border-input hover:bg-accent transition-colors">
              <TrendingUp className="h-4 w-4" />
              <span>Deploy New Strategy</span>
            </button>
            <button className="flex items-center justify-center space-x-2 p-3 rounded-lg border border-input hover:bg-accent transition-colors">
              <ArrowRightLeft className="h-4 w-4" />
              <span>Rebalance Portfolio</span>
            </button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
