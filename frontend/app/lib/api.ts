export const api = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, { ...init, credentials: "include" });
  if (response.status === 401 && typeof window !== "undefined" && !String(input).includes("/auth/")) {
    window.dispatchEvent(new Event("market-ai:session-expired"));
  }
  return response;
}

export async function jsonRequest<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  const response = await apiFetch(`${api}${path}`, body === undefined ? { cache: "no-store" } : {
    method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Certaines données sont invalides. Vérifiez le format et les champs obligatoires.");
  return data as T;
}
