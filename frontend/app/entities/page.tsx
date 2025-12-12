/**
 * Entities page - displays and manages recognized entities (Story P4-3.6)
 * AC1: Entity list page displays all recognized entities
 * AC13: Empty state with helpful guidance
 * AC15: Responsive design (grid on desktop, stack on mobile)
 */

'use client';

import { useState } from 'react';
import { Users } from 'lucide-react';
import { EntityList } from '@/components/entities/EntityList';
import { EntityDetail } from '@/components/entities/EntityDetail';
import { DeleteEntityDialog } from '@/components/entities/DeleteEntityDialog';
import type { IEntity } from '@/types/entity';

/**
 * Entities page component
 */
export default function EntitiesPage() {
  // Selected entity for detail view
  const [selectedEntity, setSelectedEntity] = useState<IEntity | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);

  // Entity to delete
  const [entityToDelete, setEntityToDelete] = useState<IEntity | null>(null);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);

  /**
   * Handle entity card click - open detail modal
   */
  const handleEntityClick = (entity: IEntity) => {
    setSelectedEntity(entity);
    setIsDetailOpen(true);
  };

  /**
   * Handle delete request from detail modal
   */
  const handleDeleteRequest = (entity: IEntity) => {
    setEntityToDelete(entity);
    setIsDeleteOpen(true);
    // Close detail modal when opening delete dialog
    setIsDetailOpen(false);
  };

  /**
   * Handle successful deletion
   */
  const handleDeleted = () => {
    setSelectedEntity(null);
    setEntityToDelete(null);
  };

  /**
   * Close detail modal
   */
  const handleCloseDetail = () => {
    setIsDetailOpen(false);
    // Keep selectedEntity for a moment for smooth animation
    setTimeout(() => setSelectedEntity(null), 200);
  };

  /**
   * Close delete dialog
   */
  const handleCloseDelete = () => {
    setIsDeleteOpen(false);
    setEntityToDelete(null);
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      {/* Page header */}
      <div className="flex items-center gap-3 mb-8">
        <div className="p-2 bg-primary/10 rounded-lg">
          <Users className="h-6 w-6 text-primary" />
        </div>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Recognized Entities</h1>
          <p className="text-muted-foreground mt-1">
            Manage recurring visitors and vehicles detected by your cameras
          </p>
        </div>
      </div>

      {/* Entity list with filtering and pagination */}
      <EntityList onEntityClick={handleEntityClick} />

      {/* Entity detail modal */}
      <EntityDetail
        entity={selectedEntity}
        open={isDetailOpen}
        onClose={handleCloseDetail}
        onDelete={handleDeleteRequest}
      />

      {/* Delete confirmation dialog */}
      <DeleteEntityDialog
        entity={entityToDelete}
        open={isDeleteOpen}
        onClose={handleCloseDelete}
        onDeleted={handleDeleted}
      />
    </div>
  );
}
