/**
 * Authentication types for frontend (Story P15-2)
 */

export type UserRole = 'admin' | 'operator' | 'viewer';

export interface IUser {
  id: string;
  username: string;
  email: string | null;
  role: UserRole;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
  last_login: string | null;
}

export interface ILoginRequest {
  username: string;
  password: string;
}

export interface ILoginResponse {
  access_token: string;
  refresh_token?: string; // Phase A - Web Refresh Tokens
  token_type: string;
  user: IUser;
  must_change_password: boolean;
}

export interface IChangePasswordRequest {
  current_password?: string;  // Optional for forced password changes
  new_password: string;
}

export interface IMessageResponse {
  message: string;
}

export interface ISetupStatusResponse {
  setup_complete: boolean;
  user_count: number;
}

// User Management Types (Story P15-2.3)
export interface IUserCreate {
  username: string;
  email?: string;
  role: UserRole;
  send_email?: boolean;
}

export interface IUserCreateResponse {
  id: string;
  username: string;
  email: string | null;
  role: UserRole;
  temporary_password: string | null;
  password_expires_at: string | null;
  created_at: string;
  email_sent?: boolean;  // Story P16-1.7: Whether invitation email was sent
}

export interface IUserUpdate {
  email?: string;
  role?: UserRole;
  is_active?: boolean;
}

export interface IPasswordResetResponse {
  temporary_password: string;
  expires_at: string;
}

// Session Management Types (Story P15-2.7)
export interface ISession {
  id: string;
  device_info: string | null;
  ip_address: string | null;
  created_at: string;
  last_active_at: string;
  is_current: boolean;
}

export interface ISessionRevokeResponse {
  revoked_count: number;
}
