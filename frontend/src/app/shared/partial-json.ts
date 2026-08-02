export interface PartialJson {
  readonly value: unknown;
  readonly complete: boolean;
}

const maxRepairSteps = 200;

export function parsePartialJson(text: string): PartialJson | null {
  const source = text
    .trim()
    .replace(/^```(?:json)?\s*/iu, '')
    .replace(/\s*```$/u, '');
  if (!/^(?:\{\s*(?:"|\}|$)|\[\s*(?:["{[\]\-\dtfn]|$))/u.test(source)) {
    return null;
  }
  try {
    return { value: JSON.parse(source) as unknown, complete: true };
  } catch {
    // not valid json yet, try to repair it below
  }
  let repaired = closeString(source);
  for (let step = 0; step < maxRepairSteps && repaired; step += 1) {
    try {
      return { value: JSON.parse(repaired + closers(repaired)) as unknown, complete: false };
    } catch {
      repaired = dropLastToken(repaired);
    }
  }
  return null;
}

function closeString(text: string): string {
  let inString = false;
  let escaped = false;
  for (const character of text) {
    if (escaped) {
      escaped = false;
    } else if (character === '\\') {
      escaped = inString;
    } else if (character === '"') {
      inString = !inString;
    }
  }
  if (!inString) {
    return text;
  }
  const cut = escaped ? text.slice(0, -1) : text.replace(/\\u[\da-f]{0,3}$/iu, '');
  return `${cut}"`;
}

function closers(text: string): string {
  const open: string[] = [];
  let inString = false;
  let escaped = false;
  for (const character of text) {
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (character === '\\') {
        escaped = true;
      } else if (character === '"') {
        inString = false;
      }
    } else if (character === '"') {
      inString = true;
    } else if (character === '{') {
      open.push('}');
    } else if (character === '[') {
      open.push(']');
    } else if (character === '}' || character === ']') {
      open.pop();
    }
  }
  return open.reverse().join('');
}

function dropLastToken(text: string): string {
  const trimmed = text.trimEnd();
  const last = trimmed.at(-1);
  if (last === ',' || last === ':' || last === '{' || last === '[') {
    return trimmed.slice(0, -1);
  }
  if (last === '"') {
    return trimmed.slice(0, stringStart(trimmed));
  }
  const partial = /[\w.+-]+$/u.exec(trimmed);
  return partial ? trimmed.slice(0, partial.index) : trimmed.slice(0, -1);
}

function stringStart(text: string): number {
  for (let index = text.length - 2; index >= 0; index -= 1) {
    if (text[index] !== '"') {
      continue;
    }
    let backslashes = 0;
    while (text[index - 1 - backslashes] === '\\') {
      backslashes += 1;
    }
    if (backslashes % 2 === 0) {
      return index;
    }
  }
  return 0;
}
