/**
 * EntityList component - displays a filterable, paginated list of entities (Story P4-3.6)
 * AC1: Sorted by last_seen_at descending (server-side)
 * AC3: Filter by entity_type
 * AC4: Filter by named_only
 * AC5: Pagination with configurable page size
 * Story P7-4.2: Search by name with debounce and URL persistence
 * Story P9-4.5: Multi-select for entity merge functionality
 */

'use client';

import { useState, useMemo, useEffect } from 'react';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { useEntities, type UseEntitiesParams } from '@/hooks/useEntities';
import { EntityCard } from './EntityCard';
import { EntityCardSkeleton } from './EntityCardSkeleton';
import { EmptyEntitiesState } from './EmptyEntitiesState';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { ChevronLeft, ChevronRight, Search, X, Merge } from 'lucide-react';
import type { EntityType, IEntity } from '@/types/entity';

interface EntityListProps {
  /** Callback when an entity is clicked */
  onEntityClick: (entity: IEntity) => void;
  /** Default page size (default 50) */
  pageSize?: number;
  /** Story P9-4.5: Set of selected entity IDs for merge */
  selectedEntityIds?: Set<string>;
  /** Story P9-4.5: Callback when entity selection is toggled */
  onToggleSelection?: (entity: IEntity) => void;
  /** Story P9-4.5: Callback to clear all selections */
  onClearSelection?: () => void;
  /** Story P9-4.5: Callback when merge button is clicked */
  onMerge?: (entities: [IEntity, IEntity]) => void;
}

const PAGE_SIZE_OPTIONS = [25, 50, 100];

/**
 * Custom hook for debounced value
 */
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return debouncedValue;
}

/**
 * EntityList component with filtering, search, and pagination
 */
export function EntityList({
  onEntityClick,
  pageSize: defaultPageSize = 50,
  selectedEntityIds = new Set(),
  onToggleSelection,
  onClearSelection,
  onMerge,
}: EntityListProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Initialize state from URL params (Story P7-4.2 AC5)
  const initialSearch = searchParams.get('search') || '';
  const initialType = (searchParams.get('type') as EntityType | 'all') || 'all';

  // Filter state
  const [entityTypeFilter, setEntityTypeFilter] = useState<EntityType | 'all'>(initialType);
  const [namedOnly, setNamedOnly] = useState(false);

  // Search state (Story P7-4.2 AC1)
  const [searchInput, setSearchInput] = useState(initialSearch);
  const debouncedSearch = useDebounce(searchInput, 300);

  // Pagination state
  const [pageSize, setPageSize] = useState(defaultPageSize);
  const [currentPage, setCurrentPage] = useState(0);

  // Sync search and type into the URL (Story P7-4.2 AC5).
  // router.replace is a navigation. Calling it when the query string is already
  // current shows the root loading state and remounts the providers above this
  // page, which recreates the QueryClient and refetches the entity list.
  useEffect(() => {
    const params = new URLSearchParams();
    if (debouncedSearch) params.set('search', debouncedSearch);
    if (entityTypeFilter !== 'all') params.set('type', entityTypeFilter);
    const queryString = params.toString();
    if (queryString === searchParams.toString()) return;
    const nextURL = queryString ? `${pathname}?${queryString}` : pathname;
    router.replace(nextURL, { scroll: false });
  }, [debouncedSearch, entityTypeFilter, pathname, router, searchParams]);

  // Build query params
  const queryParams: UseEntitiesParams = useMemo(() => ({
    limit: pageSize,
    offset: currentPage * pageSize,
    entity_type: entityTypeFilter !== 'all' ? entityTypeFilter : undefined,
    named_only: namedOnly || undefined,
    search: debouncedSearch || undefined,
  }), [pageSize, currentPage, entityTypeFilter, namedOnly, debouncedSearch]);

  // Fetch entities
  const { data, isLoading, error, refetch } = useEntities(queryParams);

  // Handler functions that reset page when filters change
  const handleEntityTypeChange = (value: string) => {
    setEntityTypeFilter(value as EntityType | 'all');
    setCurrentPage(0);
  };

  const handleNamedOnlyChange = (checked: boolean) => {
    setNamedOnly(checked);
    setCurrentPage(0);
  };

  const handlePageSizeChange = (value: string) => {
    setPageSize(Number(value));
    setCurrentPage(0);
  };

  // Search handler (Story P7-4.2 AC1)
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchInput(e.target.value);
    setCurrentPage(0);
  };

  const handleClearSearch = () => {
    setSearchInput('');
    setCurrentPage(0);
  };

  const handleClearFilters = () => {
    setEntityTypeFilter('all');
    setNamedOnly(false);
    setSearchInput('');
    setCurrentPage(0);
  };

  // Check if we have active filters/search
  const hasFilters = entityTypeFilter !== 'all' || namedOnly || debouncedSearch !== '';

  // Calculate pagination info
  const totalEntities = data?.total ?? 0;
  const totalPages = Math.ceil(totalEntities / pageSize);
  const hasNextPage = currentPage < totalPages - 1;
  const hasPrevPage = currentPage > 0;

  // Calculate showing range
  const showingStart = totalEntities > 0 ? currentPage * pageSize + 1 : 0;
  const showingEnd = Math.min((currentPage + 1) * pageSize, totalEntities);

  if (error) {
    return (
      <div className="bg-destructive/10 text-destructive px-4 py-3 rounded-lg">
        <p className="font-medium">Error loading entities</p>
        <p className="text-sm mt-1">
          {error instanceof Error ? error.message : 'An unexpected error occurred'}
        </p>
        <button
          onClick={() => refetch()}
          className="mt-3 px-3 py-1.5 text-sm border rounded-md hover:bg-destructive/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Search and Filters Row (Story P7-4.2) */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Search Input (Story P7-4.2 AC1) */}
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search by name..."
            value={searchInput}
            onChange={handleSearchChange}
            className="pl-9 pr-9"
            aria-label="Search entities by name"
          />
          {searchInput && (
            <button
              onClick={handleClearSearch}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label="Clear search"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Entity Type Filter */}
        <div className="flex items-center gap-2">
          <Label htmlFor="entity-type-filter" className="text-sm font-medium">
            Type:
          </Label>
          <Select
            value={entityTypeFilter}
            onValueChange={handleEntityTypeChange}
          >
            <SelectTrigger id="entity-type-filter" className="w-[140px]">
              <SelectValue placeholder="All types" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All types</SelectItem>
              <SelectItem value="person">Person</SelectItem>
              <SelectItem value="vehicle">Vehicle</SelectItem>
              <SelectItem value="unknown">Unknown</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Named Only Toggle */}
        <div className="flex items-center gap-2">
          <Switch
            id="named-only"
            checked={namedOnly}
            onCheckedChange={handleNamedOnlyChange}
          />
          <Label htmlFor="named-only" className="text-sm cursor-pointer">
            Named only
          </Label>
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Results count */}
        {!isLoading && (
          <p className="text-sm text-muted-foreground">
            Showing {showingStart}-{showingEnd} of {totalEntities}
          </p>
        )}
      </div>

      {/* Story P9-4.5: Selection/Merge Bar */}
      {selectedEntityIds.size > 0 && (
        <div className="flex items-center justify-between bg-muted/50 border rounded-lg px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium">
              {selectedEntityIds.size} entity{selectedEntityIds.size !== 1 ? 's' : ''} selected
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClearSelection}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4 mr-1" />
              Clear
            </Button>
          </div>
          <Button
            variant="default"
            size="sm"
            disabled={selectedEntityIds.size !== 2}
            onClick={() => {
              if (onMerge && data?.entities && selectedEntityIds.size === 2) {
                const selectedIds = Array.from(selectedEntityIds);
                const entity1 = data.entities.find((e) => e.id === selectedIds[0]);
                const entity2 = data.entities.find((e) => e.id === selectedIds[1]);
                if (entity1 && entity2) {
                  onMerge([entity1, entity2]);
                }
              }
            }}
            className="gap-2"
          >
            <Merge className="h-4 w-4" />
            Merge Entities
          </Button>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <EntityCardSkeleton key={i} />
          ))}
        </div>
      )}

      {/* Empty State (Story P7-4.2 AC2) */}
      {!isLoading && data?.entities.length === 0 && (
        <EmptyEntitiesState
          hasFilters={hasFilters}
          searchQuery={debouncedSearch}
          onClearFilters={handleClearFilters}
        />
      )}

      {/* Entity Grid */}
      {!isLoading && data && data.entities.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {data.entities.map((entity) => (
            <EntityCard
              key={entity.id}
              entity={entity}
              thumbnailUrl={entity.thumbnail_path}
              onClick={() => onEntityClick(entity)}
              selectable={!!onToggleSelection}
              isSelected={selectedEntityIds.has(entity.id)}
              onSelect={onToggleSelection ? () => onToggleSelection(entity) : undefined}
              selectionDisabled={!selectedEntityIds.has(entity.id) && selectedEntityIds.size >= 2}
              onEntityUpdated={() => refetch()}
            />
          ))}
        </div>
      )}

      {/* Pagination Controls */}
      {!isLoading && totalPages > 1 && (
        <div className="flex items-center justify-between border-t pt-4">
          {/* Page Size Selector */}
          <div className="flex items-center gap-2">
            <Label htmlFor="page-size" className="text-sm">
              Per page:
            </Label>
            <Select
              value={String(pageSize)}
              onValueChange={handlePageSizeChange}
            >
              <SelectTrigger id="page-size" className="w-[80px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Page Navigation */}
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
              disabled={!hasPrevPage}
            >
              <ChevronLeft className="h-4 w-4 mr-1" />
              Previous
            </Button>
            <span className="text-sm text-muted-foreground px-2">
              Page {currentPage + 1} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage((p) => p + 1)}
              disabled={!hasNextPage}
            >
              Next
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
