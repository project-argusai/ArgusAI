/**
 * Authentication context for managing user auth state (Story 6.3, AC: #9)
 *
 * Features:
 * - Real API authentication with backend
 * - User session management via localStorage token + HTTP-only cookies
 * - Auto-check authentication on mount
 * - Login/logout functionality
 */

'use client';

import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { apiClient, ApiError, setAuthToken, clearAuthToken } from '@/lib/api-client';

export interface User {
  id: string;
  username: string;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Check authentication status on mount
  const checkAuth = useCallback(async () => {
    try {
      const currentUser = await apiClient.auth.getCurrentUser();
      setUser(currentUser);
    } catch (error) {
      // Not authenticated - clear user
      setUser(null);
      // Only log non-401 errors (401 is expected when not logged in)
      if (error instanceof ApiError && error.statusCode !== 401) {
        console.error('Auth check failed:', error);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Check auth on mount
  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = useCallback(async (username: string, password: string) => {
    setIsLoading(true);
    try {
      const response = await apiClient.auth.login({ username, password });
      // Store token for Authorization header (backup for cookie issues)
      if (response.access_token) {
        setAuthToken(response.access_token);
      }
      setUser(response.user);
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setIsLoading(true);
    try {
      await apiClient.auth.logout();
      clearAuthToken();
      setUser(null);
    } catch (error) {
      console.error('Logout failed:', error);
      // Still clear user/token on client side even if backend fails
      clearAuthToken();
      setUser(null);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
        checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
