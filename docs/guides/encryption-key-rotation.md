# Encryption Key Rotation Guide

This guide explains how to safely rotate the master Fernet encryption key used by ArgusAI to protect sensitive data (camera passwords, Protect credentials, AI API keys, HomeKit PINs, push tokens, etc.).

## Why Rotate the Encryption Key?

The `ENCRYPTION_KEY` is a Fernet symmetric key used to encrypt sensitive credentials at rest. Rotating this key is a critical security practice because:

- It limits the impact of a compromised key.
- It is required for long-term compliance and security hygiene.
- It is especially important if you believe a key may have been exposed.

ArgusAI supports **online key rotation** with zero downtime using the multi-key support added in Phase A.

---

## Prerequisites

Before rotating the key, ensure the following:

1. **You are running a version that supports multi-key encryption** (post Phase A).
2. You have access to run Python scripts against the production database.
3. You have a recent, verified backup of the database.
4. You have the **current** `ENCRYPTION_KEY` (required for decryption during rotation).
5. You have generated a new, strong Fernet key.

### Generating a New Key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Step-by-Step Rotation Process

### 1. Generate the New Key

```bash
NEW_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
echo $NEW_KEY
```

Store this key securely (password manager, secrets manager, etc.).

### 2. Perform a Dry Run (Strongly Recommended)

Always run a dry run first:

```bash
python backend/scripts/rotate_encryption_key.py \
  --new-key "$NEW_KEY" \
  --old-key "$CURRENT_ENCRYPTION_KEY" \
  --dry-run \
  --verbose
```

Review the output carefully. Make sure the number of records looks correct.

### 3. Execute the Rotation

If the dry run looks good, run the real rotation:

```bash
python backend/scripts/rotate_encryption_key.py \
  --new-key "$NEW_KEY" \
  --old-key "$CURRENT_ENCRYPTION_KEY"
```

The script will:
- Decrypt all sensitive values using the old key(s)
- Re-encrypt them using the new primary key
- Update the database in place

### 4. Update Your Environment

After the script completes successfully:

1. Update your `.env`, Kubernetes secrets, or systemd service file with the new key:
   ```bash
   ENCRYPTION_KEY=$NEW_KEY
   ```

2. (Optional but recommended during transition)
   ```bash
   ENCRYPTION_KEY_PREVIOUS=$OLD_KEY
   ```

   This allows the application to continue decrypting any data that was missed or added during the rotation window.

3. Restart the backend service:
   ```bash
   sudo systemctl restart argusai-backend
   ```

### 5. Verify the Rotation

After restarting:

- Log in to the web interface.
- Check that cameras still work (test live view or trigger an event).
- Verify that AI providers still function (check logs or trigger a manual description).
- Check the `/health` endpoint to confirm the app started without encryption errors.

---

## Rollback Procedure

If something goes wrong:

1. **Do not delete the old key yet.**
2. Revert your `ENCRYPTION_KEY` environment variable to the old key.
3. Restart the backend.
4. The application will continue working because the data is still encrypted with the old key (the rotation script only re-encrypts — it does not delete the old ciphertext until you are confident).

If you had already updated to the new key and want to roll back:

- Set `ENCRYPTION_KEY` back to the old key.
- Set `ENCRYPTION_KEY_PREVIOUS` to the new key (so the app can still read newly encrypted data).
- Investigate what went wrong before attempting rotation again.

---

## Best Practices

- **Always use `--dry-run` first** in production.
- Keep at least one previous key for a transition period (7–30 days) after rotation.
- Document the rotation in your internal runbook with the date and new key ID (first 8 characters).
- Consider rotating the key annually or after any suspected compromise.
- Never commit encryption keys to git.
- Use a secrets manager (e.g., HashiCorp Vault, AWS Secrets Manager, Kubernetes secrets) where possible.

---

## Troubleshooting

### "Invalid ENCRYPTION_KEY" error after restart

- You likely updated the environment variable but did not restart the backend properly.
- Or the new key is malformed.

### Some records were not re-encrypted

- The script only processes records that currently have an `encrypted:` prefix.
- Run the script again after restart — it is safe to re-run.

### "Failed to decrypt password" during rotation

- The `--old-key` you provided does not match any key that was used to encrypt the data.
- Double-check that you are using the correct current key.

### Need to rotate when multiple previous keys already exist

Use the `ENCRYPTION_KEYS` environment variable instead:

```bash
ENCRYPTION_KEYS="newest-key,previous-key-1,previous-key-2"
```

The rotation script supports this format.

---

## Related Documentation

- [ADR-008: Web Refresh Token Architecture](../architecture/12-adrs.md#adr-008-web-refresh-token-architecture-phase-a) (contains related encryption decisions)
- `backend/scripts/rotate_encryption_key.py` (the rotation tool)

---

**Last Updated:** 2026-05-15

**Maintained by:** ArgusAI Team