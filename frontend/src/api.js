// Thin wrapper around fetch: every page gets real API data or a readable error, never placeholder data.
export async function api(path, options = {}) {
  let res
  try {
    res = await fetch(path, options)
  } catch {
    throw new Error('Cannot reach the backend. Is it running on port 8000?')
  }
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = body?.detail
    // FastAPI validation errors are a list of {msg, loc}.
    const msg = Array.isArray(detail) ? detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join('; ') : detail
    throw new Error(msg || `Request failed (${res.status})`)
  }
  return body
}

export const qs = (params) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined && v !== false)).toString()
