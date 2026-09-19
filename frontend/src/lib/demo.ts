import { api } from "./api";

const DEMO_EMAIL = "demo@voicefield.demo";
const DEMO_PASSWORD = "VoiceDemo123!";

/**
 * One-click demo entry: login as the shared demo user (register first
 * time), then seed one customer + two jobs if the account is empty.
 * Best-effort throughout — never throws.
 */
export async function enterDemo(
  login: (email: string, password: string) => Promise<void>,
  register: (email: string, password: string, fullName: string, phone?: string) => Promise<void>
): Promise<void> {
  try {
    await login(DEMO_EMAIL, DEMO_PASSWORD);
  } catch {
    await register(DEMO_EMAIL, DEMO_PASSWORD, "Demo Engineer", "07911 123456");
  }
  try {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    if (!token) return;
    const customers: any = await api.customers.list(token);
    const list = Array.isArray(customers) ? customers : customers?.customers || [];
    if (list.length > 0) return; // already seeded
    const c: any = await api.customers.create(
      {
        full_name: "Sarah Thompson",
        email: "sarah@example.co.uk",
        phone: "07911 654321",
        address_line1: "14 Yarwood Close",
        city: "Manchester",
        postcode: "M1 1AE",
      },
      token
    );
    if (!c?.id) return;
    await api.jobs.create(
      {
        customer_id: c.id,
        title: "Boiler annual service",
        description: "Worcester combi annual service + gas safety check",
        priority: "normal",
      },
      token
    );
    await api.jobs.create(
      {
        customer_id: c.id,
        title: "Radiator cold at top",
        description: "Bleed and balance radiators, check inhibitor levels",
        priority: "urgent",
      },
      token
    );
  } catch {
    // seeding is best-effort; login already succeeded
  }
}
