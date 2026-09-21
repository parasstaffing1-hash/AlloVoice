import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Boolean, Text, ForeignKey,
    Numeric, Integer, Float, Enum as SAEnum, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class UserRole(str, enum.Enum):
    OWNER = "owner"
    MANAGER = "manager"
    TECHNICIAN = "technician"
    DISPATCHER = "dispatcher"
    CUSTOMER = "customer"
    ADMIN = "admin"


class JobStatus(str, enum.Enum):
    QUOTE_REQUESTED = "quote_requested"
    QUOTE_SENT = "quote_sent"
    QUOTE_APPROVED = "quote_approved"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    INVOICED = "invoiced"
    PAID = "paid"
    CANCELLED = "cancelled"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    REFUNDED = "refunded"
    PARTIALLY_PAID = "partially_paid"


class ContractStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(20))
    role = Column(SAEnum(UserRole), default=UserRole.OWNER)
    avatar_url = Column(String(500))
    is_active = Column(Boolean, default=True)
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(255))
    mfa_backup_codes = Column(JSONB)
    last_login_at = Column(DateTime)
    last_login_ip = Column(String(45))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business = relationship("Business", back_populates="owner", uselist=False)
    technician_profile = relationship("Technician", back_populates="user", uselist=False)
    api_keys = relationship("ApiKey", back_populates="user")
    gdpr_consent = relationship("GdprConsent", back_populates="user", uselist=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)
    key_prefix = Column(String(10), nullable=False)
    scopes = Column(JSONB, default=[])
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="api_keys")


class Business(Base):
    __tablename__ = "businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    description = Column(Text)
    phone = Column(String(20))
    email = Column(String(255))
    website = Column(String(500))
    logo_url = Column(String(500))
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(100))
    zip_code = Column(String(20))
    country = Column(String(100), default="GB")
    latitude = Column(Numeric(10, 7))
    longitude = Column(Numeric(10, 7))
    service_radius_km = Column(Integer, default=50)
    vat_rate = Column(Numeric(5, 2), default=20)
    currency = Column(String(3), default="GBP")
    country_code = Column(String(2), default="GB")
    timezone = Column(String(64), default="Europe/London")
    tax_rate = Column(Float, default=20.0)
    tax_name = Column(String(16), default="VAT")
    stripe_account_id = Column(String(255))
    stripe_onboarded = Column(Boolean, default=False)
    gocardless_mandate = Column(String(255))
    xero_tenant_id = Column(String(255))
    xero_access_token = Column(Text)
    xero_refresh_token = Column(Text)
    xero_token_expires = Column(DateTime)
    google_calendar_sync = Column(Boolean, default=False)
    outlook_calendar_sync = Column(Boolean, default=False)
    novu_subscriber_id = Column(String(255))
    logo_r2_key = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="business")
    customers = relationship("Customer", back_populates="business")
    technicians = relationship("Technician", back_populates="business")
    jobs = relationship("Job", back_populates="business")
    services = relationship("Service", back_populates="business")
    materials = relationship("Material", back_populates="business")
    contracts = relationship("Contract", back_populates="business")
    inventory = relationship("InventoryItem", back_populates="business")
    locations = relationship("BusinessLocation", back_populates="business")
    webhooks = relationship("Webhook", back_populates="business")
    roles = relationship("BusinessRole", back_populates="business")
    kb_articles = relationship("KnowledgeBaseArticle", back_populates="business")


class BusinessLocation(Base):
    __tablename__ = "business_locations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    name = Column(String(255), nullable=False)
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(100))
    zip_code = Column(String(20))
    latitude = Column(Numeric(10, 7))
    longitude = Column(Numeric(10, 7))
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="locations")
    inventory = relationship("InventoryItem", back_populates="location")


class BusinessRole(Base):
    __tablename__ = "business_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False)
    permissions = Column(JSONB, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="roles")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255))
    phone = Column(String(20), nullable=False)
    company = Column(String(255))
    notes = Column(Text)
    tags = Column(String(500))
    portal_token = Column(String(255), unique=True)
    portal_enabled = Column(Boolean, default=False)
    marketing_consent = Column(Boolean, default=False)
    gdpr_erasure_requested = Column(Boolean, default=False)
    gdpr_erasure_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business = relationship("Business", back_populates="customers")
    properties = relationship("Property", back_populates="customer")
    jobs = relationship("Job", back_populates="customer")
    quotes = relationship("Quote", back_populates="customer")
    invoices = relationship("Invoice", back_populates="customer")
    contracts = relationship("Contract", back_populates="customer")


class Property(Base):
    __tablename__ = "properties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    label = Column(String(255), default="Primary")
    address_line1 = Column(String(255), nullable=False)
    address_line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(100))
    zip_code = Column(String(20))
    latitude = Column(Numeric(10, 7))
    longitude = Column(Numeric(10, 7))
    property_type = Column(String(50), default="residential")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="properties")
    jobs = relationship("Job", back_populates="property")


class Service(Base):
    __tablename__ = "services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    base_price = Column(Numeric(10, 2), nullable=False)
    unit = Column(String(50), default="fixed")
    estimated_hours = Column(Numeric(5, 2))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="services")


class Material(Base):
    __tablename__ = "materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    name = Column(String(255), nullable=False)
    sku = Column(String(100))
    unit_price = Column(Numeric(10, 2), nullable=False)
    unit = Column(String(50), default="piece")
    quantity_in_stock = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="materials")


class Technician(Base):
    __tablename__ = "technicians"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    skills = Column(String(500))
    hourly_rate = Column(Numeric(10, 2))
    is_available = Column(Boolean, default=True)
    vehicle_plate = Column(String(20))
    current_latitude = Column(Numeric(10, 7))
    current_longitude = Column(Numeric(10, 7))
    last_location_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="technician_profile")
    business = relationship("Business", back_populates="technicians")
    jobs = relationship("Job", back_populates="technician")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"))
    technician_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"))
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"))
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"))
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(SAEnum(JobStatus), default=JobStatus.QUOTE_REQUESTED)
    priority = Column(String(20), default="normal")
    scheduled_at = Column(DateTime)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    estimated_cost = Column(Numeric(10, 2))
    final_cost = Column(Numeric(10, 2))
    google_calendar_event_id = Column(String(255))
    outlook_calendar_event_id = Column(String(255))
    notes = Column(Text)
    ai_summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business = relationship("Business", back_populates="jobs")
    customer = relationship("Customer", back_populates="jobs")
    property = relationship("Property", back_populates="jobs")
    technician = relationship("Technician", back_populates="jobs")
    quote = relationship("Quote", back_populates="job", uselist=False)
    invoice = relationship("Invoice", back_populates="job", uselist=False)
    photos = relationship("JobPhoto", back_populates="job")
    timeline = relationship("ActivityTimeline", back_populates="job")
    contract = relationship("Contract", back_populates="jobs")


class JobPhoto(Base):
    __tablename__ = "job_photos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"))
    url = Column(String(500), nullable=False)
    r2_key = Column(String(500))
    photo_type = Column(String(20), default="before")
    caption = Column(String(255))
    ai_description = Column(Text)
    taken_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="photos")


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"))
    quote_number = Column(String(50), unique=True, nullable=False)
    title = Column(String(255))
    subtotal = Column(Numeric(10, 2), nullable=False)
    tax_rate = Column(Numeric(5, 2), default=0)
    tax_amount = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), nullable=False)
    notes = Column(Text)
    valid_until = Column(DateTime)
    is_accepted = Column(Boolean, default=False)
    accepted_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="quote")
    customer = relationship("Customer", back_populates="quotes")
    items = relationship("QuoteItem", back_populates="quote")


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quote_id = Column(UUID(as_uuid=True), ForeignKey("quotes.id"), nullable=False)
    description = Column(String(255), nullable=False)
    quantity = Column(Numeric(10, 2), default=1)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total = Column(Numeric(10, 2), nullable=False)
    sort_order = Column(Integer, default=0)

    quote = relationship("Quote", back_populates="items")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"))
    invoice_number = Column(String(50), unique=True, nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    tax_rate = Column(Numeric(5, 2), default=0)
    tax_amount = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), nullable=False)
    amount_paid = Column(Numeric(10, 2), default=0)
    payment_status = Column(SAEnum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_method = Column(String(50))
    stripe_payment_intent_id = Column(String(255))
    gocardless_payment_id = Column(String(255))
    xero_invoice_id = Column(String(255))
    xero_synced_at = Column(DateTime)
    due_date = Column(DateTime)
    paid_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="invoice")
    customer = relationship("Customer", back_populates="invoices")
    items = relationship("InvoiceItem", back_populates="invoice")
    payments = relationship("Payment", back_populates="invoice")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    description = Column(String(255), nullable=False)
    quantity = Column(Numeric(10, 2), default=1)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total = Column(Numeric(10, 2), nullable=False)
    sort_order = Column(Integer, default=0)

    invoice = relationship("Invoice", back_populates="items")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"))
    rating = Column(Integer, nullable=False)
    title = Column(String(255))
    content = Column(Text)
    google_review_url = Column(String(500))
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="GBP")
    payment_method = Column(String(50))
    stripe_payment_id = Column(String(255))
    gocardless_payment_id = Column(String(255))
    transaction_id = Column(String(255))
    status = Column(String(20), default="completed")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    invoice = relationship("Invoice", back_populates="payments")


class ActivityTimeline(Base):
    __tablename__ = "activity_timeline"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    action = Column(String(100), nullable=False)
    description = Column(Text)
    metadata_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="timeline")


# ─── Production Models ────────────────────────────────


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True))
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_audit_business_entity", "business_id", "entity_type", "entity_id"),
    )


class Webhook(Base):
    __tablename__ = "webhooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    url = Column(String(500), nullable=False)
    secret = Column(String(255), nullable=False)
    events = Column(JSONB, nullable=False, default=[])
    is_active = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime)
    failure_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="webhooks")
    deliveries = relationship("WebhookDelivery", back_populates="webhook")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id = Column(UUID(as_uuid=True), ForeignKey("webhooks.id"), nullable=False)
    event = Column(String(100), nullable=False)
    payload = Column(JSONB, nullable=False)
    response_status = Column(Integer)
    response_body = Column(Text)
    success = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    next_retry_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    webhook = relationship("Webhook", back_populates="deliveries")


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(SAEnum(ContractStatus), default=ContractStatus.DRAFT)
    frequency = Column(String(50), nullable=False)
    rrule = Column(String(255))
    monthly_price = Column(Numeric(10, 2))
    annual_price = Column(Numeric(10, 2))
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime)
    next_job_date = Column(DateTime)
    sla_response_hours = Column(Integer)
    sla_resolution_hours = Column(Integer)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business = relationship("Business", back_populates="contracts")
    customer = relationship("Customer", back_populates="contracts")
    jobs = relationship("Job", back_populates="contract")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    location_id = Column(UUID(as_uuid=True), ForeignKey("business_locations.id"))
    name = Column(String(255), nullable=False)
    sku = Column(String(100))
    description = Column(Text)
    unit_price = Column(Numeric(10, 2))
    cost_price = Column(Numeric(10, 2))
    quantity = Column(Integer, default=0)
    min_quantity = Column(Integer, default=0)
    unit = Column(String(50), default="piece")
    barcode = Column(String(255))
    qr_code_url = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business = relationship("Business", back_populates="inventory")
    location = relationship("BusinessLocation", back_populates="inventory")
    usage_logs = relationship("InventoryUsage", back_populates="item")


class InventoryUsage(Base):
    __tablename__ = "inventory_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(UUID(as_uuid=True), ForeignKey("inventory_items.id"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    technician_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"))
    quantity_used = Column(Integer, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    item = relationship("InventoryItem", back_populates="usage_logs")


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    feedback_type = Column(String(20), nullable=False)
    rating = Column(Integer)
    nps_score = Column(Integer)
    title = Column(String(255))
    content = Column(Text)
    response = Column(Text)
    responded_at = Column(DateTime)
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeBaseArticle(Base):
    __tablename__ = "kb_articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(100))
    tags = Column(JSONB, default=[])
    is_published = Column(Boolean, default=False)
    view_count = Column(Integer, default=0)
    helpful_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business = relationship("Business", back_populates="kb_articles")


class GdprConsent(Base):
    __tablename__ = "gdpr_consents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    consent_type = Column(String(50), nullable=False)
    granted = Column(Boolean, nullable=False)
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="gdpr_consent")


class GdprErasureRequest(Base):
    __tablename__ = "gdpr_erasure_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    status = Column(String(20), default="pending")
    requested_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)
    notes = Column(Text)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    to_email = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    template = Column(String(100))
    resend_id = Column(String(255))
    status = Column(String(20), default="queued")
    metadata_json = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime)


class SmsLog(Base):
    __tablename__ = "sms_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    to_phone = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    twilio_sid = Column(String(255))
    status = Column(String(20), default="queued")
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    event = Column(String(100), nullable=False, index=True)
    properties = Column(JSONB)
    user_id = Column(UUID(as_uuid=True))
    session_id = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class FleetVehicle(Base):
    __tablename__ = "fleet_vehicles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    registration = Column(String(20), nullable=False)
    make = Column(String(100))
    model = Column(String(100))
    year = Column(Integer)
    assigned_technician_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FleetTrip(Base):
    __tablename__ = "fleet_trips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("fleet_vehicles.id"), nullable=False)
    technician_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"))
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    start_lat = Column(Numeric(10, 7))
    start_lng = Column(Numeric(10, 7))
    end_lat = Column(Numeric(10, 7))
    end_lng = Column(Numeric(10, 7))
    distance_km = Column(Numeric(8, 2))
    duration_minutes = Column(Integer)
    started_at = Column(DateTime)
    ended_at = Column(DateTime)


class CalendarSync(Base):
    __tablename__ = "calendar_syncs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    provider = Column(String(20), nullable=False)
    calendar_id = Column(String(255))
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expires = Column(DateTime)
    sync_enabled = Column(Boolean, default=True)
    last_synced_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
