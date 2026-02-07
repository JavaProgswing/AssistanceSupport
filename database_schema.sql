-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- 1. Companies Table
-- Stores the profiles of different companies the bot handles.
create table if not exists companies (
    id uuid primary key default uuid_generate_v4(),
    name text not null,
    tagline text unique,
    description text,
    banner_color text default '#000000',
    admin_username text,
    admin_password text, -- Storing plain/hashed as needed. For MVP/User Request: "returns... password".
    industry text, -- e.g., 'Electronics', 'Fashion', 'SaaS'
    support_email text,
    return_policy text not null, -- Specific instructions for the AI (e.g., 'Strict: Damaged items only')
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 2. Transactions (Bills) Table
-- Represents the "Bill" or "Order" user is claiming regex.
create table if not exists transactions (
    id uuid primary key default uuid_generate_v4(),
    company_id uuid references companies(id) not null,
    customer_id uuid, -- Can link to auth.users
    order_ref text not null, -- External Order ID (e.g. #ORD-123)
    amount decimal(10, 2) not null,
    currency text default 'USD',
    item_details jsonb not null, -- e.g. '[{"item": "Laptop", "price": 999}]'
    purchase_date timestamp with time zone default timezone('utc'::text, now()) not null,
    status text default 'COMPLETED' -- 'COMPLETED', 'REFUNDED', 'DISPUTED'
);

-- 3. Refund Requests Table
-- Tracks the actual support interaction and AI decision.
create table if not exists refund_requests (
    id uuid primary key default uuid_generate_v4(),
    transaction_id uuid references transactions(id),
    company_id uuid references companies(id) not null,
    user_transcript text, -- Full chat log
    evidence_image_url text, -- Path to the uploaded image in Storage
    ai_analysis_json jsonb, -- The full JSON analysis from Gemini (probability, reasoning)
    status text default 'PENDING', -- 'PENDING', 'APPROVED', 'REJECTED', 'ESCALATED'
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- SEED DATA (For Testing)
insert into companies (name, industry, return_policy) values 
('TechNova', 'Electronics', 'Strict Policy: Refunds are only approved for severe structural damage or non-functional devices. Cosmetic scratches are rejected.'),
('CozyWear', 'Fashion', 'Lenient Policy: Refunds allowed for any effective damage, sizing issues, or general dissatisfaction within 30 days.');

-- 4. Company Refund Queue (Payouts)
-- Created when the AI decides a refund is valid.
create table if not exists company_refund_queue (
    id uuid primary key default uuid_generate_v4(),
    transaction_id uuid references transactions(id),
    company_id uuid references companies(id) not null,
    amount decimal(10, 2) not null,
    status text default 'READY_FOR_PAYOUT', -- 'READY_FOR_PAYOUT', 'PROCESSED'
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 5. Escalation Requests
-- Created when user explicitly asks for an agent or AI cannot resolve.
create table if not exists escalation_requests (
    id uuid primary key default uuid_generate_v4(),
    transaction_id uuid references transactions(id),
    customer_id uuid, -- Optional link to user
    reason text,
    status text default 'OPEN', -- 'OPEN', 'RESOLVED', 'IN_PROGRESS'
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);
