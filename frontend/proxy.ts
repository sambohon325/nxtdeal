import { NextRequest, NextResponse } from "next/server";
import { deploymentRedirect } from "./lib/deploymentRouting";

export function proxy(request: NextRequest) {
  const target = deploymentRedirect(process.env.NEXT_PUBLIC_DEPLOYMENT_MODE, request.nextUrl.pathname);
  return target ? NextResponse.redirect(new URL(target, request.url)) : NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
