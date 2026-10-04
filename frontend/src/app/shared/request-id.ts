export function requestId(source: Partial<Crypto> = crypto): string {
  if (source.randomUUID) {
    return source.randomUUID();
  }
  if (!source.getRandomValues) {
    throw new Error('This browser cannot make random identifiers.');
  }
  const hex = Array.from(source.getRandomValues(new Uint8Array(16)), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
  const variant = ((parseInt(hex.charAt(16), 16) & 0x3) | 0x8).toString(16);
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-${variant}${hex.slice(17, 20)}-${hex.slice(20)}`;
}
