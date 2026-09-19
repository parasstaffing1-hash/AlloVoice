import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const { service, description, postcode, address, date, time, name, phone, email, referralSource } = body;

    if (!service || !description || !postcode || !date || !time || !name || !phone || !email) {
      return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
    }

    const id = `BK-${Date.now().toString(36).toUpperCase()}`;

    // In production: create Job + Customer records in the database
    // await db.job.create({ ... });
    // await db.customer.upsert({ ... });

    return NextResponse.json({
      id,
      status: "pending",
      message: "Booking request received",
    });
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }
}
