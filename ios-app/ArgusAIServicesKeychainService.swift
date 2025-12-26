//
//  KeychainService.swift
//  ArgusAI
//
//  Created on 12/26/2025.
//

import Foundation
import Security

final class KeychainService {
    private let service = "com.argusai.app"
    
    enum KeychainError: Error {
        case itemNotFound
        case duplicateItem
        case invalidData
        case unexpectedStatus(OSStatus)
    }
    
    // MARK: - Access Token
    
    func saveAccessToken(_ token: String) throws {
        try save(token, forKey: "accessToken")
    }
    
    func getAccessToken() throws -> String {
        try get(forKey: "accessToken")
    }
    
    func deleteAccessToken() throws {
        try delete(forKey: "accessToken")
    }
    
    // MARK: - Refresh Token
    
    func saveRefreshToken(_ token: String) throws {
        try save(token, forKey: "refreshToken")
    }
    
    func getRefreshToken() throws -> String {
        try get(forKey: "refreshToken")
    }
    
    func deleteRefreshToken() throws {
        try delete(forKey: "refreshToken")
    }
    
    // MARK: - Private Helpers
    
    private func save(_ value: String, forKey key: String) throws {
        guard let data = value.data(using: .utf8) else {
            throw KeychainError.invalidData
        }
        
        // Delete existing item if any
        try? delete(forKey: key)
        
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data
        ]
        
        let status = SecItemAdd(query as CFDictionary, nil)
        
        guard status == errSecSuccess else {
            throw KeychainError.unexpectedStatus(status)
        }
    }
    
    private func get(forKey key: String) throws -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        
        guard status == errSecSuccess else {
            throw KeychainError.itemNotFound
        }
        
        guard let data = result as? Data,
              let string = String(data: data, encoding: .utf8) else {
            throw KeychainError.invalidData
        }
        
        return string
    }
    
    private func delete(forKey key: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]
        
        let status = SecItemDelete(query as CFDictionary)
        
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainError.unexpectedStatus(status)
        }
    }
}
