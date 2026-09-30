/** Plain text entering an HTML template, including quoted attribute values. */
export function htmlText(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]!);
}

export function htmlLines(value: unknown): string {
  return htmlText(value).replace(/\r?\n/g, '<br/>');
}
