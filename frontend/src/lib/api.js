const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

/** Central API client. Cookie-based Flask sessions are intentionally retained. */
export async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(options.headers || {})
    }
  });

  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = typeof payload === 'object' && payload?.message
      ? payload.message
      : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return payload;
}
