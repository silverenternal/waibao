/**
 * T5007 — MSW browser worker setup.
 *
 * Imports the shared handlers and wires them into a Service Worker. Only
 * started in the browser when NEXT_PUBLIC_USE_MOCK=true. See MswProvider.
 */

import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);
