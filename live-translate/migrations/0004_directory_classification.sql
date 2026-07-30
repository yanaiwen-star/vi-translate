BEGIN;

CREATE TABLE IF NOT EXISTS profile_domains (
    id VARCHAR(36) PRIMARY KEY,
    profile_id VARCHAR(36) NOT NULL REFERENCES translator_profiles(id) ON DELETE CASCADE,
    domain_code VARCHAR(32) NOT NULL,
    CONSTRAINT uq_profile_domain UNIQUE (profile_id, domain_code)
);

CREATE TABLE IF NOT EXISTS need_services (
    id VARCHAR(36) PRIMARY KEY,
    need_id VARCHAR(36) NOT NULL REFERENCES translation_needs(id) ON DELETE CASCADE,
    service_code VARCHAR(32) NOT NULL,
    CONSTRAINT uq_need_service UNIQUE (need_id, service_code)
);

CREATE TABLE IF NOT EXISTS need_domains (
    id VARCHAR(36) PRIMARY KEY,
    need_id VARCHAR(36) NOT NULL REFERENCES translation_needs(id) ON DELETE CASCADE,
    domain_code VARCHAR(32) NOT NULL,
    CONSTRAINT uq_need_domain UNIQUE (need_id, domain_code)
);

CREATE INDEX IF NOT EXISTS ix_profile_domains_profile_id ON profile_domains(profile_id);
CREATE INDEX IF NOT EXISTS ix_profile_domains_domain_code ON profile_domains(domain_code);
CREATE INDEX IF NOT EXISTS ix_need_services_need_id ON need_services(need_id);
CREATE INDEX IF NOT EXISTS ix_need_services_service_code ON need_services(service_code);
CREATE INDEX IF NOT EXISTS ix_need_domains_need_id ON need_domains(need_id);
CREATE INDEX IF NOT EXISTS ix_need_domains_domain_code ON need_domains(domain_code);

-- Preserve all legacy profile classifications by splitting mixed service/domain tags.
INSERT INTO profile_domains (id, profile_id, domain_code)
SELECT md5(ps.profile_id || ':domain:' || mapped.domain_code), ps.profile_id, mapped.domain_code
FROM profile_services ps
JOIN (
    VALUES
        ('business', 'business'),
        ('legal', 'legal'),
        ('technical', 'engineering'),
        ('tourism', 'tourism')
) AS mapped(service_code, domain_code) ON mapped.service_code = ps.service_code
ON CONFLICT DO NOTHING;

-- Old domain-only profiles remain discoverable for both kinds of work.
INSERT INTO profile_services (id, profile_id, service_code)
SELECT md5(ps.profile_id || ':service:interpretation'), ps.profile_id, 'interpretation'
FROM profile_services ps
WHERE ps.service_code IN ('business', 'legal', 'technical', 'tourism')
ON CONFLICT DO NOTHING;

INSERT INTO profile_services (id, profile_id, service_code)
SELECT md5(ps.profile_id || ':service:translation'), ps.profile_id, 'translation'
FROM profile_services ps
WHERE ps.service_code IN ('business', 'legal', 'technical', 'tourism')
ON CONFLICT DO NOTHING;

-- Legacy specialized interpretation tags collapse into the stable service type.
INSERT INTO profile_services (id, profile_id, service_code)
SELECT md5(ps.profile_id || ':service:interpretation'), ps.profile_id, 'interpretation'
FROM profile_services ps
WHERE ps.service_code IN ('simultaneous', 'escort')
ON CONFLICT DO NOTHING;

-- Every profile gets an explicit domain so matching remains deterministic.
INSERT INTO profile_domains (id, profile_id, domain_code)
SELECT md5(p.id || ':domain:general'), p.id, 'general'
FROM translator_profiles p
WHERE NOT EXISTS (
    SELECT 1 FROM profile_domains pd WHERE pd.profile_id = p.id
)
ON CONFLICT DO NOTHING;

-- Backfill need classifications while preserving translation_needs.service_type.
INSERT INTO need_services (id, need_id, service_code)
SELECT md5(n.id || ':service:' || mapped.service_code), n.id, mapped.service_code
FROM translation_needs n
JOIN (
    VALUES
        ('interpretation', 'interpretation'),
        ('translation', 'translation'),
        ('simultaneous', 'interpretation'),
        ('escort', 'interpretation')
) AS mapped(legacy_code, service_code) ON mapped.legacy_code = n.service_type
ON CONFLICT DO NOTHING;

INSERT INTO need_domains (id, need_id, domain_code)
SELECT md5(n.id || ':domain:' || mapped.domain_code), n.id, mapped.domain_code
FROM translation_needs n
JOIN (
    VALUES
        ('business', 'business'),
        ('legal', 'legal'),
        ('technical', 'engineering'),
        ('tourism', 'tourism')
) AS mapped(legacy_code, domain_code) ON mapped.legacy_code = n.service_type
ON CONFLICT DO NOTHING;

-- Domain-only legacy needs accept both service types, matching the profile policy.
INSERT INTO need_services (id, need_id, service_code)
SELECT md5(n.id || ':service:' || service_codes.service_code), n.id, service_codes.service_code
FROM translation_needs n
CROSS JOIN (VALUES ('interpretation'), ('translation')) AS service_codes(service_code)
WHERE n.service_type IN ('business', 'legal', 'technical', 'tourism')
ON CONFLICT DO NOTHING;

INSERT INTO need_domains (id, need_id, domain_code)
SELECT md5(n.id || ':domain:general'), n.id, 'general'
FROM translation_needs n
WHERE NOT EXISTS (
    SELECT 1 FROM need_domains nd WHERE nd.need_id = n.id
)
ON CONFLICT DO NOTHING;

-- Unknown historical values are kept usable without widening the new catalog.
INSERT INTO need_services (id, need_id, service_code)
SELECT md5(n.id || ':service:translation'), n.id, 'translation'
FROM translation_needs n
WHERE NOT EXISTS (
    SELECT 1 FROM need_services ns WHERE ns.need_id = n.id
)
ON CONFLICT DO NOTHING;

DELETE FROM profile_services
WHERE service_code NOT IN ('interpretation', 'translation');

COMMIT;
