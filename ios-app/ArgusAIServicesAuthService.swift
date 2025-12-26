//
//  AuthService.swift
//  ArgusAI
//
//  Created on 12/26/2025.
//

import Foundation
import Observation

@Observable
final class AuthService {
    var isAuthenticated: Bool = false
    var accessToken: String?
    var refreshToken: String?
    
    private let keychainService = KeychainService()
    
    init() {
        // Check if we have stored credentials
        loadStoredCredentials()
    }
    
    func verifyPairingCode(_ code: String, deviceID: String) async throws {
        // TODO: Implement actual API call
        // For now, simulate success
        try await Task.sleep(for: .seconds(1))
        
        // Simulate tokens
        accessToken = "mock_access_token"
        refreshToken = "mock_refresh_token"
        
        // Store in keychain
        try keychainService.saveAccessToken(accessToken!)
        try keychainService.saveRefreshToken(refreshToken!)
        
        isAuthenticated = true
    }
    
    func logout() {
        isAuthenticated = false
        accessToken = nil
        refreshToken = nil
        
        try? keychainService.deleteAccessToken()
        try? keychainService.deleteRefreshToken()
    }
    
    private func loadStoredCredentials() {
        accessToken = try? keychainService.getAccessToken()
        refreshToken = try? keychainService.getRefreshToken()
        isAuthenticated = accessToken != nil
    }
}
