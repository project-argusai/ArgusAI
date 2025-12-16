/**
 * Backup and Restore Component (Story 6.4, FF-007)
 *
 * Features:
 * - Create backup button with progress
 * - Download backup after creation
 * - List available backups
 * - Restore from file upload
 * - Confirmation dialogs for destructive actions
 * - FF-007: Selective backup/restore options
 */

'use client';

import { useState, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import {
  Download,
  Upload,
  Loader2,
  HardDrive,
  Trash2,
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileArchive,
  Database,
  Image,
  Settings,
} from 'lucide-react';

import { apiClient, ApiError } from '@/lib/api-client';
import type { IBackupListItem, IValidationResponse, IBackupOptions, IRestoreOptions } from '@/types/backup';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function BackupRestore() {
  const [isCreatingBackup, setIsCreatingBackup] = useState(false);
  const [isLoadingBackups, setIsLoadingBackups] = useState(false);
  const [backups, setBackups] = useState<IBackupListItem[]>([]);
  const [backupsLoaded, setBackupsLoaded] = useState(false);

  // FF-007: Backup options state
  const [backupOptions, setBackupOptions] = useState<IBackupOptions>({
    include_database: true,
    include_thumbnails: true,
    include_settings: true,
  });

  // Restore state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [validation, setValidation] = useState<IValidationResponse | null>(null);
  const [isRestoring, setIsRestoring] = useState(false);
  const [restoreProgress, setRestoreProgress] = useState(0);

  // FF-007: Restore options state
  const [restoreOptions, setRestoreOptions] = useState<IRestoreOptions>({
    restore_database: true,
    restore_thumbnails: true,
    restore_settings: true,
  });

  // Dialog state
  const [showRestoreConfirm, setShowRestoreConfirm] = useState(false);
  const [deleteBackup, setDeleteBackup] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load backups list
  const loadBackups = useCallback(async () => {
    try {
      setIsLoadingBackups(true);
      const response = await apiClient.backup.list();
      setBackups(response.backups);
      setBackupsLoaded(true);
    } catch (error) {
      console.error('Failed to load backups:', error);
      if (error instanceof ApiError) {
        toast.error(`Failed to load backups: ${error.message}`);
      }
    } finally {
      setIsLoadingBackups(false);
    }
  }, []);

  // Create backup
  const handleCreateBackup = async () => {
    // FF-007: Check that at least one option is selected
    if (!backupOptions.include_database && !backupOptions.include_thumbnails && !backupOptions.include_settings) {
      toast.error('Please select at least one component to backup');
      return;
    }

    try {
      setIsCreatingBackup(true);
      toast.info('Creating backup... This may take a moment.');

      // FF-007: Pass backup options
      const result = await apiClient.backup.create(backupOptions);

      if (result.success) {
        toast.success('Backup created successfully!');

        // Download the backup
        const blob = await apiClient.backup.download(result.timestamp);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `liveobject-backup-${result.timestamp}.zip`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        // Refresh backups list
        loadBackups();
      } else {
        toast.error(`Backup failed: ${result.message}`);
      }
    } catch (error) {
      console.error('Backup failed:', error);
      if (error instanceof ApiError) {
        toast.error(`Backup failed: ${error.message}`);
      } else {
        toast.error('Backup failed. Please try again.');
      }
    } finally {
      setIsCreatingBackup(false);
    }
  };

  // Download existing backup
  const handleDownloadBackup = async (timestamp: string) => {
    try {
      const blob = await apiClient.backup.download(timestamp);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `liveobject-backup-${timestamp}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      toast.success('Backup downloaded');
    } catch (error) {
      console.error('Download failed:', error);
      toast.error('Failed to download backup');
    }
  };

  // Delete backup
  const handleDeleteBackup = async (timestamp: string) => {
    try {
      await apiClient.backup.delete(timestamp);
      toast.success('Backup deleted');
      loadBackups();
    } catch (error) {
      console.error('Delete failed:', error);
      toast.error('Failed to delete backup');
    } finally {
      setDeleteBackup(null);
    }
  };

  // Handle file selection for restore
  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.name.endsWith('.zip')) {
      toast.error('Please select a ZIP file');
      return;
    }

    setSelectedFile(file);
    setValidation(null);

    // Validate the backup
    try {
      setIsValidating(true);
      const result = await apiClient.backup.validate(file);
      setValidation(result);

      if (!result.valid) {
        toast.error(`Invalid backup: ${result.message}`);
      } else if (result.warnings && result.warnings.length > 0) {
        toast.warning('Backup valid with warnings');
      } else {
        toast.success('Backup file validated');
      }
    } catch (error) {
      console.error('Validation failed:', error);
      toast.error('Failed to validate backup file');
      setSelectedFile(null);
    } finally {
      setIsValidating(false);
    }
  };

  // Perform restore
  const handleRestore = async () => {
    if (!selectedFile || !validation?.valid) return;

    // FF-007: Check that at least one option is selected
    if (!restoreOptions.restore_database && !restoreOptions.restore_thumbnails && !restoreOptions.restore_settings) {
      toast.error('Please select at least one component to restore');
      setShowRestoreConfirm(false);
      return;
    }

    try {
      setIsRestoring(true);
      setRestoreProgress(10);
      setShowRestoreConfirm(false);

      toast.info('Restoring from backup... Please wait.');
      setRestoreProgress(30);

      // FF-007: Pass restore options
      const result = await apiClient.backup.restore(selectedFile, restoreOptions);
      setRestoreProgress(90);

      if (result.success) {
        setRestoreProgress(100);
        toast.success(
          `Restore complete! Restored ${result.events_restored} events, ${result.thumbnails_restored} thumbnails.`
        );

        // Clear state
        setSelectedFile(null);
        setValidation(null);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }

        // Reload the page to reflect restored data
        setTimeout(() => {
          window.location.reload();
        }, 2000);
      } else {
        toast.error(`Restore failed: ${result.message}`);
      }
    } catch (error) {
      console.error('Restore failed:', error);
      if (error instanceof ApiError) {
        toast.error(`Restore failed: ${error.message}`);
      } else {
        toast.error('Restore failed. Please try again.');
      }
    } finally {
      setIsRestoring(false);
      setRestoreProgress(0);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HardDrive className="h-5 w-5" aria-hidden="true" />
          Backup & Restore
        </CardTitle>
        <CardDescription>
          Create backups and restore your system data
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Create Backup Section */}
        <div className="space-y-3">
          <h4 className="font-medium">Create Backup</h4>
          <p className="text-sm text-muted-foreground">
            Select which components to include in your backup.
          </p>

          {/* FF-007: Backup options checkboxes */}
          <div className="space-y-3 p-3 rounded-lg border bg-muted/30">
            <div className="flex items-center space-x-3">
              <Checkbox
                id="backup-database"
                checked={backupOptions.include_database}
                onCheckedChange={(checked) =>
                  setBackupOptions((prev) => ({ ...prev, include_database: !!checked }))
                }
              />
              <Label htmlFor="backup-database" className="flex items-center gap-2 text-sm cursor-pointer">
                <Database className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                Database (events, cameras, alert rules)
              </Label>
            </div>
            <div className="flex items-center space-x-3">
              <Checkbox
                id="backup-thumbnails"
                checked={backupOptions.include_thumbnails}
                onCheckedChange={(checked) =>
                  setBackupOptions((prev) => ({ ...prev, include_thumbnails: !!checked }))
                }
              />
              <Label htmlFor="backup-thumbnails" className="flex items-center gap-2 text-sm cursor-pointer">
                <Image className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                Thumbnails (event images)
              </Label>
            </div>
            <div className="flex items-center space-x-3">
              <Checkbox
                id="backup-settings"
                checked={backupOptions.include_settings}
                onCheckedChange={(checked) =>
                  setBackupOptions((prev) => ({ ...prev, include_settings: !!checked }))
                }
              />
              <Label htmlFor="backup-settings" className="flex items-center gap-2 text-sm cursor-pointer">
                <Settings className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                System settings (excluding API keys)
              </Label>
            </div>
          </div>

          <Button
            onClick={handleCreateBackup}
            disabled={isCreatingBackup}
            className="w-full sm:w-auto"
            aria-label="Create backup now"
          >
            {isCreatingBackup ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
                Creating Backup...
              </>
            ) : (
              <>
                <Download className="h-4 w-4 mr-2" aria-hidden="true" />
                Backup Now
              </>
            )}
          </Button>
        </div>

        {/* Available Backups Section */}
        <div className="space-y-3 pt-4 border-t">
          <div className="flex items-center justify-between">
            <h4 className="font-medium">Available Backups</h4>
            <Button
              variant="outline"
              size="sm"
              onClick={loadBackups}
              disabled={isLoadingBackups}
              aria-label="Refresh backup list"
            >
              {isLoadingBackups ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                'Refresh'
              )}
            </Button>
          </div>

          {!backupsLoaded && !isLoadingBackups && (
            <Button variant="outline" onClick={loadBackups} className="w-full">
              Load Backup History
            </Button>
          )}

          {isLoadingBackups && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          )}

          {backupsLoaded && backups.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No backups found
            </p>
          )}

          {backups.length > 0 && (
            <div className="space-y-2">
              {backups.map((backup) => (
                <div
                  key={backup.timestamp}
                  className="flex items-center justify-between p-3 rounded-lg border bg-muted/30"
                >
                  <div className="flex items-center gap-3">
                    <FileArchive className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">
                          {formatDate(backup.created_at)}
                        </span>
                        <Badge variant="secondary" className="text-xs">
                          v{backup.app_version}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span>{formatBytes(backup.size_bytes)}</span>
                        <span>{backup.thumbnails_count} thumbnails</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDownloadBackup(backup.timestamp)}
                      aria-label={`Download backup from ${formatDate(backup.created_at)}`}
                    >
                      <Download className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setDeleteBackup(backup.timestamp)}
                      aria-label={`Delete backup from ${formatDate(backup.created_at)}`}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" aria-hidden="true" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Restore Section */}
        <div className="space-y-3 pt-4 border-t">
          <h4 className="font-medium">Restore from Backup</h4>
          <p className="text-sm text-muted-foreground">
            Upload a backup file to restore your system. This will replace all existing data.
          </p>

          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            onChange={handleFileSelect}
            className="hidden"
            disabled={isRestoring}
          />

          <Button
            variant="outline"
            onClick={() => fileInputRef.current?.click()}
            disabled={isValidating || isRestoring}
            className="w-full"
          >
            {isValidating ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Validating...
              </>
            ) : (
              <>
                <Upload className="h-4 w-4 mr-2" />
                Select Backup File
              </>
            )}
          </Button>

          {/* Selected file and validation status */}
          {selectedFile && (
            <div className="p-3 rounded-lg border space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileArchive className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">{selectedFile.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatBytes(selectedFile.size)}
                    </p>
                  </div>
                </div>
                {validation && (
                  <Badge variant={validation.valid ? 'default' : 'destructive'}>
                    {validation.valid ? (
                      <>
                        <CheckCircle2 className="h-3 w-3 mr-1" />
                        Valid
                      </>
                    ) : (
                      <>
                        <AlertTriangle className="h-3 w-3 mr-1" />
                        Invalid
                      </>
                    )}
                  </Badge>
                )}
              </div>

              {validation?.valid && validation.backup_timestamp && (
                <div className="text-xs text-muted-foreground flex items-center gap-4">
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatDate(validation.backup_timestamp)}
                  </span>
                  <span>Version {validation.app_version}</span>
                </div>
              )}

              {/* FF-007: Show backup contents and restore options */}
              {validation?.valid && validation.contents && (
                <div className="space-y-3 p-3 rounded-lg border bg-muted/30">
                  <p className="text-xs font-medium text-muted-foreground">Select components to restore:</p>
                  <div className="space-y-2">
                    <div className="flex items-center space-x-3">
                      <Checkbox
                        id="restore-database"
                        checked={restoreOptions.restore_database}
                        disabled={!validation.contents.has_database}
                        onCheckedChange={(checked) =>
                          setRestoreOptions((prev) => ({ ...prev, restore_database: !!checked }))
                        }
                      />
                      <Label
                        htmlFor="restore-database"
                        className={`flex items-center gap-2 text-sm cursor-pointer ${
                          !validation.contents.has_database ? 'opacity-50' : ''
                        }`}
                      >
                        <Database className="h-4 w-4 text-muted-foreground" />
                        Database
                        {validation.contents.has_database ? (
                          <span className="text-xs text-muted-foreground">
                            ({formatBytes(validation.contents.database_size_bytes)})
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">(not in backup)</span>
                        )}
                      </Label>
                    </div>
                    <div className="flex items-center space-x-3">
                      <Checkbox
                        id="restore-thumbnails"
                        checked={restoreOptions.restore_thumbnails}
                        disabled={!validation.contents.has_thumbnails}
                        onCheckedChange={(checked) =>
                          setRestoreOptions((prev) => ({ ...prev, restore_thumbnails: !!checked }))
                        }
                      />
                      <Label
                        htmlFor="restore-thumbnails"
                        className={`flex items-center gap-2 text-sm cursor-pointer ${
                          !validation.contents.has_thumbnails ? 'opacity-50' : ''
                        }`}
                      >
                        <Image className="h-4 w-4 text-muted-foreground" />
                        Thumbnails
                        {validation.contents.has_thumbnails ? (
                          <span className="text-xs text-muted-foreground">
                            ({validation.contents.thumbnails_count} images)
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">(not in backup)</span>
                        )}
                      </Label>
                    </div>
                    <div className="flex items-center space-x-3">
                      <Checkbox
                        id="restore-settings"
                        checked={restoreOptions.restore_settings}
                        disabled={!validation.contents.has_settings}
                        onCheckedChange={(checked) =>
                          setRestoreOptions((prev) => ({ ...prev, restore_settings: !!checked }))
                        }
                      />
                      <Label
                        htmlFor="restore-settings"
                        className={`flex items-center gap-2 text-sm cursor-pointer ${
                          !validation.contents.has_settings ? 'opacity-50' : ''
                        }`}
                      >
                        <Settings className="h-4 w-4 text-muted-foreground" />
                        System settings
                        {validation.contents.has_settings ? (
                          <span className="text-xs text-muted-foreground">
                            ({validation.contents.settings_count} settings)
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">(not in backup)</span>
                        )}
                      </Label>
                    </div>
                  </div>
                </div>
              )}

              {validation?.warnings && validation.warnings.length > 0 && (
                <div className="p-2 rounded bg-yellow-50 dark:bg-yellow-950 text-yellow-800 dark:text-yellow-200 text-xs">
                  <p className="font-medium flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" />
                    Warnings:
                  </p>
                  <ul className="list-disc list-inside mt-1">
                    {validation.warnings.map((warning, i) => (
                      <li key={i}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}

              {!validation?.valid && validation?.message && (
                <p className="text-xs text-destructive">{validation.message}</p>
              )}

              {validation?.valid && (
                <Button
                  variant="destructive"
                  onClick={() => setShowRestoreConfirm(true)}
                  disabled={isRestoring}
                  className="w-full"
                >
                  {isRestoring ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Restoring...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4 mr-2" />
                      Restore from This Backup
                    </>
                  )}
                </Button>
              )}

              {isRestoring && (
                <div className="space-y-2">
                  <Progress value={restoreProgress} className="h-2" />
                  <p className="text-xs text-muted-foreground text-center">
                    {restoreProgress < 30
                      ? 'Validating backup...'
                      : restoreProgress < 90
                        ? 'Restoring data...'
                        : 'Finalizing...'}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Restore Confirmation Dialog */}
        <AlertDialog open={showRestoreConfirm} onOpenChange={setShowRestoreConfirm}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-destructive" />
                Confirm Restore
              </AlertDialogTitle>
              <AlertDialogDescription asChild>
                <div className="space-y-3">
                  <p>
                    This will <strong>replace selected data</strong> with the backup contents.
                  </p>
                  {/* FF-007: Show what will be restored */}
                  <div className="text-sm space-y-1">
                    <p className="font-medium">Components to restore:</p>
                    <ul className="list-disc list-inside text-muted-foreground">
                      {restoreOptions.restore_database && <li>Database (events, cameras, alert rules)</li>}
                      {restoreOptions.restore_thumbnails && <li>Thumbnails (event images)</li>}
                      {restoreOptions.restore_settings && <li>System settings</li>}
                    </ul>
                  </div>
                  <p className="font-medium text-destructive">
                    Are you sure you want to continue?
                  </p>
                </div>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleRestore}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                Yes, Restore
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Delete Backup Confirmation Dialog */}
        <AlertDialog open={!!deleteBackup} onOpenChange={(open) => !open && setDeleteBackup(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete Backup?</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently delete this backup file. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => deleteBackup && handleDeleteBackup(deleteBackup)}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  );
}
