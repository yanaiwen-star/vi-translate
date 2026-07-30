BEGIN;

CREATE TABLE IF NOT EXISTS translator_profiles (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE REFERENCES users(id),
    subject_type VARCHAR(16) NOT NULL,
    display_name VARCHAR(80) NOT NULL,
    bio TEXT NOT NULL DEFAULT '',
    country_code VARCHAR(2) NOT NULL,
    city VARCHAR(80) NOT NULL DEFAULT '',
    service_mode VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    verification_status VARCHAR(16) NOT NULL DEFAULT 'unverified',
    completeness_score INTEGER NOT NULL DEFAULT 0,
    contact_ciphertext TEXT,
    last_active_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS profile_languages (
    id VARCHAR(36) PRIMARY KEY,
    profile_id VARCHAR(36) NOT NULL REFERENCES translator_profiles(id) ON DELETE CASCADE,
    language_code VARCHAR(16) NOT NULL,
    CONSTRAINT uq_profile_language UNIQUE (profile_id, language_code)
);

CREATE TABLE IF NOT EXISTS profile_services (
    id VARCHAR(36) PRIMARY KEY,
    profile_id VARCHAR(36) NOT NULL REFERENCES translator_profiles(id) ON DELETE CASCADE,
    service_code VARCHAR(32) NOT NULL,
    CONSTRAINT uq_profile_service UNIQUE (profile_id, service_code)
);

CREATE TABLE IF NOT EXISTS directory_contact_requests (
    id VARCHAR(36) PRIMARY KEY,
    profile_id VARCHAR(36) NOT NULL REFERENCES translator_profiles(id) ON DELETE CASCADE,
    requester_id VARCHAR(36) NOT NULL REFERENCES users(id),
    purpose VARCHAR(160) NOT NULL DEFAULT '',
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    idempotency_key VARCHAR(96) UNIQUE,
    expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS translation_needs (
    id VARCHAR(36) PRIMARY KEY,
    requester_id VARCHAR(36) NOT NULL REFERENCES users(id),
    source_lang VARCHAR(16) NOT NULL,
    target_lang VARCHAR(16) NOT NULL,
    service_type VARCHAR(32) NOT NULL,
    service_mode VARCHAR(16) NOT NULL,
    country_code VARCHAR(2) NOT NULL DEFAULT '',
    city VARCHAR(80) NOT NULL DEFAULT '',
    service_at TIMESTAMP,
    note VARCHAR(120) NOT NULL DEFAULT '',
    response_limit INTEGER NOT NULL DEFAULT 3,
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS need_responses (
    id VARCHAR(36) PRIMARY KEY,
    need_id VARCHAR(36) NOT NULL REFERENCES translation_needs(id) ON DELETE CASCADE,
    profile_id VARCHAR(36) NOT NULL REFERENCES translator_profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_need_profile_response UNIQUE (need_id, profile_id)
);

CREATE TABLE IF NOT EXISTS directory_notifications (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    kind VARCHAR(32) NOT NULL,
    entity_type VARCHAR(32) NOT NULL DEFAULT '',
    entity_id VARCHAR(36) NOT NULL DEFAULT '',
    dedupe_key VARCHAR(128) UNIQUE,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS directory_verifications (
    id VARCHAR(36) PRIMARY KEY,
    profile_id VARCHAR(36) NOT NULL UNIQUE REFERENCES translator_profiles(id) ON DELETE CASCADE,
    provider VARCHAR(32) NOT NULL DEFAULT '',
    verification_type VARCHAR(32) NOT NULL DEFAULT 'individual',
    status VARCHAR(16) NOT NULL DEFAULT 'unverified',
    provider_ref VARCHAR(128) NOT NULL DEFAULT '',
    verified_at TIMESTAMP,
    expires_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS directory_reports (
    id VARCHAR(36) PRIMARY KEY,
    profile_id VARCHAR(36) NOT NULL REFERENCES translator_profiles(id) ON DELETE CASCADE,
    reporter_id VARCHAR(36) NOT NULL REFERENCES users(id),
    reason VARCHAR(32) NOT NULL,
    note VARCHAR(120) NOT NULL DEFAULT '',
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_profile_reporter UNIQUE (profile_id, reporter_id)
);

CREATE INDEX IF NOT EXISTS ix_translator_profiles_status ON translator_profiles(status);
CREATE INDEX IF NOT EXISTS ix_translator_profiles_country ON translator_profiles(country_code);
CREATE INDEX IF NOT EXISTS ix_translator_profiles_city ON translator_profiles(city);
CREATE INDEX IF NOT EXISTS ix_translator_profiles_last_active ON translator_profiles(last_active_at);
CREATE INDEX IF NOT EXISTS ix_profile_languages_code ON profile_languages(language_code);
CREATE INDEX IF NOT EXISTS ix_profile_services_code ON profile_services(service_code);
CREATE INDEX IF NOT EXISTS ix_contact_requests_owner ON directory_contact_requests(profile_id, status);
CREATE INDEX IF NOT EXISTS ix_contact_requests_requester ON directory_contact_requests(requester_id, status);
CREATE INDEX IF NOT EXISTS ix_translation_needs_match ON translation_needs(status, target_lang, service_type, service_mode);
CREATE INDEX IF NOT EXISTS ix_translation_needs_expires ON translation_needs(expires_at);
CREATE INDEX IF NOT EXISTS ix_directory_notifications_user ON directory_notifications(user_id, is_read, created_at);
CREATE INDEX IF NOT EXISTS ix_directory_notifications_expires ON directory_notifications(expires_at);
CREATE INDEX IF NOT EXISTS ix_directory_reports_profile ON directory_reports(profile_id, status);

COMMIT;
