//
//  EventListView.swift
//  ArgusAI
//
//  Created on 12/26/2025.
//

import SwiftUI

struct EventListView: View {
    @Environment(AuthService.self) private var authService
    @State private var viewModel = EventListViewModel()
    
    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading {
                    ProgressView("Loading events...")
                } else if viewModel.events.isEmpty {
                    ContentUnavailableView(
                        "No Events",
                        systemImage: "video.slash",
                        description: Text("Security events will appear here when detected")
                    )
                } else {
                    List(viewModel.events) { event in
                        NavigationLink(value: event) {
                            EventRow(event: event)
                        }
                    }
                    .refreshable {
                        await viewModel.loadEvents(authService: authService)
                    }
                }
            }
            .navigationTitle("Security Events")
            .navigationDestination(for: EventSummary.self) { event in
                EventDetailView(eventID: event.id)
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button(role: .destructive) {
                            authService.logout()
                        } label: {
                            Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
            .task {
                await viewModel.loadEvents(authService: authService)
            }
        }
    }
}

struct EventRow: View {
    let event: EventSummary
    
    var body: some View {
        HStack(spacing: 12) {
            // Thumbnail placeholder
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(.systemGray5))
                .frame(width: 80, height: 60)
                .overlay {
                    Image(systemName: "photo")
                        .foregroundStyle(.secondary)
                }
            
            VStack(alignment: .leading, spacing: 4) {
                Text(event.description)
                    .font(.body)
                    .lineLimit(2)
                
                HStack {
                    Text(event.cameraName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    
                    Text("•")
                        .foregroundStyle(.secondary)
                    
                    Text(event.timestamp, style: .relative)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

#Preview {
    EventListView()
        .environment(AuthService())
        .environment(DiscoveryService())
}
