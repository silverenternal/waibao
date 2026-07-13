"use client"; import {RefineProvider} from "@/lib/refine"; export default function AuthenticatedLayout({children}:{children:React.ReactNode}){return <RefineProvider>{children}</RefineProvider>}
