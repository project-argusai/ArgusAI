"""
Constants for APNS and push notification providers.

Story P11-2.1: APNS provider constants
"""

# APNS Hosts
APNS_PRODUCTION_HOST = "api.push.apple.com"
APNS_SANDBOX_HOST = "api.sandbox.push.apple.com"
APNS_PORT = 443

# APNS API path
APNS_DEVICE_PATH = "/3/device/{device_token}"

# JWT configuration
JWT_ALGORITHM = "ES256"
JWT_TOKEN_LIFETIME_SECONDS = 3600  # 1 hour

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 2  # Exponential backoff: 2s, 4s, 8s

# APNS Error Codes (from reason header)
APNS_ERROR_CODES = {
    # Client errors
    "BadCollapseId": "The collapse identifier exceeds the maximum allowed size",
    "BadDeviceToken": "The specified device token is invalid",
    "BadExpirationDate": "The apns-expiration value is invalid",
    "BadMessageId": "The apns-id value is invalid",
    "BadPriority": "The apns-priority value is invalid",
    "BadTopic": "The apns-topic value is invalid",
    "DeviceTokenNotForTopic": "The device token doesn't match the specified topic",
    "DuplicateHeaders": "One or more headers are repeated",
    "IdleTimeout": "Idle timeout",
    "InvalidPushType": "The apns-push-type value is invalid",
    "MissingDeviceToken": "The device token is not specified in the request path",
    "MissingTopic": "The apns-topic header is missing from the request",
    "PayloadEmpty": "The message payload is empty",
    "TopicDisallowed": "Pushing to this topic is not allowed",

    # Token errors
    "BadCertificate": "The certificate is invalid",
    "BadCertificateEnvironment": "The client certificate is for the wrong environment",
    "ExpiredProviderToken": "The provider token is stale and a new token should be generated",
    "Forbidden": "The specified action is not allowed",
    "InvalidProviderToken": "The provider token is not valid or the token signature cannot be verified",
    "MissingProviderToken": "No provider certificate was used to connect to APNs",

    # Device token errors
    "Unregistered": "The device token is no longer active for the topic",

    # Server errors
    "TooManyProviderTokenUpdates": "The provider token has been updated too often",
    "TooManyRequests": "Too many requests were made consecutively to the same device token",
    "InternalServerError": "An internal server error occurred",
    "ServiceUnavailable": "The service is unavailable",
    "Shutdown": "The server is shutting down",
}

# HTTP status code to retry behavior mapping
APNS_RETRYABLE_STATUS_CODES = {429, 500, 503}
APNS_TOKEN_INVALID_STATUS_CODES = {410}  # Unregistered
APNS_AUTH_ERROR_STATUS_CODES = {401, 403}
