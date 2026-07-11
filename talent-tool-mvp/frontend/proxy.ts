import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { intlMiddleware } from "./i18n";

// 让 next-intl 先跑(同步 locale cookie),然后复用返回的 response headers 做 Supabase 鉴权.
export async function proxy(request: NextRequest) {
  // Step 1: 让 next-intl 设置 locale cookie
  const intlResponse = intlMiddleware(request);
  // 如果中间件返回了重定向,直接返回
  if (intlResponse.headers.get("location")) {
    return intlResponse;
  }

  const { pathname } = request.nextUrl;

  // Step 2: 复用 intl 响应作为基础,保留其 set-cookie
  const response = NextResponse.next({
    request: { headers: request.headers },
  });
  intlResponse.headers.forEach((value: string, key: string) => {
    response.headers.set(key, value);
  });

  // Step 3: 公共路由
  if (pathname === "/" || pathname === "/login") {
    return response;
  }

  // Check for demo mode user (stored in cookie by client)
  const demoUser = request.cookies.get("recruittech_demo_role")?.value;
  if (demoUser) {
    // Demo mode — skip Supabase auth, enforce role-based routing
    if (pathname.startsWith("/mind") && demoUser !== "client") {
      if (demoUser === "talent_partner") {
        return NextResponse.redirect(new URL("/mothership/dashboard", request.url));
      }
      if (demoUser === "admin") {
        return NextResponse.redirect(new URL("/mothership/admin/analytics", request.url));
      }
    }
    if (pathname.startsWith("/mothership") && demoUser === "client") {
      return NextResponse.redirect(new URL("/mind/dashboard", request.url));
    }
    if (pathname.startsWith("/mothership/admin") && demoUser !== "admin") {
      return NextResponse.redirect(new URL("/mothership/dashboard", request.url));
    }
    return response;
  }

  // Real auth — check Supabase session
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => {
            request.cookies.set(name, value);
            response.cookies.set(name, value, options);
          });
        },
      },
    }
  );

  const { data: { session } } = await supabase.auth.getSession();

  // No session and no demo cookie — redirect to login
  if (!session) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Fetch user role from users table
  const { data: user } = await supabase
    .from("users")
    .select("role")
    .eq("id", session.user.id)
    .single();

  const role = user?.role as string | undefined;

  // Route guards
  if (pathname.startsWith("/mind") && role !== "client") {
    if (role === "talent_partner") {
      return NextResponse.redirect(new URL("/mothership/dashboard", request.url));
    }
    if (role === "admin") {
      return NextResponse.redirect(new URL("/mothership/admin/analytics", request.url));
    }
  }

  if (pathname.startsWith("/mothership") && role === "client") {
    return NextResponse.redirect(new URL("/mind/dashboard", request.url));
  }

  if (pathname.startsWith("/mothership/admin") && role !== "admin") {
    return NextResponse.redirect(new URL("/mothership/dashboard", request.url));
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|api).*)",
  ],
};
