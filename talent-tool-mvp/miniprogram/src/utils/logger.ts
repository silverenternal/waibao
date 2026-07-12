/**
 * T1203 — tiny logger that no-ops in production to keep the console clean
 * inside the WeChat devtools and on real devices.
 */
const ENABLED = true; // flip to `import.meta.env.DEV` in production builds

function fmt(level: string, args: unknown[]) {
  return [`[waibao:${level}]`, ...args];
}

export const logger = {
  debug(...args: unknown[]) {
    if (ENABLED) console.debug(...fmt('debug', args));
  },
  info(...args: unknown[]) {
    if (ENABLED) console.info(...fmt('info', args));
  },
  warn(...args: unknown[]) {
    if (ENABLED) console.warn(...fmt('warn', args));
  },
  error(...args: unknown[]) {
    console.error(...fmt('error', args));
  },
};