function normalizeBase(base) {
  if (!base) {
    return '/api';
  }
  return base.endsWith('/') ? base.slice(0, -1) : base;
}

function buildUrl(path) {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }

  const prefix = normalizeBase(import.meta.env.VITE_API_BASE_URL);
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${prefix}${cleanPath}`;
}

export async function apiRequest(path, options = {}) {
  const response = await fetch(buildUrl(path), options);
  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const body = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const message = (isJson && (body?.detail || body?.message)) || `Request failed: ${response.status}`;
    throw new Error(message);
  }

  return body;
}