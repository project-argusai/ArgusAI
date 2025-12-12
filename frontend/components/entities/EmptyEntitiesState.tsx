/**
 * EmptyEntitiesState component - displayed when no entities exist (Story P4-3.6)
 * AC13: Empty state with helpful guidance
 */

import { Users } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface EmptyEntitiesStateProps {
  /** Whether filters are applied (show different message) */
  hasFilters?: boolean;
  /** Callback to clear filters */
  onClearFilters?: () => void;
}

/**
 * Empty state component for the entities list
 */
export function EmptyEntitiesState({
  hasFilters = false,
  onClearFilters,
}: EmptyEntitiesStateProps) {
  if (hasFilters) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="mb-4 p-4 bg-muted rounded-full">
          <Users className="h-12 w-12 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold mb-2">No matching entities</h3>
        <p className="text-sm text-muted-foreground mb-6 max-w-md">
          No entities match your current filters. Try adjusting or clearing them.
        </p>
        {onClearFilters && (
          <Button variant="outline" onClick={onClearFilters}>
            Clear Filters
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="mb-4 p-4 bg-muted rounded-full">
        <Users className="h-12 w-12 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-semibold mb-2">No recognized entities yet</h3>
      <p className="text-sm text-muted-foreground max-w-md">
        Entities are automatically created when the same person or vehicle is seen
        multiple times. As your cameras detect recurring visitors, they will
        appear here.
      </p>
    </div>
  );
}
