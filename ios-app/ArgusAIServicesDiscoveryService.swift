//
//  DiscoveryService.swift
//  ArgusAI
//
//  Created on 12/26/2025.
//

import Foundation
import Observation

@Observable
final class DiscoveryService {
    var localDeviceURL: URL?
    var cloudRelayURL: URL? = URL(string: "https://your-argusai-instance.example.com")
    
    var baseURL: URL? {
        // Prefer local, fallback to cloud
        localDeviceURL ?? cloudRelayURL
    }
    
    // TODO: Implement Bonjour discovery
    func startDiscovery() {
        // Placeholder for _argusai._tcp.local discovery
    }
    
    func stopDiscovery() {
        // Placeholder
    }
}
