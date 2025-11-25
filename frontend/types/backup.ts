/**
 * Backup and Restore Types (Story 6.4)
 */

export interface IBackupResponse {
  success: boolean;
  timestamp: string;
  size_bytes: number;
  download_url: string;
  message: string;
  database_size_bytes: number;
  thumbnails_count: number;
  thumbnails_size_bytes: number;
  settings_count: number;
}

export interface IRestoreResponse {
  success: boolean;
  message: string;
  events_restored: number;
  settings_restored: number;
  thumbnails_restored: number;
  warnings: string[];
}

export interface IBackupListItem {
  timestamp: string;
  size_bytes: number;
  created_at: string;
  app_version: string;
  database_size_bytes: number;
  thumbnails_count: number;
  download_url: string;
}

export interface IBackupListResponse {
  backups: IBackupListItem[];
  total_count: number;
}

export interface IValidationResponse {
  valid: boolean;
  message: string;
  app_version?: string;
  backup_timestamp?: string;
  warnings: string[];
}
