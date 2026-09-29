function canonicalId(value: string | number | undefined): string {
  if (typeof value === 'number' && !Number.isSafeInteger(value)) {
    throw new Error('자료 식별자가 올바르지 않습니다. 자료 목록에서 다시 열어주세요.');
  }
  const id = String(value ?? '');
  if (!/^[1-9]\d*$/.test(id) || BigInt(id) > 9223372036854775807n) {
    throw new Error('자료 식별자가 올바르지 않습니다. 자료 목록에서 다시 열어주세요.');
  }
  return id;
}

/** Keep Material and UploadedFile identifiers distinct; the server checks ownership. */
export function quizDocumentId(mode: 'create' | 'edit', materialId?: string, pdfId?: number): string {
  if (materialId !== undefined) return canonicalId(materialId);
  if (mode === 'edit') throw new Error('자료 ID가 없습니다. 자료 목록에서 다시 열어주세요.');
  return `pdf_${canonicalId(pdfId)}`;
}
