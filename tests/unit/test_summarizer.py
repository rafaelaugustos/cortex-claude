from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.summarizer import summarize


def test_summarize_short_text():
    text = "Hello world."
    result = summarize(text)
    assert result == text


def test_summarize_reduces_tokens():
    text = (
        "The authentication service uses JWT tokens with 24-hour expiry. "
        "Refresh tokens are stored in httpOnly cookies with a 7-day lifetime. "
        "The service validates tokens using the express-jwt middleware. "
        "Rate limiting is applied at 10 auth attempts per minute per IP address. "
        "Failed attempts are logged to the security audit trail. "
        "Two-factor authentication is supported via TOTP and SMS. "
        "Session data is stored in Redis with automatic expiration."
    )
    result = summarize(text)
    assert count_tokens(result) < count_tokens(text)


def test_summarize_preserves_meaning():
    text = (
        "PostgreSQL is the primary database for this project. "
        "We use JSONB columns for flexible metadata storage. "
        "The database runs on AWS RDS with multi-AZ deployment. "
        "Backups are taken every 6 hours with 30-day retention."
    )
    result = summarize(text)
    assert "PostgreSQL" in result or "database" in result
