const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface FetchOptions extends RequestInit {
  token?: string;
}

async function request<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  const { token, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function apiRequest<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  return request<T>(endpoint, options);
}

export const api = {
  request: apiRequest,
  auth: {
    login: (data: { email: string; password: string }) =>
      request("/api/auth/login", { method: "POST", body: JSON.stringify(data) }),
    register: (data: { email: string; password: string; full_name: string; phone?: string }) =>
      request("/api/auth/register", { method: "POST", body: JSON.stringify(data) }),
    me: (token: string) => request("/api/auth/me", { token }),
    createBusiness: (data: any, token: string) =>
      request("/api/auth/business", { method: "POST", body: JSON.stringify(data), token }),
    getBusiness: (token: string) => request("/api/auth/business", { token }),
  },
  dashboard: {
    stats: (token: string) => request("/api/dashboard/stats", { token }),
  },
  customers: {
    list: (token: string) => request("/api/customers/", { token }),
    create: (data: any, token: string) =>
      request("/api/customers/", { method: "POST", body: JSON.stringify(data), token }),
    get: (id: string, token: string) => request(`/api/customers/${id}`, { token }),
    update: (id: string, data: any, token: string) =>
      request(`/api/customers/${id}`, { method: "PUT", body: JSON.stringify(data), token }),
    delete: (id: string, token: string) =>
      request(`/api/customers/${id}`, { method: "DELETE", token }),
    properties: (customerId: string, token: string) =>
      request(`/api/customers/${customerId}/properties`, { token }),
    createProperty: (customerId: string, data: any, token: string) =>
      request(`/api/customers/${customerId}/properties`, { method: "POST", body: JSON.stringify(data), token }),
  },
  jobs: {
    list: (token: string, status?: string) =>
      request(`/api/jobs/${status ? `?status=${status}` : ""}`, { token }),
    create: (data: any, token: string) =>
      request("/api/jobs/", { method: "POST", body: JSON.stringify(data), token }),
    get: (id: string, token: string) => request(`/api/jobs/${id}`, { token }),
    updateStatus: (id: string, status: string, token: string) =>
      request(`/api/jobs/${id}/status?status=${status}`, { method: "PUT", token }),
    assign: (jobId: string, technicianId: string, token: string) =>
      request(`/api/jobs/${jobId}/assign?technician_id=${technicianId}`, { method: "PUT", token }),
    uploadPhoto: (jobId: string, url: string, photoType: string, token: string) =>
      request(`/api/jobs/${jobId}/photos?url=${url}&photo_type=${photoType}`, { method: "POST", token }),
  },
  quotes: {
    list: (token: string) => request("/api/quotes/", { token }),
    create: (data: any, token: string) =>
      request("/api/quotes/", { method: "POST", body: JSON.stringify(data), token }),
    get: (id: string, token: string) => request(`/api/quotes/${id}`, { token }),
    accept: (id: string, token: string) =>
      request(`/api/quotes/${id}/accept`, { method: "PUT", token }),
  },
  invoices: {
    list: (token: string) => request("/api/invoices/", { token }),
    create: (data: any, token: string) =>
      request("/api/invoices/", { method: "POST", body: JSON.stringify(data), token }),
    get: (id: string, token: string) => request(`/api/invoices/${id}`, { token }),
    pay: (id: string, token: string, amount?: number) =>
      request(`/api/invoices/${id}/pay${amount ? `?amount=${amount}` : ""}`, { method: "PUT", token }),
  },
  voice: {
    transcribe: (data: { audio_base64?: string; transcript?: string }, token: string) =>
      request("/api/voice/transcribe", { method: "POST", body: JSON.stringify(data), token }),
    textToSpeech: (text: string, token: string) =>
      request(`/api/voice/text-to-speech?text=${encodeURIComponent(text)}`, { method: "POST", token }),
    speechToText: (audioBase64: string, token: string) =>
      request(`/api/voice/speech-to-text?audio_base64=${encodeURIComponent(audioBase64)}`, { method: "POST", token }),
  },
  voiceNotes: {
    transcribeJob: (data: { audio_base64?: string; transcript?: string; job_id: string }, token: string) =>
      request("/api/voice-notes/transcribe-job", { method: "POST", body: JSON.stringify(data), token }),
    save: (jobId: string, notes: any, token: string) =>
      request(`/api/voice-notes/save?job_id=${jobId}`, { method: "POST", body: JSON.stringify(notes), token }),
    get: (jobId: string, token: string) =>
      request(`/api/voice-notes/${jobId}`, { token }),
    refine: (transcript: string, style: string, token: string) =>
      request("/api/voice-notes/refine", { method: "POST", body: JSON.stringify({ transcript, style }), token }),
  },
  predictions: {
    duration: (data: any, token: string) =>
      request("/api/predictions/duration", { method: "POST", body: JSON.stringify(data), token }),
    cost: (data: any, token: string) =>
      request("/api/predictions/cost", { method: "POST", body: JSON.stringify(data), token }),
    accuracy: (token: string) =>
      request("/api/predictions/accuracy", { token }),
  },
  reviews: {
    list: (token: string) => request("/api/reviews/", { token }),
    create: (data: any, token: string) =>
      request("/api/reviews/", { method: "POST", body: JSON.stringify(data), token }),
  },
  postcodes: {
    lookup: (postcode: string) => request(`/api/postcodes/lookup/${postcode}`),
    validate: (postcode: string) => request(`/api/postcodes/validate/${postcode}`),
    autocomplete: (query: string) => request(`/api/postcodes/autocomplete/${query}`),
    nearest: (lat: number, lng: number) =>
      request(`/api/postcodes/nearest?latitude=${lat}&longitude=${lng}`),
    // Backend is GET /api/postcodes/bulk?postcodes=A&postcodes=B (query list).
    bulk: (postcodes: string[]) =>
      request(
        `/api/postcodes/bulk?${postcodes.map((p) => `postcodes=${encodeURIComponent(p)}`).join("&")}`
      ),
  },
  photos: {
    upload: async (jobId: string, file: File, photoType: string, token: string) => {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(
        `${API_BASE}/api/photos/upload/${jobId}?photo_type=${photoType}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        }
      );
      return response.json();
    },
    list: (jobId: string, token: string) =>
      request(`/api/photos/job/${jobId}`, { token }),
    analyze: (photoId: string, token: string) =>
      request(`/api/photos/analyze/${photoId}`, { method: "POST", token }),
  },
  realtime: {
    dispatchBoard: (token: string) =>
      request("/api/realtime/dispatch/board", { token }),
    updateLocation: (lat: number, lng: number, token: string) =>
      request(`/api/realtime/location/update?latitude=${lat}&longitude=${lng}`, { method: "POST", token }),
  },
  notifications: {
    send: (data: any, token: string) =>
      request("/api/notifications/send", { method: "POST", body: JSON.stringify(data), token }),
    jobCompletion: (jobId: string, token: string) =>
      request(`/api/notifications/job-completion?job_id=${jobId}`, { method: "POST", token }),
    reviewRequest: (jobId: string, token: string) =>
      request(`/api/notifications/review-request?job_id=${jobId}`, { method: "POST", token }),
    invoiceReminder: (invoiceId: string, token: string) =>
      request(`/api/notifications/invoice-reminder?invoice_id=${invoiceId}`, { method: "POST", token }),
  },
  whatsapp: {
    sendMessage: (phone: string, message: string, token: string) =>
      request("/api/whatsapp/send-message", {
        method: "POST",
        body: JSON.stringify({ phone_number: phone, message }),
        token,
      }),
    sendQuote: (customerId: string, quoteId: string, token: string) =>
      request(`/api/whatsapp/send-quote?customer_id=${customerId}&quote_id=${quoteId}`, { method: "POST", token }),
    sendInvoice: (customerId: string, invoiceId: string, token: string) =>
      request(`/api/whatsapp/send-invoice?customer_id=${customerId}&invoice_id=${invoiceId}`, { method: "POST", token }),
    sendJobUpdate: (customerId: string, jobId: string, status: string, token: string) =>
      request(`/api/whatsapp/send-job-update?customer_id=${customerId}&job_id=${jobId}&status=${status}`, { method: "POST", token }),
  },
  payments: {
    config: (token: string) => request("/api/payments/config", { token }),
    createIntent: (invoiceId: string, token: string) =>
      request(`/api/payments/create-payment-intent?invoice_id=${invoiceId}`, { method: "POST", token }),
    createCheckout: (invoiceId: string, token: string) =>
      request(`/api/payments/create-checkout-session?invoice_id=${invoiceId}`, { method: "POST", token }),
    paymentLink: (invoiceId: string, token: string) =>
      request(`/api/payments/payment-link/${invoiceId}`, { token }),
    gocardlessMandate: (invoiceId: string, token: string) =>
      request(`/api/payments/gocardless/create-mandate?invoice_id=${invoiceId}`, { method: "POST", token }),
  },
  xero: {
    auth: (token: string) => request("/api/xero/auth", { token }),
    status: (token: string) => request("/api/xero/status", { token }),
    syncInvoices: (token: string) => request("/api/xero/sync-invoices", { method: "POST", token }),
    syncContacts: (token: string) => request("/api/xero/sync-contacts", { method: "POST", token }),
    disconnect: (token: string) => request("/api/xero/disconnect", { method: "POST", token }),
  },
  gocardless: {
    status: (token: string) => request("/api/gocardless/status", { token }),
    redirectFlow: (invoiceId: string, token: string) =>
      request(`/api/gocardless/redirect-flow?invoice_id=${invoiceId}`, { method: "POST", token }),
    completeFlow: (redirectFlowId: string, token: string) =>
      request("/api/gocardless/complete-flow", {
        method: "POST",
        body: JSON.stringify({ redirect_flow_id: redirectFlowId }),
        token,
      }),
    collect: (invoiceId: string, token: string) =>
      request(`/api/gocardless/collect?invoice_id=${invoiceId}`, { method: "POST", token }),
    mandates: (token: string) => request("/api/gocardless/mandates", { token }),
  },
  emails: {
    // Backend takes query params: POST /api/emails/send?to=&subject=&html=
    send: (data: { to: string; subject: string; html: string }, token: string) =>
      request(
        `/api/emails/send?to=${encodeURIComponent(data.to)}&subject=${encodeURIComponent(data.subject)}&html=${encodeURIComponent(data.html)}`,
        { method: "POST", token }
      ),
    sendInvoice: (invoiceId: string, token: string) =>
      request(`/api/emails/send-invoice/${invoiceId}`, { method: "POST", token }),
    sendQuote: (quoteId: string, token: string) =>
      request(`/api/emails/send-quote/${quoteId}`, { method: "POST", token }),
    logs: (token: string) => request("/api/emails/logs", { token }),
  },
  sms: {
    // Backend takes query params: POST /api/sms/send?to_phone=&message=
    send: (data: { to_phone: string; message: string }, token: string) =>
      request(
        `/api/sms/send?to_phone=${encodeURIComponent(data.to_phone)}&message=${encodeURIComponent(data.message)}`,
        { method: "POST", token }
      ),
    // Backend: POST /api/sms/send-otp?to_phone= (no job-reminder route exists).
    sendOtp: (toPhone: string, token: string) =>
      request(`/api/sms/send-otp?to_phone=${encodeURIComponent(toPhone)}`, { method: "POST", token }),
    logs: (token: string) => request("/api/sms/logs", { token }),
  },
  gdpr: {
    // Backend: POST /api/gdpr/consent?consent_type=&granted= (records for current user).
    consent: (data: { consent_type: string; granted: boolean }, token: string) =>
      request(
        `/api/gdpr/consent?consent_type=${encodeURIComponent(data.consent_type)}&granted=${data.granted}`,
        { method: "POST", token }
      ),
    // Backend: POST /api/gdpr/export-data/{user_id} (own user id or a customer id).
    exportData: (userId: string, token: string) =>
      request(`/api/gdpr/export-data/${userId}`, { method: "POST", token }),
    // Backend: POST /api/gdpr/erasure-request?customer_id= (query, optional).
    requestErasure: (data: { customer_id?: string }, token: string) =>
      request(
        `/api/gdpr/erasure-request${data?.customer_id ? `?customer_id=${encodeURIComponent(data.customer_id)}` : ""}`,
        { method: "POST", token }
      ),
    dataMap: (token: string) => request("/api/gdpr/data-map", { token }),
    // Backend: GET /api/gdpr/consent-status (current user only, no id param).
    consentStatus: (token: string) => request("/api/gdpr/consent-status", { token }),
  },
  audit: {
    logs: (token: string, limit?: number) =>
      request(`/api/audit/logs${limit ? `?limit=${limit}` : ""}`, { token }),
    // No backend /search route — /logs supports the same filters
    // (entity_type, entity_id, action, limit), so search targets it.
    search: (params: string, token: string) => request(`/api/audit/logs?${params}`, { token }),
  },
  rbac: {
    roles: (token: string) => request("/api/rbac/roles", { token }),
    assignRole: (data: any, token: string) =>
      request("/api/rbac/assign", { method: "POST", body: JSON.stringify(data), token }),
  },
  mfa: {
    setup: (token: string) => request("/api/mfa/setup", { method: "POST", token }),
    // Backend: POST /api/mfa/verify?code=&secret= (secret comes from the setup response).
    // No backend GET /status route exists, so status() was removed — derive MFA
    // state from the verify response instead.
    verify: (code: string, secret: string, token: string) =>
      request(
        `/api/mfa/verify?code=${encodeURIComponent(code)}&secret=${encodeURIComponent(secret)}`,
        { method: "POST", token }
      ),
  },
  webhooks: {
    list: (token: string) => request("/api/webhooks/", { token }),
    create: (data: any, token: string) =>
      request("/api/webhooks/", { method: "POST", body: JSON.stringify(data), token }),
    delete: (id: string, token: string) =>
      request(`/api/webhooks/${id}`, { method: "DELETE", token }),
    deliveries: (id: string, token: string) =>
      request(`/api/webhooks/${id}/deliveries`, { token }),
    test: (id: string, token: string) =>
      request(`/api/webhooks/${id}/test`, { method: "POST", token }),
  },
  search: {
    global: (q: string, token: string) => request(`/api/search/?q=${encodeURIComponent(q)}`, { token }),
  },
  importExport: {
    customersCsv: (token: string) => request("/api/import-export/export/customers", { token }),
    jobsCsv: (token: string) => request("/api/import-export/export/jobs", { token }),
    invoicesCsv: (token: string) => request("/api/import-export/export/invoices", { token }),
    importCustomers: async (file: File, token: string) => {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_BASE}/api/import-export/import/customers`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      return response.json();
    },
    importJobs: async (file: File, token: string) => {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_BASE}/api/import-export/import/jobs`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      return response.json();
    },
  },
  portal: {
    login: (accessCode: string) =>
      request("/api/portal/login", { method: "POST", body: JSON.stringify({ access_code: accessCode }) }),
    dashboard: (token: string) => request("/api/portal/dashboard", { token }),
    jobs: (token: string) => request("/api/portal/jobs", { token }),
    invoices: (token: string) => request("/api/portal/invoices", { token }),
    payInvoice: (invoiceId: string, token: string) =>
      request(`/api/portal/invoices/${invoiceId}/pay`, { method: "POST", token }),
    leaveReview: (jobId: string, data: any, token: string) =>
      request(`/api/portal/jobs/${jobId}/review`, { method: "POST", body: JSON.stringify(data), token }),
  },
  calendar: {
    status: (token: string) => request("/api/calendar/status", { token }),
    googleAuth: (token: string) => request("/api/calendar/google/auth", { token }),
    outlookAuth: (token: string) => request("/api/outlook/auth", { token }),
    sync: (provider: string, token: string) =>
      request(`/api/calendar/sync?provider=${provider}`, { method: "POST", token }),
  },
  outlook: {
    auth: (token: string) => request("/api/outlook/auth", { token }),
    callback: (code: string, token: string) =>
      request(`/api/outlook/callback?code=${encodeURIComponent(code)}`, { token }),
    status: (token: string) => request("/api/outlook/status", { token }),
    sync: (token: string) => request("/api/outlook/sync", { method: "POST", token }),
    disconnect: (token: string) => request("/api/outlook/disconnect", { method: "POST", token }),
  },
  telephony: {
    status: (token: string) => request("/api/telephony/status", { token }),
    call: (toPhone: string, message: string | undefined, token: string) =>
      request("/api/telephony/call", {
        method: "POST",
        body: JSON.stringify({ to_phone: toPhone, message }),
        token,
      }),
    hangup: (callSid: string, token: string) =>
      request("/api/telephony/hangup", {
        method: "POST",
        body: JSON.stringify({ call_sid: callSid }),
        token,
      }),
  },
  contracts: {
    list: (token: string) => request("/api/contracts/", { token }),
    create: (data: any, token: string) =>
      request("/api/contracts/", { method: "POST", body: JSON.stringify(data), token }),
    get: (id: string, token: string) => request(`/api/contracts/${id}`, { token }),
    pause: (id: string, token: string) =>
      request(`/api/contracts/${id}/pause`, { method: "PUT", token }),
    resume: (id: string, token: string) =>
      request(`/api/contracts/${id}/resume`, { method: "PUT", token }),
    // No backend cancel route exists — closest real semantics is pause.
    cancel: (id: string, token: string) =>
      request(`/api/contracts/${id}/pause`, { method: "PUT", token }),
    generateJobs: (id: string, token: string) =>
      request(`/api/contracts/${id}/generate-jobs`, { method: "POST", token }),
  },
  inventory: {
    list: (token: string) => request("/api/inventory/", { token }),
    // Backend takes query params: POST /api/inventory/?name=&sku=&quantity=...
    create: (
      data: {
        name: string;
        sku?: string;
        unit_price?: number;
        cost_price?: number;
        quantity?: number;
        min_quantity?: number;
        unit?: string;
        barcode?: string;
        location_id?: string;
      },
      token: string
    ) => {
      const q = new URLSearchParams({ name: data.name });
      if (data.sku) q.set("sku", data.sku);
      if (data.unit_price !== undefined) q.set("unit_price", String(data.unit_price));
      if (data.cost_price !== undefined) q.set("cost_price", String(data.cost_price));
      if (data.quantity !== undefined) q.set("quantity", String(data.quantity));
      if (data.min_quantity !== undefined) q.set("min_quantity", String(data.min_quantity));
      if (data.unit) q.set("unit", data.unit);
      if (data.barcode) q.set("barcode", data.barcode);
      if (data.location_id) q.set("location_id", data.location_id);
      return request(`/api/inventory/?${q.toString()}`, { method: "POST", token });
    },
    // Backend: POST /api/inventory/{item_id}/adjust?quantity_change=&job_id=&notes=
    adjustStock: (
      id: string,
      data: { quantity_change: number; job_id?: string; notes?: string },
      token: string
    ) => {
      const q = new URLSearchParams({ quantity_change: String(data.quantity_change) });
      if (data.job_id) q.set("job_id", data.job_id);
      if (data.notes) q.set("notes", data.notes);
      return request(`/api/inventory/${id}/adjust?${q.toString()}`, { method: "POST", token });
    },
    // No backend /usage route — usage is recorded via adjust with a negative
    // quantity_change. Keeps the (jobId, data) signature so existing callers
    // (job complete page) are unchanged.
    usage: (
      jobId: string,
      data: { inventory_item_id: string; quantity: number; notes?: string },
      token: string
    ) => {
      const q = new URLSearchParams({
        quantity_change: String(-Math.abs(data.quantity)),
        job_id: jobId,
      });
      if (data.notes) q.set("notes", data.notes);
      return request(`/api/inventory/${data.inventory_item_id}/adjust?${q.toString()}`, {
        method: "POST",
        token,
      });
    },
  },
  feedback: {
    // Backend takes query params: POST /api/feedback/?rating=&feedback_type=...
    submit: (
      data: {
        rating: number;
        feedback_type?: string;
        title?: string;
        content?: string;
        job_id?: string;
        customer_id?: string;
        nps_score?: number;
      },
      token: string
    ) => {
      const q = new URLSearchParams({ rating: String(data.rating) });
      if (data.feedback_type) q.set("feedback_type", data.feedback_type);
      if (data.title) q.set("title", data.title);
      if (data.content) q.set("content", data.content);
      if (data.job_id) q.set("job_id", data.job_id);
      if (data.customer_id) q.set("customer_id", data.customer_id);
      if (data.nps_score !== undefined) q.set("nps_score", String(data.nps_score));
      return request(`/api/feedback/?${q.toString()}`, { method: "POST", token });
    },
    list: (token: string) => request("/api/feedback/", { token }),
    // Backend route is GET /api/feedback/stats
    // (returns { average_rating, nps_score, total, csat }).
    report: (token: string) => request("/api/feedback/stats", { token }),
    stats: (token: string) => request("/api/feedback/stats", { token }),
  },
  knowledgeBase: {
    // Backend prefix is /api/kb (no /search route).
    list: (token: string, category?: string) =>
      request(`/api/kb/${category ? `?category=${encodeURIComponent(category)}` : ""}`, { token }),
    // Backend takes query params: POST /api/kb/?title=&content=&category=&tags=
    create: (
      data: { title: string; content: string; category?: string; tags?: string[] },
      token: string
    ) => {
      const q = new URLSearchParams({ title: data.title, content: data.content });
      if (data.category) q.set("category", data.category);
      (data.tags || []).forEach((t) => q.append("tags", t));
      return request(`/api/kb/?${q.toString()}`, { method: "POST", token });
    },
    // Backend looks up by slug: GET /api/kb/{slug}.
    get: (slug: string, token: string) =>
      request(`/api/kb/${encodeURIComponent(slug)}`, { token }),
    // No backend search endpoint — filter the list client-side.
    search: async (q: string, token: string) => {
      const articles: any[] = await request("/api/kb/", { token });
      const needle = q.toLowerCase();
      return (Array.isArray(articles) ? articles : []).filter(
        (a) =>
          a.title?.toLowerCase().includes(needle) ||
          a.category?.toLowerCase().includes(needle) ||
          (Array.isArray(a.tags) && a.tags.some((t: string) => t.toLowerCase().includes(needle)))
      );
    },
    helpful: (articleId: string, token: string) =>
      request(`/api/kb/${articleId}/helpful`, { method: "POST", token }),
  },
  fleet: {
    list: (token: string) => request("/api/fleet/vehicles", { token }),
    // Backend takes query params: POST /api/fleet/vehicles?registration=&make=&model=&year=
    create: (
      data: {
        registration: string;
        make?: string;
        model?: string;
        year?: number;
        assigned_technician_id?: string;
      },
      token: string
    ) => {
      const q = new URLSearchParams({ registration: data.registration });
      if (data.make) q.set("make", data.make);
      if (data.model) q.set("model", data.model);
      if (data.year !== undefined) q.set("year", String(data.year));
      if (data.assigned_technician_id) q.set("assigned_technician_id", data.assigned_technician_id);
      return request(`/api/fleet/vehicles?${q.toString()}`, { method: "POST", token });
    },
    // Backend: POST /api/fleet/location/update?latitude=&longitude= (technician GPS).
    updateLocation: (latitude: number, longitude: number, token: string) =>
      request(`/api/fleet/location/update?latitude=${latitude}&longitude=${longitude}`, {
        method: "POST",
        token,
      }),
    // Backend: GET /api/fleet/trips/{vehicle_id}.
    trips: (vehicleId: string, token: string) =>
      request(`/api/fleet/trips/${vehicleId}`, { token }),
    positions: (token: string) => request("/api/fleet/positions", { token }),
  },
  reports: {
    // Real backend routes: /revenue, /technician-performance,
    // /customer-satisfaction, /job-utilization.
    // (No /overview, /performance, or /export routes exist.)
    revenue: (params: string, token: string) => request(`/api/reports/revenue?${params}`, { token }),
    technicianPerformance: (token: string) =>
      request("/api/reports/technician-performance", { token }),
    customerSatisfaction: (token: string) =>
      request("/api/reports/customer-satisfaction", { token }),
    jobUtilization: (token: string) => request("/api/reports/job-utilization", { token }),
  },
  branches: {
    list: (token: string) => request("/api/branches/", { token }),
    create: (data: any, token: string) =>
      request("/api/branches/", { method: "POST", body: JSON.stringify(data), token }),
  },
  analytics: {
    track: (event: string, properties: any, token: string) =>
      request("/api/analytics/event", { method: "POST", body: JSON.stringify({ event, properties }), token }),
    summary: (token: string) => request("/api/analytics/summary", { token }),
    events: (event: string, token: string) =>
      request(`/api/analytics/events${event ? `?event=${event}` : ""}`, { token }),
  },
  aiQuote: {
    generate: (data: any, token: string) =>
      request("/api/ai-quote/generate", { method: "POST", body: JSON.stringify(data), token }),
    similar: (data: any, token: string) =>
      request("/api/ai-quote/similar", { method: "POST", body: JSON.stringify(data), token }),
    upsell: (data: any, token: string) =>
      request("/api/ai-quote/upsell", { method: "POST", body: JSON.stringify(data), token }),
    templates: (token: string) => request("/api/ai-quote/templates", { token }),
  },
  memberships: {
    listPlans: (token: string) => request("/api/memberships/plans", { token }),
    createPlan: (data: any, token: string) =>
      request("/api/memberships/plans", { method: "POST", body: JSON.stringify(data), token }),
    enroll: (data: any, token: string) =>
      request("/api/memberships/enroll", { method: "POST", body: JSON.stringify(data), token }),
    getMembership: (customerId: string, token: string) =>
      request(`/api/memberships/${customerId}`, { token }),
    cancel: (membershipId: string, token: string) =>
      request("/api/memberships/cancel", { method: "POST", body: JSON.stringify({ membership_id: membershipId }), token }),
    businessOverview: (token: string) => request("/api/memberships/business/overview", { token }),
    scheduleRecurring: (token: string) =>
      request("/api/memberships/schedule-recurring", { method: "POST", token }),
  },
  pricebook: {
    listServices: (token: string, category?: string) =>
      request(`/api/pricebook/services${category ? `?category=${encodeURIComponent(category)}` : ""}`, { token }),
    createService: (data: any, token: string) =>
      request("/api/pricebook/services", { method: "POST", body: JSON.stringify(data), token }),
    updateService: (id: string, data: any, token: string) =>
      request(`/api/pricebook/services/${id}`, { method: "PUT", body: JSON.stringify(data), token }),
    deleteService: (id: string, token: string) =>
      request(`/api/pricebook/services/${id}`, { method: "DELETE", token }),
    listMaterials: (token: string) => request("/api/pricebook/materials", { token }),
    createMaterial: (data: any, token: string) =>
      request("/api/pricebook/materials", { method: "POST", body: JSON.stringify(data), token }),
    updateMaterial: (id: string, data: any, token: string) =>
      request(`/api/pricebook/materials/${id}`, { method: "PUT", body: JSON.stringify(data), token }),
    deleteMaterial: (id: string, token: string) =>
      request(`/api/pricebook/materials/${id}`, { method: "DELETE", token }),
    getMarkups: (token: string) => request("/api/pricebook/markups", { token }),
    updateMarkups: (data: any, token: string) =>
      request("/api/pricebook/markups", { method: "POST", body: JSON.stringify(data), token }),
    getQuoteTemplate: (token: string) => request("/api/pricebook/quote-template", { token }),
    updateQuoteTemplate: (data: any, token: string) =>
      request("/api/pricebook/quote-template", { method: "POST", body: JSON.stringify(data), token }),
    calculate: (data: any, token: string) =>
      request("/api/pricebook/calculate", { method: "POST", body: JSON.stringify(data), token }),
  },
  cis: {
    registerSub: (data: any, token: string) =>
      request("/api/cis/subcontractor/register", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    listSubs: (token: string) => request("/api/cis/subcontractor/list", { token }),
    updateSub: (id: string, data: any, token: string) =>
      request(`/api/cis/subcontractor/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
        token,
      }),
    verifySub: (id: string, data: any, token: string) =>
      request(`/api/cis/subcontractor/${id}/verify`, {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    createPayment: (data: any, token: string) =>
      request("/api/cis/payment/monthly", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    periodPayments: (period: string, token: string) =>
      request(`/api/cis/payment/monthly/${period}`, { token }),
    payslip: (paymentId: string, token: string) =>
      request(`/api/cis/payment/${paymentId}/payslip`, { method: "POST", token }),
    returns: (period: string, token: string) =>
      request(`/api/cis/returns/${period}`, { token }),
    annualSummary: (taxYear: string, token: string) =>
      request(`/api/cis/annual-summary?tax_year=${encodeURIComponent(taxYear)}`, { token }),
  },
  tracking: {
    status: (jobId: string) => request(`/api/tracking/${jobId}/status`),
    eta: (jobId: string) => request(`/api/tracking/${jobId}/eta`),
    share: (jobId: string, token: string) =>
      request(`/api/tracking/${jobId}/share`, { method: "POST", token }),
    shared: (code: string) => request(`/api/tracking/share/${code}`),
    updateLocation: (latitude: number, longitude: number, jobId: string | null, token: string) =>
      request("/api/tracking/location/update", {
        method: "POST",
        body: JSON.stringify({ latitude, longitude, job_id: jobId }),
        token,
      }),
  },
  scheduling: {
    optimize: (jobId: string, technicianIds: string[], token: string) =>
      request("/api/scheduling/optimize", {
        method: "POST",
        body: JSON.stringify({ job_id: jobId, technician_ids: technicianIds }),
        token,
      }),
    autoAssign: (token: string) =>
      request("/api/scheduling/auto-assign", { method: "POST", token }),
    availability: (startDate: string, endDate: string, token: string) =>
      request(`/api/scheduling/availability?start_date=${startDate}&end_date=${endDate}`, { token }),
    reschedule: (jobId: string, newDate: string, token: string) =>
      request("/api/scheduling/reschedule", {
        method: "POST",
        body: JSON.stringify({ job_id: jobId, new_date: newDate }),
        token,
      }),
  },
  aiInsights: {
    churnPredict: (customerId: string, token: string) =>
      request("/api/ai-insights/churn/predict", {
        method: "POST",
        body: JSON.stringify({ customer_id: customerId }),
        token,
      }),
    churnSegment: (token: string) =>
      request("/api/ai-insights/churn/segment", { token }),
    churnRetain: (data: { customer_ids: string[]; campaign_type: string }, token: string) =>
      request("/api/ai-insights/churn/retain", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    reviewRespond: (data: any, token: string) =>
      request("/api/ai-insights/reviews/respond", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    reviewBulkRespond: (reviews: any[], token: string) =>
      request("/api/ai-insights/reviews/bulk-respond", {
        method: "POST",
        body: JSON.stringify({ reviews }),
        token,
      }),
    upsellGenerate: (data: any, token: string) =>
      request("/api/ai-insights/upsell/generate", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    upsellOnCompletion: (jobId: string, token: string) =>
      request("/api/ai-insights/upsell/on-completion", {
        method: "POST",
        body: JSON.stringify({ job_id: jobId }),
        token,
      }),
  },
  quickbooks: {
    authUrl: (token: string) => request("/api/quickbooks/auth/url", { token }),
    status: (token: string) => request("/api/quickbooks/status", { token }),
    disconnect: (token: string) =>
      request("/api/quickbooks/disconnect", { method: "POST", token }),
    syncInvoices: (token: string) =>
      request("/api/quickbooks/sync/invoices", { method: "POST", token }),
    syncContacts: (token: string) =>
      request("/api/quickbooks/sync/contacts", { method: "POST", token }),
    syncPayments: (token: string) =>
      request("/api/quickbooks/sync/payments", { method: "POST", token }),
    profitLoss: (token: string) =>
      request("/api/quickbooks/profit-loss", { token }),
  },
  reviewPlatforms: {
    googleStatus: (token: string) =>
      request("/api/review-platforms/google/status", { token }),
    googleConnect: (locationId: string, token: string) =>
      request("/api/review-platforms/google/connect", {
        method: "POST",
        body: JSON.stringify({ location_id: locationId }),
        token,
      }),
    googleDisconnect: (token: string) =>
      request("/api/review-platforms/google/disconnect", { method: "POST", token }),
    googleReviews: (token: string) =>
      request("/api/review-platforms/google/reviews", { token }),
    googleReply: (reviewId: string, replyText: string, token: string) =>
      request("/api/review-platforms/google/reply", {
        method: "POST",
        body: JSON.stringify({ review_id: reviewId, reply_text: replyText }),
        token,
      }),
    trustpilotStatus: (token: string) =>
      request("/api/review-platforms/trustpilot/status", { token }),
    trustpilotConnect: (data: { api_key: string; business_unit_id: string }, token: string) =>
      request("/api/review-platforms/trustpilot/connect", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    trustpilotInvite: (data: { customer_id: string; job_id: string; email: string }, token: string) =>
      request("/api/review-platforms/trustpilot/invite", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    trustpilotInvitations: (token: string) =>
      request("/api/review-platforms/trustpilot/invitations", { token }),
    autoRequest: (jobId: string, token: string) =>
      request("/api/review-platforms/auto-request", {
        method: "POST",
        body: JSON.stringify({ job_id: jobId }),
        token,
      }),
  },
  marketing: {
    status: (token: string) => request("/api/marketing/status", { token }),
    createList: (name: string, token: string) =>
      request("/api/marketing/lists", {
        method: "POST",
        body: JSON.stringify({ name }),
        token,
      }),
    syncContacts: (token: string) =>
      request("/api/marketing/sync-contacts", { method: "POST", token }),
    sendCampaign: (data: { name: string; subject: string; html_content: string; list_id: string }, token: string) =>
      request("/api/marketing/campaign", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    winback: (token: string) =>
      request("/api/marketing/winback", { method: "POST", token }),
    zapierTriggers: (token: string) =>
      request("/api/marketing/zapier/triggers", { token }),
    zapierSubscribe: (trigger: string, targetUrl: string, token: string) =>
      request("/api/marketing/zapier/subscribe", {
        method: "POST",
        body: JSON.stringify({ trigger, target_url: targetUrl }),
        token,
      }),
    zapierUnsubscribe: (subscriptionId: string, token: string) =>
      request(`/api/marketing/zapier/subscribe/${subscriptionId}`, {
        method: "DELETE",
        token,
      }),
    zapierSubscriptions: (token: string) =>
      request("/api/marketing/zapier/subscriptions", { token }),
    zapierTest: (trigger: string, token: string) =>
      request("/api/marketing/zapier/test", {
        method: "POST",
        body: JSON.stringify({ trigger }),
        token,
      }),
  },
  chatbot: {
    chat: (message: string, sessionId: string, pageUrl?: string) =>
      request("/api/chatbot/chat", {
        method: "POST",
        body: JSON.stringify({ message, session_id: sessionId, page_url: pageUrl }),
      }),
    config: () => request("/api/chatbot/config"),
    escalate: (sessionId: string, reason: string) =>
      request("/api/chatbot/escalate", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, reason }),
      }),
    leads: (token: string) => request("/api/chatbot/leads", { token }),
    convertLead: (leadId: string, token: string) =>
      request(`/api/chatbot/leads/${leadId}/convert`, { method: "POST", token }),
  },
  performance: {
    scorecards: (period: string, token: string) =>
      request(`/api/performance/scorecards?period=${encodeURIComponent(period)}`, { token }),
    scorecard: (technicianId: string, token: string) =>
      request(`/api/performance/scorecards/${technicianId}`, { token }),
    leaderboard: (token: string) =>
      request("/api/performance/leaderboard", { token }),
    profitability: (groupBy: string, token: string) =>
      request(`/api/performance/profitability?group_by=${encodeURIComponent(groupBy)}`, { token }),
    jobProfit: (jobId: string, token: string) =>
      request(`/api/performance/job/${jobId}/profit`, { token }),
    clv: (token: string) => request("/api/performance/clv", { token }),
  },
  warehouses: {
    list: (token: string) => request("/api/warehouses", { token }),
    create: (data: { name: string; address?: string; postcode?: string; is_default?: boolean }, token: string) =>
      request("/api/warehouses", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    get: (id: string, token: string) =>
      request(`/api/warehouses/${id}`, { token }),
    adjust: (id: string, data: { sku: string; quantity_change: number; reason?: string }, token: string) =>
      request(`/api/warehouses/${id}/adjust`, {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    createTransfer: (data: { from_warehouse_id: string; to_warehouse_id: string; items: any[]; notes?: string }, token: string) =>
      request("/api/warehouses/transfers", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    listTransfers: (token: string, status?: string, warehouseId?: string) => {
      const q = new URLSearchParams();
      if (status) q.set("status", status);
      if (warehouseId) q.set("warehouse_id", warehouseId);
      const qs = q.toString() ? `?${q.toString()}` : "";
      return request(`/api/warehouses/transfers/list${qs}`, { token });
    },
    receiveTransfer: (id: string, token: string, receivedItems?: any[]) =>
      request(`/api/warehouses/transfers/${id}/receive`, {
        method: "POST",
        body: JSON.stringify(receivedItems ? { received_items: receivedItems } : {}),
        token,
      }),
  },
  attendance: {
    clockIn: (data: { latitude?: number; longitude?: number; notes?: string }, token: string) =>
      request("/api/attendance/clock-in", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    clockOut: (data: { latitude?: number; longitude?: number; notes?: string }, token: string) =>
      request("/api/attendance/clock-out", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    me: (token: string, startDate?: string, endDate?: string) => {
      const q = new URLSearchParams();
      if (startDate) q.set("start_date", startDate);
      if (endDate) q.set("end_date", endDate);
      const qs = q.toString() ? `?${q.toString()}` : "";
      return request(`/api/attendance/me${qs}`, { token });
    },
    team: (token: string, startDate?: string, endDate?: string) => {
      const q = new URLSearchParams();
      if (startDate) q.set("start_date", startDate);
      if (endDate) q.set("end_date", endDate);
      const qs = q.toString() ? `?${q.toString()}` : "";
      return request(`/api/attendance/team${qs}`, { token });
    },
    status: (token: string) => request("/api/attendance/status", { token }),
    breakStart: (token: string) =>
      request("/api/attendance/break/start", { method: "POST", token }),
    breakEnd: (token: string) =>
      request("/api/attendance/break/end", { method: "POST", token }),
  },
  safety: {
    checkIn: (data: { job_id?: string; latitude?: number; longitude?: number; note?: string }, token: string) =>
      request("/api/safety/check-in", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    status: (token: string) => request("/api/safety/status", { token }),
    panic: (data: { latitude?: number; longitude?: number; job_id?: string; message?: string }, token: string) =>
      request("/api/safety/panic", {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }),
    alerts: (token: string, status?: string) =>
      request(`/api/safety/alerts${status ? `?status=${encodeURIComponent(status)}` : ""}`, { token }),
    resolveAlert: (alertId: string, resolutionNote: string, token: string) =>
      request(`/api/safety/alerts/${alertId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ resolution_note: resolutionNote }),
        token,
      }),
    getSettings: (token: string) => request("/api/safety/settings", { token }),
    updateSettings: (data: any, token: string) =>
      request("/api/safety/settings", {
        method: "PUT",
        body: JSON.stringify(data),
        token,
      }),
  },
  branding: {
    get: (token: string) => request("/api/branding", { token }),
    update: (data: any, token: string) =>
      request("/api/branding", {
        method: "PUT",
        body: JSON.stringify(data),
        token,
      }),
    uploadLogo: (logoBase64: string, filename: string, token: string) =>
      request("/api/branding/logo", {
        method: "POST",
        body: JSON.stringify({ logo_base64: logoBase64, filename }),
        token,
      }),
    portalTheme: (subdomain?: string) =>
      request(`/api/branding/portal-theme${subdomain ? `?subdomain=${encodeURIComponent(subdomain)}` : ""}`),
    reset: (token: string) =>
      request("/api/branding/reset", { method: "POST", token }),
  },
  billing: {
    plans: (token?: string) =>
      request("/api/billing/plans", token ? { token } : {}),
    checkout: (data: { plan_id: string; billing_cycle: string; seats: number }, token: string) =>
      request("/api/billing/checkout", { method: "POST", body: JSON.stringify(data), token }),
    subscription: (token: string) => request("/api/billing/subscription", { token }),
    portal: (token: string) => request("/api/billing/portal", { method: "POST", token }),
  },
  voiceAgent: {
    transcribe: (audioBase64: string, token: string) =>
      request("/api/voice-agent/transcribe", { method: "POST", body: JSON.stringify({ audio_base64: audioBase64 }), token }),
    speak: (text: string, token: string) =>
      request("/api/voice-agent/speak", { method: "POST", body: JSON.stringify({ text }), token }),
    chat: (message: string, sessionId: string | null, token: string) =>
      request("/api/voice-agent/chat", { method: "POST", body: JSON.stringify({ message, session_id: sessionId }), token }),
    voices: (token: string) => request("/api/voice-agent/voices", { token }),
  },
};
