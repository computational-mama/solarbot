const STOP_WORDS = new Set([
  "a","an","the","and","or","but","in","on","at","to","for","of","with",
  "is","are","was","were","be","been","being","have","has","had","do","does",
  "did","will","would","could","should","may","might","shall","can","i","you",
  "he","she","it","we","they","this","that","these","those","what","which",
]);

export function buildSparseVector(text: string): { indices: number[]; values: number[] } {
  const tokens = text
    .toLowerCase()
    .replace(/[^a-z0-9一-鿿]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter((t) => t.length > 1 && !STOP_WORDS.has(t));

  const freq: Map<number, number> = new Map();
  for (const token of tokens) {
    let hash = 0;
    for (let i = 0; i < token.length; i++) {
      hash = (Math.imul(31, hash) + token.charCodeAt(i)) >>> 0;
    }
    const idx = hash % 30000;
    freq.set(idx, (freq.get(idx) ?? 0) + 1);
  }

  const total = tokens.length || 1;
  const indices: number[] = [];
  const values: number[] = [];
  for (const [idx, count] of freq) {
    indices.push(idx);
    values.push(count / total);
  }
  return { indices, values };
}

export function chunkText(
  text: string,
  maxSize = 600,
  overlap = 100
): string[] {
  const clean = text.replace(/\s+/g, " ").trim();
  const sentences = splitSentences(clean);

  const chunks: string[] = [];
  let current = "";

  for (const sentence of sentences) {
    if ((current + " " + sentence).length <= maxSize) {
      current += (current ? " " : "") + sentence;
    } else {
      chunks.push(current.trim());
      current = sentence;
    }
  }

  if (current.trim()) {
    chunks.push(current.trim());
  }

  // overlap 处理
  if (overlap > 0 && chunks.length > 1) {
    return applyOverlap(chunks, overlap);
  }

  return chunks;
}

/**
 * 简单句子分割（中英文兼容）
 */
function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[。！？.!?])/)
    .map(s => s.trim())
    .filter(Boolean);
}

/**
 * 添加重叠上下文
 */
function applyOverlap(chunks: string[], overlap: number): string[] {
  const result: string[] = [];

  for (let i = 0; i < chunks.length; i++) {
    if (i === 0) {
      result.push(chunks[i]);
    } else {
      const prev = chunks[i - 1];
      // Take trailing full sentences from previous chunk up to overlap chars
      const sentences = splitSentences(prev);
      let overlapText = "";
      for (let j = sentences.length - 1; j >= 0; j--) {
        const candidate = sentences.slice(j).join(" ");
        if (candidate.length <= overlap) {
          overlapText = candidate;
        } else {
          break;
        }
      }
      result.push(overlapText ? overlapText + " " + chunks[i] : chunks[i]);
    }
  }

  return result;
}
