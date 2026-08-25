'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Send, Bot, User, AlertCircle, Zap, ChevronDown } from 'lucide-react'

export default function AIAnalysisPanel() {
  return (
    <div className="grid gap-6">
      <Card className="bg-surface-container border-outline-variant">
        <CardHeader>
          <CardTitle className="flex items-center space-x-2 text-on-surface">
            <Bot className="h-5 w-5 text-primary glow-emerald" />
            <span>AI Trading Assistant</span>
            <Badge variant="success" className="ml-auto">
              Active
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[400px] overflow-y-auto space-y-4 mb-4 ai-terminal">
            {/* Sample AI messages */}
            <div className="space-y-3 p-3">
              <div className="flex space-x-3">
                <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
                  <Bot className="h-4 w-4 text-primary" />
                </div>
                <div className="bg-surface-bright/50 rounded-lg p-3 max-w-[80%] border border-outline-variant">
                  <p className="text-sm text-on-surface">Analyzing portfolio for income opportunities...</p>
                  <div className="flex items-center space-x-1 mt-2 text-xs text-on-surface-variant">
                    <AlertCircle className="h-3 w-3" />
                    <span>Scanning AAPL options chain</span>
                  </div>
                </div>
              </div>
              
              <div className="flex space-x-3 ml-auto justify-end">
                <div className="bg-primary/10 rounded-lg p-3 max-w-[80%] border border-primary/30">
                  <p className="text-sm text-on-primary">Generate a covered call strategy for my MSFT position</p>
                </div>
                <div className="w-8 h-8 rounded-full bg-secondary/20 flex items-center justify-center flex-shrink-0">
                  <User className="h-4 w-4 text-secondary" />
                </div>
              </div>
              
              <div className="flex space-x-3">
                <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
                  <Bot className="h-4 w-4 text-primary" />
                </div>
                <div className="bg-surface-bright/50 rounded-lg p-3 max-w-[80%] border border-outline-variant">
                  <p className="text-sm text-on-surface">
                    Found 2 high-probability covered call opportunities for MSFT:
                  </p>
                  <ul className="list-disc list-inside mt-2 space-y-1 text-sm">
                    <li className="text-green-400 trade-buy">BUY MSFT240628C00355000</li>
                    <li className="text-red-400 trade-sell">SELL MSFT240705C0036000</li>
                  </ul>
                  <div className="flex items-center space-x-1 mt-2 text-xs text-on-surface-variant">
                    <Zap className="h-3 w-3 text-primary" />
                    <span>Recommendation: <strong className="text-primary">INITIATE_POSITION</strong> for higher yield</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <div className="flex-1 relative">
              <input
                type="text"
                placeholder="Ask the AI assistant about strategies..."
                className="w-full rounded-md border border-outline-variant bg-surface-bright px-4 py-2 text-sm text-on-surface placeholder-on-surface-variant/50 focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <div className="absolute right-3 top-1/2 -translate-y-1/2">
                <Send className="h-4 w-4 text-on-surface-variant" />
              </div>
            </div>
            <Button size="sm" className="bg-primary text-primary-foreground hover:bg-primary/80">
              Send
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-surface-container border-outline-variant">
        <CardHeader>
          <CardTitle className="text-on-surface">AI Strategy Parameters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <label className="text-sm font-medium mb-2 block text-on-surface">Max Risk Tolerance</label>
              <select className="w-full rounded-md border border-outline-variant bg-surface-bright px-3 py-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary">
                <option>Conservative (2% max drawdown)</option>
                <option>Moderate (5% max drawdown)</option>
                <option>Aggressive (10% max drawdown)</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block text-on-surface">Target Yield</label>
              <select className="w-full rounded-md border border-outline-variant bg-surface-bright px-3 py-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary">
                <option>Monthly (1-3%)</option>
                <option>Bi-weekly (2-5%)</option>
                <option>Weekly (3-8%)</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block text-on-surface">Asset Allocation</label>
              <select className="w-full rounded-md border border-outline-variant bg-surface-bright px-3 py-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary">
                <option>Single Asset Focus</option>
                <option>Portfolio-wide</option>
                <option>High IV Opportunities</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
