//
//  EventListViewModel.swift
//  ArgusAI
//
//  Created on 12/26/2025.
//

import Foundation
import Observation

@Observable
final class EventListViewModel {
    var events: [EventSummary] = []
    var isLoading: Bool = false
    var errorMessage: String?
    
    func loadEvents(authService: AuthService) async {
        isLoading = true
        errorMessage = nil
        
        do {
            // TODO: Implement actual API call
            // For now, simulate loading with mock data
            try await Task.sleep(for: .seconds(1))
            
            events = [
                EventSummary(
                    id: "1",
                    description: "Person detected at front door",
                    cameraName: "Front Door",
                    timestamp: Date().addingTimeInterval(-300)
                ),
                EventSummary(
                    id: "2",
                    description: "Motion detected in backyard",
                    cameraName: "Backyard",
                    timestamp: Date().addingTimeInterval(-3600)
                ),
                EventSummary(
                    id: "3",
                    description: "Package delivery detected",
                    cameraName: "Front Porch",
                    timestamp: Date().addingTimeInterval(-7200)
                )
            ]
        } catch {
            errorMessage = error.localizedDescription
        }
        
        isLoading = false
    }
}

// MARK: - Models

struct EventSummary: Identifiable, Hashable {
    let id: String
    let description: String
    let cameraName: String
    let timestamp: Date
}
