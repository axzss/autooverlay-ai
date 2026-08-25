import { forwardRef } from 'react'
import { cn } from '@/lib/utils'

interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'destructive' | 'outline' | 'secondary'
}

const Badge = forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant = 'default', ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-offset-background transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          {
            'bg-secondary text-secondary-foreground': variant === 'default',
            'bg-primary text-primary-foreground': variant === 'primary',
            'bg-green-500/20 text-green-400': variant === 'success',
            'bg-amber-500/20 text-amber-400': variant === 'warning',
            'bg-secondary/20 text-secondary': variant === 'secondary',
            'bg-destructive text-destructive-foreground': variant === 'destructive',
            'border border-input text-foreground': variant === 'outline',
          },
          className
        )}
        {...props}
      />
    )
  }
)
Badge.displayName = 'Badge'

export { Badge }
