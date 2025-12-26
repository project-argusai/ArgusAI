//
//  ContentView.swift
//  ArgusAI
//
//  Created on 12/26/2025.
//

import SwiftUI

struct ContentView: View {
    @Environment(AuthService.self) private var authService
    
    var body: some View {
        Group {
            if authService.isAuthenticated {
                EventListView()
            } else {
                PairingView()
            }
        }
    }
}

#Preview {
    ContentView()
        .environment(AuthService())
        .environment(DiscoveryService())
}
