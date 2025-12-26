//
//  PairingViewModel.swift
//  ArgusAI
//
//  Created on 12/26/2025.
//

import Foundation
import Observation

@Observable
final class PairingViewModel {
    var code: String = ""
    var isLoading: Bool = false
    var errorMessage: String?
    
    var isValidCode: Bool {
        code.count == 6 && code.allSatisfy(\.isNumber)
    }
    
    func verifyCode(authService: AuthService) async {
        guard isValidCode else {
            errorMessage = "Please enter a valid 6-digit code"
            return
        }
        
        isLoading = true
        errorMessage = nil
        
        do {
            let deviceID = UIDevice.current.identifierForVendor?.uuidString ?? UUID().uuidString
            try await authService.verifyPairingCode(code, deviceID: deviceID)
            // Success - AuthService will update isAuthenticated
        } catch {
            errorMessage = "Failed to verify code: \(error.localizedDescription)"
        }
        
        isLoading = false
    }
}
