//
//  PairingView.swift
//  ArgusAI
//
//  Created on 12/26/2025.
//

import SwiftUI

struct PairingView: View {
    @Environment(AuthService.self) private var authService
    @State private var viewModel = PairingViewModel()
    
    var body: some View {
        NavigationStack {
            VStack(spacing: 32) {
                // Header
                VStack(spacing: 12) {
                    Image(systemName: "lock.shield.fill")
                        .font(.system(size: 64))
                        .foregroundStyle(.blue.gradient)
                    
                    Text("Welcome to ArgusAI")
                        .font(.largeTitle.bold())
                    
                    Text("Enter your 6-digit pairing code from the ArgusAI web dashboard")
                        .font(.body)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }
                .padding(.top, 60)
                
                // Code Entry
                VStack(spacing: 16) {
                    TextField("000000", text: $viewModel.code)
                        .font(.system(size: 48, weight: .bold, design: .monospaced))
                        .multilineTextAlignment(.center)
                        .keyboardType(.numberPad)
                        .textContentType(.oneTimeCode)
                        .frame(maxWidth: 300)
                        .padding()
                        .background(Color(.systemGray6))
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                    
                    if let error = viewModel.errorMessage {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }
                .padding(.horizontal)
                
                // Pair Button
                Button {
                    Task {
                        await viewModel.verifyCode(authService: authService)
                    }
                } label: {
                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                    } else {
                        Text("Pair Device")
                            .font(.headline)
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!viewModel.isValidCode || viewModel.isLoading)
                .padding(.horizontal, 32)
                
                Spacer()
            }
            .navigationTitle("Pairing")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

#Preview {
    PairingView()
        .environment(AuthService())
        .environment(DiscoveryService())
}
