'use client';

/**
 * Alert Rules page - Epic 5, Story 5.2
 * Manage alert rules and notifications
 */

import { useState } from 'react';
import type { IAlertRule } from '@/types/alert-rule';
import { RulesList } from '@/components/rules/RulesList';
import { RuleFormDialog } from '@/components/rules/RuleFormDialog';
import { DeleteRuleDialog } from '@/components/rules/DeleteRuleDialog';

export default function RulesPage() {
  // Modal states
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<IAlertRule | null>(null);
  const [deletingRule, setDeletingRule] = useState<IAlertRule | null>(null);

  const handleCreateRule = () => {
    setEditingRule(null);
    setIsFormOpen(true);
  };

  const handleEditRule = (rule: IAlertRule) => {
    setEditingRule(rule);
    setIsFormOpen(true);
  };

  const handleDeleteRule = (rule: IAlertRule) => {
    setDeletingRule(rule);
  };

  const handleFormClose = () => {
    setIsFormOpen(false);
    setEditingRule(null);
  };

  const handleDeleteClose = () => {
    setDeletingRule(null);
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Alert Rules</h1>
        <p className="text-muted-foreground mt-2">
          Configure rules to receive notifications for specific events
        </p>
      </div>

      <RulesList
        onCreateRule={handleCreateRule}
        onEditRule={handleEditRule}
        onDeleteRule={handleDeleteRule}
      />

      {/* Create/Edit Rule Dialog */}
      <RuleFormDialog
        open={isFormOpen}
        onOpenChange={setIsFormOpen}
        rule={editingRule}
        onClose={handleFormClose}
      />

      {/* Delete Confirmation Dialog */}
      <DeleteRuleDialog
        rule={deletingRule}
        onClose={handleDeleteClose}
      />
    </div>
  );
}
