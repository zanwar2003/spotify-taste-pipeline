import { NextRequest, NextResponse } from "next/server";
import { clearSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  await clearSession();
  // 303 so the browser follows the redirect with GET.
  return NextResponse.redirect(new URL("/", req.url), 303);
}
