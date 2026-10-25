const BASE62 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
/** Random 128-bit capability, fixed-width Base62. No alias or click counter. */
export async function createShortToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  let number = BigInt('0x' + Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join(''));
  let token = '';
  do { token = BASE62[Number(number % 62n)] + token; number /= 62n; } while (number);
  token = token.padStart(22, '0');
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  const hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  return { token, hash };
}
