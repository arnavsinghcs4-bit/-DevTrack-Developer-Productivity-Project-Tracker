import pytest
from pydantic import ValidationError
from app.core.config import Settings, DEV_DEFAULT_SECRET_KEY, SUPPORTED_ENVIRONMENTS


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch):
    """
    Isolate tests from process-level environment variables so that a real
    ENVIRONMENT or SECRET_KEY in the shell can never leak into Settings.
    """
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)


def test_production_config_missing_secret():
    """Production configuration with an empty or whitespace-only secret must fail startup."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY="")
    assert "SECRET_KEY is required" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY="   ")
    assert "SECRET_KEY is required" in str(exc_info.value)


def test_production_config_placeholder_secret():
    """Production configuration using the known default placeholder secret must fail startup."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY=DEV_DEFAULT_SECRET_KEY)
    assert "Insecure default SECRET_KEY cannot be used in production" in str(exc_info.value)


def test_production_config_placeholder_with_whitespace_rejected():
    """The default secret surrounded by whitespace must be rejected in production."""
    padded_placeholder = f"  {DEV_DEFAULT_SECRET_KEY}  "
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY=padded_placeholder)
    assert "Insecure default SECRET_KEY cannot be used in production" in str(exc_info.value)


def test_production_config_short_secret_with_whitespace_padding_rejected():
    """A short secret padded with whitespace to >=32 characters cannot bypass the minimum-length check."""
    # 20 key characters padded with 12 spaces (raw length 32, but real key length 20)
    padded_short = "      " + ("a" * 20) + "      "
    assert len(padded_short) == 32
    assert len(padded_short.strip()) == 20

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY=padded_short)
    assert "at least 32 characters long" in str(exc_info.value)


def test_production_config_weak_secret():
    """Production configuration with an unpadded secret shorter than 32 characters must fail startup."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY="too_short_secret_key_123")
    assert "at least 32 characters long" in str(exc_info.value)


def test_production_config_acceptable_secret():
    """Production configuration with a valid >=32 character unique secret must succeed."""
    acceptable_secret = "a_sufficiently_strong_and_long_production_secret_key_2026"
    config = Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY=acceptable_secret)
    assert config.ENVIRONMENT == "production"
    assert config.SECRET_KEY == acceptable_secret


def test_production_config_secret_whitespace_normalization():
    """Leading and trailing whitespace on a valid secret is cleanly normalized for JWT operations."""
    acceptable_secret = "a_sufficiently_strong_and_long_production_secret_key_2026"
    padded_valid_secret = f"   {acceptable_secret}   "
    config = Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY=padded_valid_secret)
    assert config.SECRET_KEY == acceptable_secret


def test_empty_environment_value_rejected():
    """Empty or whitespace-only ENVIRONMENT values must fail with descriptive errors."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="")
    assert "ENVIRONMENT cannot be empty" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="   ")
    assert "ENVIRONMENT cannot be empty" in str(exc_info.value)


def test_unknown_environment_value_rejected():
    """Typo and unrecognized ENVIRONMENT values must fail with descriptive errors rather than defaulting to dev."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="producton")
    assert "Invalid ENVIRONMENT 'producton'" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="invalid_env")
    assert "Invalid ENVIRONMENT 'invalid_env'" in str(exc_info.value)


def test_supported_environment_values_work():
    """All supported environment values and aliases must be accepted and normalized."""
    valid_secret = "a_sufficiently_strong_and_long_production_secret_key_2026"

    for env_name in SUPPORTED_ENVIRONMENTS:
        config = Settings(_env_file=None, ENVIRONMENT=f"  {env_name.upper()}  ", SECRET_KEY=valid_secret)
        assert config.ENVIRONMENT == env_name


def test_development_config_behavior():
    """Development configuration should cleanly use the convenient default secret without errors."""
    for dev_env in ("development", "dev"):
        config = Settings(_env_file=None, ENVIRONMENT=dev_env)
        assert config.ENVIRONMENT == dev_env
        assert config.SECRET_KEY == DEV_DEFAULT_SECRET_KEY
