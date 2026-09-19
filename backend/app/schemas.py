from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    phone: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    phone: Optional[str]
    role: str
    avatar_url: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class BusinessCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None


class BusinessResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    logo_url: Optional[str]
    address_line1: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip_code: Optional[str]
    currency: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CustomerCreate(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone: str
    company: Optional[str] = None
    notes: Optional[str] = None


class CustomerResponse(BaseModel):
    id: UUID
    full_name: str
    email: Optional[str]
    phone: str
    company: Optional[str]
    notes: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PropertyCreate(BaseModel):
    label: str = "Primary"
    address_line1: str
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    property_type: str = "residential"


class PropertyResponse(BaseModel):
    id: UUID
    label: str
    address_line1: str
    address_line2: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip_code: Optional[str]
    property_type: str
    created_at: datetime

    class Config:
        from_attributes = True


class ServiceCreate(BaseModel):
    name: str
    description: Optional[str] = None
    base_price: float
    unit: str = "fixed"
    estimated_hours: Optional[float] = None


class ServiceResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    base_price: float
    unit: str
    estimated_hours: Optional[float]
    is_active: bool

    class Config:
        from_attributes = True


class JobCreate(BaseModel):
    customer_id: UUID
    property_id: Optional[UUID] = None
    service_id: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    priority: str = "normal"


class JobResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    status: str
    priority: str
    scheduled_at: Optional[datetime]
    estimated_cost: Optional[float]
    final_cost: Optional[float]
    ai_summary: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuoteItemCreate(BaseModel):
    description: str
    quantity: float = 1
    unit_price: float


class QuoteCreate(BaseModel):
    job_id: UUID
    customer_id: UUID
    title: Optional[str] = None
    items: List[QuoteItemCreate]
    tax_rate: float = 20
    notes: Optional[str] = None
    valid_days: int = 30


class QuoteItemResponse(BaseModel):
    id: UUID
    description: str
    quantity: float
    unit_price: float
    total: float

    class Config:
        from_attributes = True


class QuoteResponse(BaseModel):
    id: UUID
    quote_number: str
    title: Optional[str]
    subtotal: float
    tax_rate: float
    tax_amount: float
    total: float
    notes: Optional[str]
    valid_until: Optional[datetime]
    is_accepted: bool
    created_at: datetime
    items: List[QuoteItemResponse]

    class Config:
        from_attributes = True


class InvoiceCreate(BaseModel):
    job_id: UUID
    customer_id: UUID
    items: List[QuoteItemCreate]
    tax_rate: float = 0
    notes: Optional[str] = None
    due_days: int = 30


class InvoiceItemResponse(BaseModel):
    id: UUID
    description: str
    quantity: float
    unit_price: float
    total: float

    class Config:
        from_attributes = True


class InvoiceResponse(BaseModel):
    id: UUID
    invoice_number: str
    subtotal: float
    tax_rate: float
    tax_amount: float
    total: float
    amount_paid: float
    payment_status: str
    due_date: Optional[datetime]
    paid_at: Optional[datetime]
    created_at: datetime
    items: List[InvoiceItemResponse]

    class Config:
        from_attributes = True


class VoiceQuoteRequest(BaseModel):
    audio_base64: Optional[str] = None
    transcript: Optional[str] = None
    customer_id: Optional[UUID] = None
    property_id: Optional[UUID] = None


class VoiceQuoteResponse(BaseModel):
    transcript: str
    quote_data: dict
    voice_response: str


class DashboardStats(BaseModel):
    total_jobs: int
    active_jobs: int
    completed_jobs: int
    total_revenue: float
    pending_quotes: int
    pending_invoices: int
    total_customers: int
    reviews_count: int
    average_rating: float
    revenue_this_month: float
    jobs_this_month: int


class ReviewCreate(BaseModel):
    job_id: UUID
    customer_id: Optional[UUID] = None
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = None
    content: Optional[str] = None


class ReviewResponse(BaseModel):
    id: UUID
    rating: int
    title: Optional[str]
    content: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
