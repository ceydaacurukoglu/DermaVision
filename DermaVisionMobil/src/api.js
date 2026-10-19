import * as SecureStore from 'expo-secure-store';

// Seçenek 1 (yalnızca emülatör): adb reverse tcp:8000 tcp:8000 yapıp 'http://localhost:8000' kullanın.
// Seçenek 2 (önerilen, mail linkleri ve gerçek telefon için): ngrok adresiniz, ör. 'https://abcd-12-34.ngrok-free.app'
// Bu adres backend/.env içindeki DERMA_BASE_URL ile AYNI olmalı.
export const BASE_URL = 'http://localhost:8000';

// Google Cloud Console'daki "Web application" client ID'si (backend'deki GOOGLE_CLIENT_ID ile AYNI olmalı)
export const GOOGLE_WEB_CLIENT_ID = '680566286065-ben5ll4iju106tr3d99r77b6iactciob.apps.googleusercontent.com';

let token = null;
export async function getToken() {
  if (token) return token;
  token = await SecureStore.getItemAsync('oturum');
  return token;
}
export async function setToken(t, kalici = true) {
  token = t || null;
  if (t && kalici) await SecureStore.setItemAsync('oturum', t);
  else await SecureStore.deleteItemAsync('oturum');
}

function hataMesaji(d) {
  if (typeof d?.detail === 'string') return d.detail;
  return (d?.detail?.[0]?.msg || 'Bir hata oluştu.').replace(/^Value error, /, '');
}

async function istek(yol, opts) {
  const t = await getToken();
  const headers = { 'ngrok-skip-browser-warning': '1', ...(opts.headers || {}) };
  if (t) headers.Authorization = `Bearer ${t}`;
  let r;
  try {
    r = await fetch(BASE_URL + yol, { ...opts, headers });
  } catch (e) {
    throw new Error('Sunucuya ulaşılamadı (' + (e?.message || e) + '). Backend açık mı ve adb reverse yapıldı mı?');
  }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    if (r.status === 401) await setToken(null);
    const err = new Error(hataMesaji(d));
    err.status = r.status;
    throw err;
  }
  return d;
}

export const api = (yol, { method = 'GET', body } = {}) =>
  istek(yol, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });

export const yukle = (yol, formData) => istek(yol, { method: 'POST', body: formData });

export const mailRe = /^[^\s@]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$/;
export const isimRe = /^\p{L}+(?:[ '\-]\p{L}+)*$/u;
export const pwErr = (p) =>
  p.length < 8
    ? 'Şifre en az 8 karakter olmalı.'
    : !/[A-Z]/.test(p) || !/[a-z]/.test(p) || !/\d/.test(p)
    ? 'En az 1 büyük harf, 1 küçük harf ve 1 rakam gerekli.'
    : '';
