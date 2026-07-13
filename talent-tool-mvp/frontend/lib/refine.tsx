"use client";
import { Refine } from "@refinedev/core";
import routerProvider from "@refinedev/nextjs-router";
import dataProvider from "@refinedev/simple-rest";
import type { ReactNode } from "react";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "/api";
export function RefineProvider({ children }: { children: ReactNode }) {
  return <Refine routerProvider={routerProvider} dataProvider={dataProvider(apiUrl)} options={{ syncWithLocation: true, warnWhenUnsavedChanges: true }}>{children}</Refine>;
}
