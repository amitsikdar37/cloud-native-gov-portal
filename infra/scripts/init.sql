-- Enable UUID extension for unique, unguessable applicant identifiers
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Define Application Lifecycle Statuses
DO $$ BEGIN
    CREATE TYPE application_status AS ENUM (
        'SUBMITTED', 
        'UNDER_REVIEW', 
        'APPROVED', 
        'REJECTED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Idempotency protection: Ensures duplicate SQS deliveries never create duplicate rows
    idempotency_key VARCHAR(64) UNIQUE NOT NULL,
    
    -- Step 1: Personal Information
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    date_of_birth DATE,
    gender VARCHAR(20),
    residential_address TEXT,

    -- Step 2: Academic Details (JSONB for multi-level educational history)
    academic_details JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Step 3: Direct S3 Photo Upload Link (Uploaded via client-side Pre-Signed URL)
    photo_s3_url TEXT NOT NULL,

    -- Step 4: Submission Metadata & State
    status application_status NOT NULL DEFAULT 'SUBMITTED',
    
    -- Audit Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_applications_phone ON applications(phone_number);
CREATE INDEX IF NOT EXISTS idx_applications_email ON applications(email);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);

-- Sorting by recent submissions
CREATE INDEX IF NOT EXISTS idx_applications_created_at ON applications(created_at DESC);

-- GIN Index on JSONB for high-speed indexing inside academic attributes
CREATE INDEX IF NOT EXISTS idx_applications_academic_gin ON applications USING gin (academic_details);

-- Auto-update Trigger for 'updated_at' column
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_timestamp ON applications;
CREATE TRIGGER set_timestamp
BEFORE UPDATE ON applications
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();
