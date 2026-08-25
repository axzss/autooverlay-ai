'use client'

import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { TrendingUp, Shield, BarChart3 } from 'lucide-react'

interface StrategyCardProps {
  title: string
  description: string
  roi: string
  status: 'active' | 'monitoring' | 'completed'
  icon?: React.ReactNode
}

export default function StrategyCard({ 
  title, 
  description, 
  roi, 
  status = 'monitoring',
  icon
}: StrategyCardProps) {
  const statusConfig = {
    active: { color: 'bg-green-500', label: 'Active' },
    monitoring: { color: 'bg-blue-500', label: 'Monitoring' },
    completed: { color: 'bg-gray-500', label: 'Completed' },
  }

  const config = statusConfig[status]

  return (
    <Card className="p-6 hover:shadow-lg transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            {icon || <Shield className="h-6 w-6 text-primary" />}
          </div>
          <div>
            <h3 className="font-semibold text-lg">{title}</h3>
            <p className="text-sm text-muted-foreground mt-1">{description}</p>
          </div>
        </div>
        <Badge 
          className={`${config.color}/20 text-${config.color.replace('bg-', '')} border-0`}
        >
          {config.label}
        </Badge>
      </div>
      
      <div className="mt-4 flex items-center justify-between">
        <div className="flex items-center space-x-1">
          <TrendingUp className="h-4 w-4 text-green-500" />
          <span className="font-bold text-lg">{roi}</span>
          <span className="text-sm text-muted-foreground">Projected ROI</span>
        </div>
        <button className="text-sm text-primary hover:text-primary/80 font-medium">
          View Details →
        </button>
      </div>
    </Card>
  )
}
