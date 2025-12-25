# Mobile Authentication Flow

**Version:** 1.0.0
**Last Updated:** 2025-12-25
**Story:** P10-5.2

This document describes authentication flows for mobile clients (iOS, iPadOS, watchOS, tvOS) connecting to ArgusAI.

---

## Table of Contents

1. [Overview](#overview)
2. [JWT Token Authentication](#jwt-token-authentication)
3. [Token Refresh Strategy](#token-refresh-strategy)
4. [Device Registration](#device-registration)
5. [Push Notification Token Management](#push-notification-token-management)
6. [Biometric Authentication](#biometric-authentication)
7. [Secure Token Storage](#secure-token-storage)
8. [Sequence Diagrams](#sequence-diagrams)
9. [Error Handling](#error-handling)
10. [Security Best Practices](#security-best-practices)

---

## Overview

ArgusAI uses **JWT (JSON Web Token)** authentication for all API access. Mobile clients authenticate differently from web clients:

| Aspect | Web Client | Mobile Client |
|--------|------------|---------------|
| Token Storage | HTTP-only cookie | iOS Keychain / Android Keystore |
| Token Transmission | Cookie (automatic) | Authorization header (explicit) |
| Token Refresh | On page load | Background refresh before expiry |
| Session Persistence | Browser session | Keychain persistence |

### Authentication Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/login` | POST | Authenticate with username/password |
| `/api/v1/auth/logout` | POST | End session (clears server-side cookie) |
| `/api/v1/auth/me` | GET | Get current user info |
| `/api/v1/auth/change-password` | POST | Change user password |
| `/api/v1/auth/setup-status` | GET | Check if initial setup is complete |

---

## JWT Token Authentication

### Login Flow

**Endpoint:** `POST /api/v1/auth/login`

**Request:**
```json
{
  "username": "admin",
  "password": "YourSecurePassword123!"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "admin",
    "is_active": true,
    "created_at": "2025-12-01T10:00:00Z",
    "last_login": "2025-12-25T08:30:00Z"
  }
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid credentials
- `429 Too Many Requests` - Rate limit exceeded (5 attempts per 15 minutes)

### Using the Token

Mobile clients **MUST** use the `Authorization` header for all authenticated requests:

```http
GET /api/v1/events HTTP/1.1
Host: argusai.local
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Swift Example:**
```swift
var request = URLRequest(url: URL(string: "https://argusai.local/api/v1/events")!)
request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
```

### Token Structure

The JWT payload contains:

```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",  // User ID
  "username": "admin",
  "exp": 1735135200,  // Expiration (Unix timestamp)
  "iat": 1735048800   // Issued at (Unix timestamp)
}
```

### Token Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `JWT_EXPIRATION_HOURS` | 24 | Token lifetime in hours |
| `JWT_ALGORITHM` | HS256 | Signing algorithm |
| `JWT_SECRET_KEY` | Auto-generated | Signing secret |

---

## Token Refresh Strategy

### Current Implementation

ArgusAI **does not currently implement** a dedicated refresh token endpoint. Mobile clients should handle token expiration by:

1. **Proactive Refresh:** Re-authenticate before token expires
2. **Reactive Refresh:** Catch 401 errors and re-authenticate

### Recommended Mobile Implementation

```mermaid
sequenceDiagram
    participant App
    participant TokenManager
    participant API
    participant Keychain

    App->>TokenManager: checkTokenValidity()
    TokenManager->>Keychain: getTokenExpiration()
    Keychain-->>TokenManager: exp: 1735135200

    alt Token expires within 1 hour
        TokenManager->>Keychain: getCredentials()
        Keychain-->>TokenManager: {username, password}
        TokenManager->>API: POST /auth/login
        API-->>TokenManager: {access_token, ...}
        TokenManager->>Keychain: storeToken(access_token)
    end

    TokenManager-->>App: tokenValid: true
```

### Token Refresh Timing

| Scenario | Action |
|----------|--------|
| Token valid > 1 hour | Continue using token |
| Token expires < 1 hour | Proactively refresh |
| Token expired | Immediate re-authentication |
| 401 response received | Re-authenticate and retry |

### Swift Implementation Pattern

```swift
class TokenManager {
    private let keychain = KeychainManager.shared
    private let refreshThreshold: TimeInterval = 3600 // 1 hour

    func ensureValidToken() async throws -> String {
        guard let tokenData = keychain.getTokenData() else {
            throw AuthError.notAuthenticated
        }

        let expiresAt = tokenData.expiresAt
        let now = Date()

        // Refresh if expiring within threshold
        if expiresAt.timeIntervalSince(now) < refreshThreshold {
            return try await refreshToken()
        }

        return tokenData.accessToken
    }

    private func refreshToken() async throws -> String {
        guard let credentials = keychain.getCredentials() else {
            throw AuthError.credentialsNotFound
        }

        let response = try await authService.login(
            username: credentials.username,
            password: credentials.password
        )

        keychain.storeToken(response.accessToken, expiresIn: 24 * 3600)
        return response.accessToken
    }
}
```

### Future Enhancement: Refresh Token (Planned)

A dedicated refresh token mechanism is planned for future implementation:

```
POST /api/v1/auth/refresh
Authorization: Bearer <expired_access_token>
X-Refresh-Token: <refresh_token>

Response: {
  "access_token": "new_jwt...",
  "refresh_token": "new_refresh...",
  "expires_in": 86400
}
```

---

## Device Registration

### Purpose

Device registration enables:
- Per-device session management
- Push notification targeting
- Device-specific settings
- Remote session revocation

### Device Registration Flow

```mermaid
sequenceDiagram
    participant App
    participant Device
    participant API
    participant DB

    App->>Device: generateDeviceId()
    Device-->>App: UUID (persistent)

    App->>API: POST /auth/login
    Note right of API: Include X-Device-Id header
    API-->>App: {access_token, user}

    App->>API: POST /push/subscribe
    Note right of API: Links push token to device
    API-->>App: {subscription_id}

    API->>DB: Store device info
```

### Device Identification

Each device should generate a unique, persistent identifier:

**iOS Implementation:**
```swift
import UIKit

class DeviceIdentifier {
    static var id: String {
        // Use identifierForVendor (persists until app uninstall)
        if let vendorId = UIDevice.current.identifierForVendor?.uuidString {
            return vendorId
        }

        // Fallback: Generate and store in Keychain
        if let stored = KeychainManager.shared.getString(forKey: "device_id") {
            return stored
        }

        let newId = UUID().uuidString
        KeychainManager.shared.set(newId, forKey: "device_id")
        return newId
    }
}
```

### Device Headers

Include device information in all API requests:

```http
POST /api/v1/auth/login HTTP/1.1
Content-Type: application/json
X-Device-Id: 550e8400-e29b-41d4-a716-446655440000
X-Device-Platform: iOS
X-Device-Model: iPhone15,3
X-App-Version: 1.0.0

{...}
```

### Device Management (Future)

Planned endpoints for device management:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/devices` | GET | List registered devices |
| `/api/v1/devices/{id}` | GET | Get device details |
| `/api/v1/devices/{id}` | DELETE | Revoke device access |
| `/api/v1/devices/{id}/rename` | PUT | Rename device |

---

## Push Notification Token Management

### Overview

ArgusAI uses **Web Push** with VAPID keys for push notifications. Mobile apps require platform-specific integration:

| Platform | Service | Registration |
|----------|---------|--------------|
| iOS | APNS (Apple Push Notification Service) | UIApplication.registerForRemoteNotifications |
| Android | FCM (Firebase Cloud Messaging) | FirebaseMessaging.getInstance().token |

### APNS Registration Flow (iOS)

```mermaid
sequenceDiagram
    participant App
    participant iOS
    participant APNS
    participant ArgusAPI
    participant DB

    App->>iOS: registerForRemoteNotifications()
    iOS->>APNS: Request device token
    APNS-->>iOS: Device token (Data)
    iOS-->>App: didRegisterForRemoteNotifications(token)

    App->>App: Convert token to hex string
    App->>ArgusAPI: POST /push/subscribe
    Note right of ArgusAPI: {endpoint, keys}
    ArgusAPI->>DB: Store subscription
    ArgusAPI-->>App: {subscription_id}
```

### Subscription Request

**Endpoint:** `POST /api/v1/push/subscribe`

**Request:**
```json
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/abc123...",
  "keys": {
    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_...",
    "auth": "tBHItJI5svbpez7KI4CCXg=="
  },
  "user_agent": "ArgusAI-iOS/1.0.0 (iPhone15,3; iOS 18.0)"
}
```

**Response (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "endpoint": "https://fcm.googleapis.com/...xyz",
  "created_at": "2025-12-25T10:30:00Z"
}
```

### VAPID Public Key

**Endpoint:** `GET /api/v1/push/vapid-public-key`

**Response:**
```json
{
  "public_key": "BEl62iUYgUivxIkv69yViEuiBIa-..."
}
```

### iOS Swift Implementation

```swift
import UserNotifications

class PushNotificationManager: NSObject, UNUserNotificationCenterDelegate {
    static let shared = PushNotificationManager()

    func requestAuthorization() async throws -> Bool {
        let center = UNUserNotificationCenter.current()
        let options: UNAuthorizationOptions = [.alert, .sound, .badge]
        return try await center.requestAuthorization(options: options)
    }

    func registerForPushNotifications() {
        Task {
            let granted = try await requestAuthorization()
            guard granted else { return }

            await MainActor.run {
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }

    func handleDeviceToken(_ deviceToken: Data) async {
        let tokenString = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()

        do {
            let vapidKey = try await api.getVapidPublicKey()

            // For APNS, create a subscription-like structure
            try await api.subscribe(
                endpoint: "apns://\(tokenString)",
                keys: generateKeys(vapidPublicKey: vapidKey)
            )
        } catch {
            print("Push registration failed: \(error)")
        }
    }
}

// In AppDelegate
func application(_ application: UIApplication,
                 didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
    Task {
        await PushNotificationManager.shared.handleDeviceToken(deviceToken)
    }
}
```

### Token Refresh Handling

Push tokens can change. Handle refresh:

```swift
// iOS: Token changes are delivered to the same delegate method
func application(_ application: UIApplication,
                 didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
    // Always re-register - the API handles upsert
    Task {
        await PushNotificationManager.shared.handleDeviceToken(deviceToken)
    }
}
```

### Notification Preferences

**Get Preferences:** `POST /api/v1/push/preferences`
```json
{
  "endpoint": "apns://abc123..."
}
```

**Update Preferences:** `PUT /api/v1/push/preferences`
```json
{
  "endpoint": "apns://abc123...",
  "enabled_cameras": ["cam-uuid-1", "cam-uuid-2"],
  "enabled_object_types": ["person", "vehicle"],
  "quiet_hours_enabled": true,
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "07:00",
  "timezone": "America/New_York",
  "sound_enabled": true
}
```

---

## Biometric Authentication

### Overview

Biometric authentication (Face ID, Touch ID) provides a seamless login experience after initial authentication. **Credentials are stored securely in Keychain** and protected by biometric access control.

### Implementation Pattern

```mermaid
sequenceDiagram
    participant User
    participant App
    participant LAContext
    participant Keychain
    participant API

    User->>App: Open app
    App->>Keychain: Check biometric credentials

    alt Biometric credentials exist
        App->>LAContext: evaluatePolicy(.biometry)
        LAContext->>User: Face ID / Touch ID prompt
        User-->>LAContext: Authenticate
        LAContext-->>App: Success
        App->>Keychain: getCredentials() [biometric protected]
        Keychain-->>App: {username, password}
        App->>API: POST /auth/login
        API-->>App: {access_token, user}
    else No biometric credentials
        App->>User: Show login form
    end
```

### Storing Credentials for Biometric

```swift
import LocalAuthentication
import Security

class BiometricAuthManager {
    private let account = "com.argusai.credentials"

    /// Store credentials protected by biometric
    func storeCredentials(username: String, password: String) throws {
        let credentials = "\(username):\(password)".data(using: .utf8)!

        // Create access control requiring biometric authentication
        var error: Unmanaged<CFError>?
        guard let accessControl = SecAccessControlCreateWithFlags(
            nil,
            kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly,
            .biometryCurrentSet,
            &error
        ) else {
            throw BiometricError.accessControlCreationFailed
        }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: account,
            kSecValueData as String: credentials,
            kSecAttrAccessControl as String: accessControl
        ]

        // Delete existing and add new
        SecItemDelete(query as CFDictionary)
        let status = SecItemAdd(query as CFDictionary, nil)

        guard status == errSecSuccess else {
            throw BiometricError.storageFailed(status)
        }
    }

    /// Retrieve credentials with biometric authentication
    func getCredentials() async throws -> (username: String, password: String) {
        let context = LAContext()
        context.localizedReason = "Authenticate to access ArgusAI"

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecUseAuthenticationContext as String: context
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        guard status == errSecSuccess,
              let data = result as? Data,
              let credentialString = String(data: data, encoding: .utf8) else {
            throw BiometricError.retrievalFailed(status)
        }

        let parts = credentialString.split(separator: ":")
        guard parts.count == 2 else {
            throw BiometricError.invalidCredentialFormat
        }

        return (String(parts[0]), String(parts[1]))
    }

    /// Check if biometric authentication is available
    func isBiometricAvailable() -> Bool {
        let context = LAContext()
        var error: NSError?
        return context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error)
    }

    /// Clear stored credentials
    func clearCredentials() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}
```

### Biometric Flow Integration

```swift
class AuthenticationCoordinator {
    private let biometric = BiometricAuthManager()
    private let api = APIClient.shared
    private let tokenManager = TokenManager.shared

    func authenticateOnLaunch() async throws {
        // Try biometric first
        if biometric.isBiometricAvailable() {
            do {
                let credentials = try await biometric.getCredentials()
                let response = try await api.login(
                    username: credentials.username,
                    password: credentials.password
                )
                tokenManager.storeToken(response.accessToken)
                return
            } catch {
                // Biometric failed, fall through to manual login
            }
        }

        // Manual login required
        throw AuthError.manualLoginRequired
    }

    /// Called after successful manual login
    func offerBiometricSetup(username: String, password: String) async {
        guard biometric.isBiometricAvailable() else { return }

        // Show UI prompt asking if user wants to enable biometric login
        let userAccepted = await showBiometricSetupPrompt()

        if userAccepted {
            try? biometric.storeCredentials(username: username, password: password)
        }
    }
}
```

### Security Considerations

1. **Never store plain text credentials** - Always use Keychain with biometric access control
2. **Use `.biometryCurrentSet`** - Invalidates credentials if biometric enrollment changes
3. **Provide password fallback** - Allow manual entry if biometric fails
4. **Clear on logout** - Remove credentials when user explicitly logs out

---

## Secure Token Storage

### iOS Keychain

The iOS Keychain is the **only recommended** storage for sensitive data:

```swift
import Security

class KeychainManager {
    static let shared = KeychainManager()
    private let service = "com.argusai.app"

    enum KeychainKey: String {
        case accessToken = "access_token"
        case tokenExpiration = "token_exp"
        case deviceId = "device_id"
        case pushToken = "push_token"
    }

    func set(_ value: String, forKey key: KeychainKey) {
        guard let data = value.data(using: .utf8) else { return }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]

        SecItemDelete(query as CFDictionary)
        SecItemAdd(query as CFDictionary, nil)
    }

    func getString(forKey key: KeychainKey) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue,
            kSecReturnData as String: true
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        guard status == errSecSuccess,
              let data = result as? Data,
              let string = String(data: data, encoding: .utf8) else {
            return nil
        }

        return string
    }

    func delete(forKey key: KeychainKey) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue
        ]
        SecItemDelete(query as CFDictionary)
    }
}
```

### Storage Accessibility Levels

| Level | Use Case |
|-------|----------|
| `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` | Access token (needs background access) |
| `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` | Sensitive user data |
| `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` + Biometry | Password storage for biometric |

### What NOT to Store

**Never store tokens or credentials in:**
- UserDefaults
- Core Data (unencrypted)
- Plain files
- NSCache

---

## Sequence Diagrams

### Complete Login Flow

```mermaid
sequenceDiagram
    participant User
    participant App
    participant Keychain
    participant API

    User->>App: Launch app
    App->>Keychain: getToken()

    alt Token exists and valid
        Keychain-->>App: accessToken
        App->>API: GET /auth/me
        API-->>App: 200 {user}
        App->>User: Show dashboard
    else Token expired
        Keychain-->>App: accessToken (expired)
        App->>Keychain: getCredentials()
        Keychain-->>App: {username, password}
        App->>API: POST /auth/login
        API-->>App: 200 {access_token, user}
        App->>Keychain: storeToken()
        App->>User: Show dashboard
    else No token
        Keychain-->>App: nil
        App->>User: Show login screen
    end
```

### Token Refresh Flow

```mermaid
sequenceDiagram
    participant App
    participant TokenManager
    participant Keychain
    participant API

    App->>TokenManager: ensureValidToken()
    TokenManager->>Keychain: getTokenExpiration()
    Keychain-->>TokenManager: exp timestamp

    alt Expires within 1 hour
        TokenManager->>Keychain: getCredentials()
        alt Has biometric credentials
            Keychain-->>TokenManager: {username, password}
            TokenManager->>API: POST /auth/login
            API-->>TokenManager: 200 {access_token}
            TokenManager->>Keychain: storeToken()
            TokenManager-->>App: newToken
        else No credentials
            TokenManager-->>App: error: reauth required
        end
    else Token still valid
        TokenManager->>Keychain: getToken()
        Keychain-->>TokenManager: accessToken
        TokenManager-->>App: existingToken
    end
```

### Push Registration Flow

```mermaid
sequenceDiagram
    participant App
    participant iOS
    participant APNS
    participant API
    participant DB

    App->>iOS: requestAuthorization()
    iOS->>User: Permission prompt
    User-->>iOS: Allow
    iOS-->>App: granted: true

    App->>iOS: registerForRemoteNotifications()
    iOS->>APNS: Register device
    APNS-->>iOS: deviceToken
    iOS-->>App: didRegister(token)

    App->>API: GET /push/vapid-public-key
    API-->>App: {public_key}

    App->>API: POST /push/subscribe
    Note right of App: {endpoint, keys, user_agent}
    API->>DB: Upsert subscription
    API-->>App: {subscription_id}

    App->>Keychain: storePushToken()
```

### Biometric Authentication Flow

```mermaid
sequenceDiagram
    participant User
    participant App
    participant LAContext
    participant Keychain
    participant API

    User->>App: Open app
    App->>App: Check biometric availability

    alt Biometric available
        App->>LAContext: evaluatePolicy(.biometry)
        LAContext->>User: Face ID prompt
        User-->>LAContext: Authenticate
        LAContext-->>App: Success

        App->>Keychain: getCredentials()
        Note right of Keychain: Protected by biometric
        Keychain-->>App: {username, password}

        App->>API: POST /auth/login
        API-->>App: {access_token, user}
        App->>Keychain: storeToken()
        App->>User: Show dashboard
    else Biometric failed or unavailable
        App->>User: Show login form
    end
```

---

## Error Handling

### HTTP Error Codes

| Code | Meaning | Mobile Action |
|------|---------|---------------|
| 400 | Bad Request | Show validation error |
| 401 | Unauthorized | Clear token, re-authenticate |
| 403 | Forbidden | Show access denied |
| 404 | Not Found | Show not found message |
| 429 | Rate Limited | Show retry message with countdown |
| 500 | Server Error | Show generic error, allow retry |

### Authentication Error Handling

```swift
enum AuthError: Error {
    case invalidCredentials
    case rateLimited(retryAfter: Int)
    case accountDisabled
    case tokenExpired
    case networkError(Error)
    case serverError
}

func handleAuthError(_ error: AuthError) {
    switch error {
    case .invalidCredentials:
        showError("Invalid username or password")
    case .rateLimited(let retryAfter):
        showError("Too many attempts. Try again in \(retryAfter) seconds")
    case .accountDisabled:
        showError("Account is disabled. Contact administrator.")
    case .tokenExpired:
        clearSession()
        showLoginScreen()
    case .networkError:
        showError("Network error. Check your connection.")
    case .serverError:
        showError("Server error. Please try again later.")
    }
}
```

### Retry Strategy

```swift
class APIClient {
    private let maxRetries = 3
    private let retryDelay: TimeInterval = 1.0

    func request<T: Decodable>(
        _ endpoint: Endpoint
    ) async throws -> T {
        var lastError: Error?

        for attempt in 0..<maxRetries {
            do {
                return try await performRequest(endpoint)
            } catch let error as APIError {
                if case .unauthorized = error {
                    // Token expired - refresh and retry once
                    try await tokenManager.refreshToken()
                    return try await performRequest(endpoint)
                }

                if case .rateLimited = error {
                    throw error // Don't retry rate limits
                }

                lastError = error
                try await Task.sleep(nanoseconds: UInt64(retryDelay * Double(attempt + 1) * 1_000_000_000))
            }
        }

        throw lastError ?? APIError.unknown
    }
}
```

---

## Security Best Practices

### Token Security

1. **Never log tokens** - Redact in all logs
2. **Clear on logout** - Remove all tokens from Keychain
3. **Validate on server** - Don't trust client-side expiration alone
4. **Use HTTPS only** - Never send tokens over plain HTTP

### Credential Storage

1. **Use Keychain** - Never UserDefaults or plain storage
2. **Biometric protection** - Use `.biometryCurrentSet` for credentials
3. **Device-only** - Use `ThisDeviceOnly` accessibility
4. **Clear on uninstall** - Keychain clears automatically

### Network Security

1. **Certificate pinning** - Consider for high-security deployments
2. **TLS 1.2+** - Reject older protocols
3. **No HTTP fallback** - Fail if HTTPS unavailable

### App Transport Security

Configure `Info.plist` appropriately:

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <false/>
    <key>NSExceptionDomains</key>
    <dict>
        <key>argusai.local</key>
        <dict>
            <key>NSExceptionAllowsInsecureHTTPLoads</key>
            <true/>
            <key>NSIncludesSubdomains</key>
            <true/>
        </dict>
    </dict>
</dict>
```

---

## Related Documentation

- [OpenAPI Specification](./openapi-v1.yaml) - Complete API reference
- [Push Notification Architecture](./mobile-push-architecture.md) - Planned
- [Cloud Relay Architecture](./cloud-relay-architecture.md) - Planned

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-25 | Initial documentation (Story P10-5.2) |
