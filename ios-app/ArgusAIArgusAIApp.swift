//
//  ArgusAIApp.swift
//  ArgusAI
//
//  Created on 12/26/2025.
//

import SwiftUI

@main
struct ArgusAIApp: App {
    @State private var authService = AuthService()
    @State private var discoveryService = DiscoveryService()
    
    init() {
        // Only register for push on real devices
        #if !targetEnvironment(simulator)
        registerForPushNotifications()
        #else
        print("📱 Running in Simulator - Push notifications disabled")
        #endif
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(authService)
                .environment(discoveryService)
        }
    }
    
    private func registerForPushNotifications() {
        Task {
            do {
                try await UNUserNotificationCenter.current().requestAuthorization(
                    options: [.alert, .sound, .badge]
                )
                await MainActor.run {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            } catch {
                print("⚠️ Failed to register for notifications: \(error)")
            }
        }
    }
}
