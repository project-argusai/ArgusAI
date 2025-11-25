/**
 * Authentication types for frontend
 */

export interface IUser {
  id: string;
  username: string;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}

export interface ILoginRequest {
  username: string;
  password: string;
}

export interface ILoginResponse {
  access_token: string;
  token_type: string;
  user: IUser;
}

export interface IChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface IMessageResponse {
  message: string;
}

export interface ISetupStatusResponse {
  setup_complete: boolean;
  user_count: number;
}
