//
//  EventDetailView.swift
//  ArgusAI
//
//  Created on 12/26/2025.
//

import SwiftUI

struct EventDetailView: View {
    let eventID: String
    
    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Thumbnail placeholder
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.systemGray5))
                    .aspectRatio(16/9, contentMode: .fit)
                    .overlay {
                        Image(systemName: "photo")
                            .font(.system(size: 48))
                            .foregroundStyle(.secondary)
                    }
                
                VStack(alignment: .leading, spacing: 16) {
                    Text("Person detected at front door")
                        .font(.title2.bold())
                    
                    HStack {
                        Label("Front Door", systemImage: "video.fill")
                        Spacer()
                        Text(Date(), style: .relative)
                            .foregroundStyle(.secondary)
                    }
                    .font(.subheadline)
                    
                    Divider()
                    
                    Text("Event Details")
                        .font(.headline)
                    
                    Text("This is a placeholder for event details. In the full implementation, this would show AI-generated descriptions, confidence scores, and other metadata.")
                        .font(.body)
                        .foregroundStyle(.secondary)
                }
                .padding()
            }
            .padding()
        }
        .navigationTitle("Event Detail")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    NavigationStack {
        EventDetailView(eventID: "1")
    }
}
