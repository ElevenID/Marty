/**
 * Authentication Context
 *
 * Provides authentication state and methods to the React component tree.
 * Handles user session, user type detection, organization membership, and auth status.
 */

import React, { createContext, useState, useEffect, useCallback, useMemo } from 'react';
import { getCurrentUser, initiateLogin, initiateRegister, initiateLogout } from '../services/authApi';

/**
 * @typedef {Object} User
 * @property {string} user_id - Unique user identifier (OIDC sub)
 * @property {string} email - User email
 * @property {string|null} username - Username
 * @property {string|null} given_name - First name
 * @property {string|null} family_name - Last name
 * @property {string} user_type - 'administrator', 'vendor', or 'applicant'
 * @property {string|null} applicant_id - Linked ApplicantRecord ID (for applicants)
 * @property {string[]} roles - User roles (from Keycloak realm_access.roles)
 * @property {string|null} organization_id - Keycloak Organization ID (for vendors/org members)
 * @property {string|null} organization_name - Organization display name
 * @property {Object|null} organization - Raw organization claim from Keycloak
 */

/**
 * @typedef {Object} AuthContextValue
 * @property {User|null} user - Current authenticated user
 * @property {boolean} isAuthenticated - Whether user is authenticated
 * @property {boolean} isLoading - Whether auth state is loading
 * @property {boolean} isAdministrator - Whether user is a super-administrator
 * @property {boolean} isVendor - Whether user is a vendor (org admin)
 * @property {boolean} isApplicant - Whether user is an applicant
 * @property {string|null} organizationId - Current organization ID
 * @property {string|null} organizationName - Current organization name
 * @property {function} login - Initiate login flow
 * @property {function} register - Initiate registration flow
 * @property {function} logout - Initiate logout flow
 * @property {function} refreshUser - Refresh user info from server
 */

const defaultContextValue = {
  user: null,
  isAuthenticated: false,
  isLoading: true,
  isAdministrator: false,
  isVendor: false,
  isApplicant: false,
  organizationId: null,
  organizationName: null,
  login: () => {},
  register: () => {},
  logout: () => {},
  refreshUser: async () => {},
};

export const AuthContext = createContext(defaultContextValue);

/**
 * Parse organization claim from Keycloak token.
 * Keycloak Organizations feature returns: { "org-id": { "name": "Org Name", ... } }
 * @param {Object|null} orgClaim - Raw organization claim from token
 * @returns {{ id: string|null, name: string|null }}
 */
function parseOrganizationClaim(orgClaim) {
  if (!orgClaim || typeof orgClaim !== 'object') {
    return { id: null, name: null };
  }
  
  // Keycloak returns organization as { "org-id": { "name": "...", ... } }
  const orgIds = Object.keys(orgClaim);
  if (orgIds.length === 0) {
    return { id: null, name: null };
  }
  
  // Use the first organization (user can be member of multiple, but we use primary)
  const orgId = orgIds[0];
  const orgData = orgClaim[orgId];
  
  return {
    id: orgId,
    name: orgData?.name || null,
  };
}

/**
 * Determine user type from roles and claims.
 * Priority: administrator > vendor > applicant
 * @param {string[]} roles - User roles array
 * @param {string|null} userTypeClaim - Explicit user_type claim
 * @returns {string}
 */
function determineUserType(roles, userTypeClaim) {
  // Check explicit claim first
  if (userTypeClaim && ['administrator', 'vendor', 'applicant'].includes(userTypeClaim)) {
    return userTypeClaim;
  }
  
  // Check roles (priority order)
  if (roles?.includes('administrator')) return 'administrator';
  if (roles?.includes('vendor')) return 'vendor';
  if (roles?.includes('applicant')) return 'applicant';
  
  // Default to applicant for self-registered users
  return 'applicant';
}

/**
 * Authentication Provider Component
 *
 * Wraps the application and provides authentication context.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch current user on mount
  const fetchUser = useCallback(async () => {
    try {
      setIsLoading(true);
      const result = await getCurrentUser();

      if (result.authenticated && result.user) {
        // Enrich user object with parsed organization data
        const rawUser = result.user;
        const org = parseOrganizationClaim(rawUser.organization);
        const userType = determineUserType(rawUser.roles, rawUser.user_type);
        
        setUser({
          ...rawUser,
          user_type: userType,
          organization_id: org.id || rawUser.organization_id || null,
          organization_name: org.name || rawUser.organization_name || null,
        });
      } else {
        setUser(null);
      }
    } catch (error) {
      console.error('Error fetching user:', error);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  // Login handler - accepts optional redirect URI string
  // Note: When used as onClick handler, first arg is Event object - we ignore non-string args
  const login = useCallback((redirectUri) => {
    const redirect = typeof redirectUri === 'string' ? redirectUri : window.location.pathname;
    initiateLogin(redirect);
  }, []);

  // Register handler - accepts optional redirect URI string
  // Note: When used as onClick handler, first arg is Event object - we ignore non-string args
  const register = useCallback((redirectUri) => {
    const redirect = typeof redirectUri === 'string' ? redirectUri : window.location.pathname;
    initiateRegister(redirect);
  }, []);

  // Logout handler
  const logout = useCallback(() => {
    initiateLogout();
    setUser(null);
  }, []);

  // Refresh user info
  const refreshUser = useCallback(async () => {
    await fetchUser();
  }, [fetchUser]);

  // Computed values - derive role booleans and organization info
  const contextValue = useMemo(() => {
    const userType = user?.user_type;
    const roles = user?.roles || [];
    
    return {
      user,
      isAuthenticated: !!user,
      isLoading,
      // Role checks - explicit type or role membership
      isAdministrator: userType === 'administrator' || roles.includes('administrator'),
      isVendor: userType === 'vendor' || roles.includes('vendor'),
      isApplicant: userType === 'applicant' || roles.includes('applicant'),
      // Organization info
      organizationId: user?.organization_id || null,
      organizationName: user?.organization_name || null,
      // Actions
      login,
      register,
      logout,
      refreshUser,
    };
  }, [user, isLoading, login, register, logout, refreshUser]);

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}

export default AuthContext;
