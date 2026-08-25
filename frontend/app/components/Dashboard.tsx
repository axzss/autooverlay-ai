'use client'

import { PortfolioData } from '@/types/portfolio'
import PortfolioOverview from '@/components/portfolio/PortfolioOverview'
import StrategyOpportunities from '@/components/strategy/StrategyOpportunities'
import AIAnalysisPanel from '@/components/ai/AIAnalysisPanel'
import TradeHistory from '@/components/trading/TradeHistory'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

interface DashboardProps {
  data: PortfolioData
}

export default function Dashboard({ data }: DashboardProps) {
  return (
    <div className="p-6 space-y-6">
      <PortfolioOverview positions={data.positions} accountInfo={data.account_info} />
      
      <Tabs defaultValue="opportunities" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3 lg:grid-cols-4 gap-2">
          <TabsTrigger value="opportunities">Strategy Opportunities</TabsTrigger>
          <TabsTrigger value="analysis">AI Analysis</TabsTrigger>
          <TabsTrigger value="trade-history">Trade History</TabsTrigger>
          <TabsTrigger value="risk">Risk Dashboard</TabsTrigger>
        </TabsList>
        
        <TabsContent value="opportunities">
          <StrategyOpportunities opportunities={data.covered_call_opportunities} />
        </TabsContent>
        
        <TabsContent value="analysis">
          <AIAnalysisPanel />
        </TabsContent>
        
        <TabsContent value="trade-history">
          <TradeHistory orders={data.orders} />
        </TabsContent>
        
        <TabsContent value="risk">
          <div className="text-center py-12 text-muted-foreground">
            Risk dashboard coming soon
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
