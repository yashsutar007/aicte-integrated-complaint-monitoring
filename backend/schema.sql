
CREATE DATABASE IF NOT EXISTS aicte_complaints
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE aicte_complaints;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM(
        'SUPER_ADMIN',
        'ADMIN',
        'BUREAU_OFFICER',
        'CASE_OFFICER',
        'VIEWER'
    ) NOT NULL DEFAULT 'CASE_OFFICER',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bureaus (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    code VARCHAR(40) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_bureaus (
    user_id BIGINT UNSIGNED NOT NULL,
    bureau_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (user_id, bureau_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (bureau_id) REFERENCES bureaus(id)
);

CREATE TABLE IF NOT EXISTS institutions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    institution_code VARCHAR(60) UNIQUE,
    name VARCHAR(255) NOT NULL,
    institution_type VARCHAR(100),
    state VARCHAR(100),
    district VARCHAR(100),
    address TEXT,
    official_email VARCHAR(255),
    phone VARCHAR(25),
    status ENUM('ACTIVE', 'INACTIVE', 'UNDER_REVIEW')
        NOT NULL DEFAULT 'ACTIVE',
    created_by BIGINT UNSIGNED,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id),
    INDEX idx_institution_name (name),
    INDEX idx_institution_location (state, district)
);

CREATE TABLE IF NOT EXISTS complaints (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_number VARCHAR(40) NOT NULL UNIQUE,
    institution_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(100) NOT NULL,
    priority ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
        NOT NULL DEFAULT 'MEDIUM',
    status ENUM(
        'SUBMITTED',
        'UNDER_REVIEW',
        'ASSIGNED',
        'AWAITING_INFORMATION',
        'RESOLVED',
        'CLOSED',
        'REOPENED'
    ) NOT NULL DEFAULT 'SUBMITTED',
    current_bureau_id BIGINT UNSIGNED,
    created_by BIGINT UNSIGNED NOT NULL,
    reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sla_due_at DATETIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (institution_id) REFERENCES institutions(id),
    FOREIGN KEY (current_bureau_id) REFERENCES bureaus(id),
    FOREIGN KEY (created_by) REFERENCES users(id),
    INDEX idx_complaint_status (status),
    INDEX idx_complaint_priority (priority),
    INDEX idx_complaint_institution (institution_id),
    INDEX idx_complaint_sla (sla_due_at)
);

CREATE TABLE IF NOT EXISTS complaint_assignments (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    complaint_id BIGINT UNSIGNED NOT NULL,
    bureau_id BIGINT UNSIGNED NOT NULL,
    assigned_to BIGINT UNSIGNED,
    assigned_by BIGINT UNSIGNED NOT NULL,
    note TEXT,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    released_at DATETIME,
    FOREIGN KEY (complaint_id) REFERENCES complaints(id),
    FOREIGN KEY (bureau_id) REFERENCES bureaus(id),
    FOREIGN KEY (assigned_to) REFERENCES users(id),
    FOREIGN KEY (assigned_by) REFERENCES users(id),
    INDEX idx_assignment_bureau (bureau_id),
    INDEX idx_assignment_user (assigned_to)
);

CREATE TABLE IF NOT EXISTS case_actions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    complaint_id BIGINT UNSIGNED NOT NULL,
    actor_id BIGINT UNSIGNED NOT NULL,
    action_type VARCHAR(80) NOT NULL,
    from_status VARCHAR(40),
    to_status VARCHAR(40),
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (complaint_id) REFERENCES complaints(id),
    FOREIGN KEY (actor_id) REFERENCES users(id),
    INDEX idx_case_actions_date (complaint_id, created_at)
);

CREATE TABLE IF NOT EXISTS complaint_links (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    complaint_id BIGINT UNSIGNED NOT NULL,
    related_complaint_id BIGINT UNSIGNED NOT NULL,
    relationship ENUM(
        'POTENTIAL_DUPLICATE',
        'RELATED',
        'FOLLOW_UP'
    ) NOT NULL DEFAULT 'RELATED',
    review_status ENUM('SUGGESTED', 'CONFIRMED', 'REJECTED')
        NOT NULL DEFAULT 'SUGGESTED',
    confidence DECIMAL(5, 2),
    explanation TEXT,
    created_by BIGINT UNSIGNED,
    reviewed_by BIGINT UNSIGNED,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME,
    FOREIGN KEY (complaint_id) REFERENCES complaints(id),
    FOREIGN KEY (related_complaint_id) REFERENCES complaints(id),
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (reviewed_by) REFERENCES users(id),
    UNIQUE KEY uq_complaint_link (
        complaint_id, related_complaint_id, relationship
    )
);

CREATE TABLE IF NOT EXISTS sla_policies (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    priority ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
        NOT NULL UNIQUE,
    target_hours INT UNSIGNED NOT NULL,
    alert_before_hours INT UNSIGNED NOT NULL DEFAULT 24,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS notifications (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    complaint_id BIGINT UNSIGNED,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    severity ENUM('INFO', 'WARNING', 'CRITICAL')
        NOT NULL DEFAULT 'INFO',
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (complaint_id) REFERENCES complaints(id),
    INDEX idx_notification_user (user_id, is_read, created_at)
);

CREATE TABLE IF NOT EXISTS documents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    complaint_id BIGINT UNSIGNED,
    institution_id BIGINT UNSIGNED,
    uploaded_by BIGINT UNSIGNED NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    stored_path VARCHAR(500) NOT NULL,
    mime_type VARCHAR(120),
    size_bytes BIGINT UNSIGNED,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (complaint_id) REFERENCES complaints(id),
    FOREIGN KEY (institution_id) REFERENCES institutions(id),
    FOREIGN KEY (uploaded_by) REFERENCES users(id),
    INDEX idx_document_complaint (complaint_id),
    INDEX idx_document_institution (institution_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    entity_id VARCHAR(80),
    details JSON,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_audit_entity (entity_type, entity_id),
    INDEX idx_audit_date (created_at)
);

INSERT IGNORE INTO sla_policies
    (priority, target_hours, alert_before_hours)
VALUES
    ('LOW', 240, 48),
    ('MEDIUM', 120, 24),
    ('HIGH', 48, 12),
    ('CRITICAL', 24, 4);
